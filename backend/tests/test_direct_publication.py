import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from garminconnect import GarminConnectNotFoundError
from app.database import connect
from app.garmin_training_publish import send, preview, approve, run, view
from app.training import list_training, encoded
from test_training_adjustments import NOW, TZ
import test_garmin_publication as fixtures


class DirectPublicationTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.GarminPublicationQC()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.path=self.case.path
        self.client=self.case.client
        self.factory=self.case.factory

    def publish(self):
        job=send({'next_days':7,'timezone':TZ},self.path,self.factory,NOW)
        if job.get('id') and job['status']=='queued':
            run(job['id'],self.path,self.factory)
            return view(job['id'],self.path)
        return job

    def test_direct_send_queues_without_separate_approval_and_only_covers_seven_days(self):
        job=send({'next_days':7,'timezone':TZ},self.path,self.factory,NOW)
        self.assertEqual(job['status'],'queued',job)
        days=[item['scheduled_date'] for item in job['items']]
        self.assertTrue(days)
        self.assertTrue(all(NOW.date().isoformat()<=day<(NOW.date()+timedelta(days=7)).isoformat() for day in days))
        run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified')
        counts=(self.client.creates,self.client.schedules)
        self.assertEqual(self.publish()['status'],'verified')
        self.assertEqual((self.client.creates,self.client.schedules),counts)

    def test_removes_skipped_app_entries_and_preserves_outside_window_and_personal_entries(self):
        self.assertEqual(self.publish()['status'],'verified')
        first=next(w for w in list_training(self.path)['workouts'] if w['scheduled_for'][:10]==NOW.date().isoformat())
        with connect(self.path) as c:
            link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(first['id'],)).fetchone()
            removed=link['remote_schedule_id']
            c.execute("UPDATE planned_workouts SET completion_status='skipped',publish_status='update_needed',revision=revision+1 WHERE id=?",(first['id'],))
        self.client.calendar['personal']={'workoutScheduleId':999,'workoutId':999,'date':NOW.date().isoformat()}
        personal=copy.deepcopy(self.client.calendar['personal'])
        later=next(w for w in list_training(self.path)['workouts'] if w['id']!=first['id'])
        with connect(self.path) as c:
            later_day=(NOW.date()+timedelta(days=7)).isoformat()
            definition={**later['definition'],'scheduled_date':later_day}
            c.execute('UPDATE planned_workouts SET definition_json=?,scheduled_for=? WHERE id=?',(encoded(definition),later_day+'T12:00:00+03:00',later['id']))
        job=preview({'workout_ids':[later['id']],'timezone':TZ},self.path,self.factory,NOW)
        approve(job['id'],self.path,self.factory,NOW);run(job['id'],self.path,self.factory)
        with connect(self.path) as c:outside=c.execute('SELECT remote_schedule_id FROM garmin_publication_links WHERE workout_id=?',(later['id'],)).fetchone()[0]
        result=self.publish()
        self.assertEqual(result['status'],'verified',result)
        self.assertNotIn(removed,self.client.calendar)
        self.assertEqual(self.client.calendar['personal'],personal)
        self.assertIn(outside,self.client.calendar)
        self.assertEqual(next(w for w in list_training(self.path)['workouts'] if w['id']==first['id'])['publish_status'],'published')

    def test_removes_obsolete_app_standalone_entry_within_window(self):
        definition=self.case.workout['definition']
        job=preview({'definition':definition,'scheduled_date':NOW.date().isoformat(),'timezone':TZ},self.path,self.factory,NOW)
        approve(job['id'],self.path,self.factory,NOW);run(job['id'],self.path,self.factory)
        old=view(job['id'],self.path)['items'][0]['remote_schedule_id']
        self.assertEqual(self.publish()['status'],'verified')
        self.assertNotIn(old,self.client.calendar)

    def test_confirmed_missing_workout_is_recreated_once_and_old_calendar_removed(self):
        self.assertEqual(self.publish()['status'],'verified')
        with connect(self.path) as c:link=dict(c.execute('SELECT * FROM garmin_publication_links ORDER BY rowid LIMIT 1').fetchone())
        old=link['remote_workout_id'];calendar=link['remote_schedule_id']
        del self.client.workouts[old]
        original=self.client.get_workout_by_id
        def read(identifier):
            if str(identifier)==old:raise GarminConnectNotFoundError('API Error 404')
            return original(identifier)
        creates=self.client.creates
        with patch.object(self.client,'get_workout_by_id',side_effect=read):
            result=self.publish()
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual(self.client.creates,creates+1)
        self.assertNotIn(calendar,self.client.calendar)
        self.assertEqual(self.publish()['status'],'verified')
        self.assertEqual(self.client.creates,creates+1)

    def test_failed_older_revision_is_superseded_by_rest_day(self):
        self.assertEqual(self.publish()['status'],'verified')
        first=self.case.workout
        job=preview({'workout_ids':[first['id']],'timezone':TZ},self.path,self.factory,NOW)
        approve(job['id'],self.path,self.factory,NOW)
        with connect(self.path) as c:
            c.execute("UPDATE garmin_publication_jobs SET status='attention' WHERE id=?",(job['id'],))
            c.execute("UPDATE garmin_publication_items SET state='retryable' WHERE job_id=?",(job['id'],))
            c.execute("UPDATE planned_workouts SET completion_status='skipped',publish_status='update_needed',revision=revision+1 WHERE id=?",(first['id'],))
            old=c.execute('SELECT remote_schedule_id FROM garmin_publication_links WHERE workout_id=?',(first['id'],)).fetchone()[0]
        result=self.publish()
        self.assertEqual(result['status'],'verified',result)
        self.assertNotIn(old,self.client.calendar)

    def test_network_loss_does_not_recreate_existing_workouts(self):
        self.assertEqual(self.publish()['status'],'verified')
        count=self.client.creates
        self.client.read_failure=True
        result=self.publish()
        self.assertEqual(result['status'],'attention',result)
        self.assertEqual(self.client.creates,count)

    def test_garmin_calendar_id_format_is_reconciled_without_duplicate_schedule(self):
        original=self.client.get_scheduled_workouts
        def calendar(year,month):
            response=original(year,month)
            return {'calendarItems':[{**{k:v for k,v in row.items() if k!='workoutScheduleId'},
                                     'id':row['workoutScheduleId'],'itemType':'workout'} for row in response['calendarItems']]}
        self.client.schedule_timeout=True
        with patch.object(self.client,'get_scheduled_workouts',side_effect=calendar):
            self.assertEqual(self.publish()['status'],'attention')
            self.assertEqual(self.publish()['status'],'verified')
            self.assertEqual(self.client.creates,self.client.schedules)
            first=self.case.workout['id']
            with connect(self.path) as c:
                schedule=c.execute('SELECT remote_schedule_id FROM garmin_publication_links WHERE workout_id=?',(first,)).fetchone()[0]
                c.execute("UPDATE planned_workouts SET completion_status='skipped',publish_status='update_needed',revision=revision+1 WHERE id=?",(first,))
            self.assertEqual(self.publish()['status'],'verified')
            self.assertNotIn(schedule,self.client.calendar)

    def test_send_api_starts_worker_without_preview_approval_request(self):
        from app.main import send_garmin_publication, GarminPublicationPreview
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app=FastAPI()
        app.post('/send')(send_garmin_publication)
        from app.garmin_training_publish import send as real_send, run as real_run
        with patch('app.garmin_training_publish.send',side_effect=lambda args:real_send(args,self.path,self.factory,NOW)), \
             patch('app.garmin_training_publish.run',side_effect=lambda identifier:real_run(identifier,self.path,self.factory)):
            response=TestClient(app).post('/send',json={'next_days':7,'timezone':TZ})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'queued')
        result=view(response.json()['id'],self.path)
        self.assertEqual(result['status'],'verified',result)

    def test_midweek_send_fills_through_next_week_instead_of_stopping_at_sunday(self):
        thursday=NOW+timedelta(days=3)
        job=send({'next_days':7,'timezone':TZ},self.path,self.factory,thursday)
        self.assertEqual(job['status'],'queued',job)
        days=[item['scheduled_date'] for item in job['items'] if item['action']!='unschedule']
        self.assertIn((NOW.date()+timedelta(days=7)).isoformat(),days)
        self.assertIn((NOW.date()+timedelta(days=9)).isoformat(),days)
        self.assertTrue(all(thursday.date().isoformat()<=day<(thursday.date()+timedelta(days=7)).isoformat() for day in days))
        self.assertEqual(days,sorted(days))
        run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified')
        self.assertEqual(sorted(row['date'] for row in self.client.calendar.values()),sorted(days))

    def test_publishing_after_swap_uses_saved_dates_without_duplicate_workouts(self):
        from app.active_training import swap_workouts
        self.assertEqual(self.publish()['status'],'verified')
        workouts=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])
        a,b=workouts[:2];creates=self.client.creates
        swap_workouts(a['id'],b['id'],a['revision'],b['revision'],self.path,NOW,manual_override=True)
        result=self.publish()
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual(self.client.creates,creates)
        with connect(self.path) as c:
            for identifier in (a['id'],b['id']):
                row=c.execute('SELECT * FROM planned_workouts WHERE id=?',(identifier,)).fetchone()
                link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(identifier,)).fetchone()
                expected=json.loads(row['definition_json'])['scheduled_date']
                self.assertEqual(self.client.calendar[link['remote_schedule_id']]['date'],expected)
                self.assertEqual(link['scheduled_date'],expected)
        self.assertEqual(len(self.client.calendar),len(result['items']))

    def test_retryable_older_item_does_not_prevent_other_saved_date_changes(self):
        from app.active_training import swap_workouts
        self.assertEqual(self.publish()['status'],'verified')
        workouts=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])
        a,b,failed=workouts[:3]
        old=preview({'workout_ids':[failed['id']],'timezone':TZ},self.path,self.factory,NOW)
        approve(old['id'],self.path,self.factory,NOW)
        with connect(self.path) as c:
            c.execute("UPDATE garmin_publication_items SET state='retryable' WHERE job_id=?",(old['id'],))
            c.execute("UPDATE garmin_publication_jobs SET status='attention' WHERE id=?",(old['id'],))
            remote=c.execute('SELECT remote_workout_id FROM garmin_publication_links WHERE workout_id=?',(failed['id'],)).fetchone()[0]
        swap_workouts(a['id'],b['id'],a['revision'],b['revision'],self.path,NOW,manual_override=True)
        original=self.client.get_workout_by_id
        def read(identifier):
            if str(identifier)==remote:raise ValueError('Read-back unavailable for this workout')
            return original(identifier)
        with patch.object(self.client,'get_workout_by_id',side_effect=read):result=self.publish()
        self.assertNotEqual(result['id'],old['id'])
        self.assertEqual(result['status'],'attention')
        with connect(self.path) as c:
            for identifier in (a['id'],b['id']):
                row=c.execute('SELECT definition_json FROM planned_workouts WHERE id=?',(identifier,)).fetchone()
                link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(identifier,)).fetchone()
                self.assertEqual(link['scheduled_date'],json.loads(row[0])['scheduled_date'])
        self.assertEqual(view(old['id'],self.path)['items'][0]['state'],'superseded')

    def test_date_changed_during_send_stays_marked_for_update(self):
        first=self.case.workout
        with connect(self.path) as c:
            definition=copy.deepcopy(first['definition']);definition.pop('scheduled_date',None)
            c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(definition),first['id']))
        job=send({'workout_ids':[first['id']],'timezone':TZ},self.path,self.factory,NOW)
        original=self.client.schedule_workout
        def schedule(identifier,day):
            result=original(identifier,day)
            with connect(self.path) as c:
                c.execute("UPDATE planned_workouts SET scheduled_for=?,publish_status='update_needed',revision=revision+1 WHERE id=?",((NOW.date()+timedelta(days=1)).isoformat()+'T12:00:00+03:00',first['id']))
            return result
        with patch.object(self.client,'schedule_workout',side_effect=schedule):run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified')
        workout=next(w for w in list_training(self.path)['workouts'] if w['id']==first['id'])
        self.assertEqual(workout['publish_status'],'update_needed')

    def test_local_date_window_includes_all_sessions_and_excludes_day_eight(self):
        from app.rolling_publication import window
        from app.active_training import _program_workouts
        # UTC Sunday evening is already Monday locally. Date-only intent wins
        # over storage timestamps when determining order and window boundaries.
        now=NOW.replace(hour=22)-timedelta(days=1)
        with connect(self.path) as c:
            root=c.execute('SELECT plan_id FROM active_training_program').fetchone()[0]
            rows=_program_workouts(c,root)
            for index,row in enumerate(rows):
                definition=json.loads(row['definition_json'])
                definition['scheduled_date']=(NOW.date()+timedelta(days=6 if index<3 else 7)).isoformat()
                c.execute('UPDATE planned_workouts SET definition_json=? WHERE id=?',(encoded(definition),row['id']))
            selected=window(c,root,TZ,now,include_pending=False)
        self.assertEqual(set(selected),{r['id'] for r in rows[:3]})

    def test_pending_send_from_old_date_is_found_when_workout_moves_into_window(self):
        self.assertEqual(self.publish()['status'],'verified')
        workout=self.case.workout
        old=preview({'workout_ids':[workout['id']],'timezone':TZ},self.path,self.factory,NOW)
        approve(old['id'],self.path,self.factory,NOW)
        with connect(self.path) as c:
            item=c.execute('SELECT * FROM garmin_publication_items WHERE job_id=?',(old['id'],)).fetchone()
            snapshot=json.loads(item['snapshot_json']);snapshot['date']=(NOW.date()-timedelta(days=2)).isoformat()
            c.execute("UPDATE garmin_publication_items SET state='retryable',snapshot_json=? WHERE id=?",(encoded(snapshot),item['id']))
            c.execute("UPDATE garmin_publication_jobs SET status='attention' WHERE id=?",(old['id'],))
        result=self.publish()
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual(view(old['id'],self.path)['items'][0]['state'],'superseded')

    def test_failed_new_upload_without_verified_mapping_does_not_block_today(self):
        # A later workout was created remotely but failed instruction read-back.
        # It must retain its remote ID for reconciliation, while today's mapped
        # workout can still move from yesterday onto today's Garmin calendar.
        self.case.send()
        today=self.case.workout
        workouts=sorted(list_training(self.path)['workouts'],key=lambda w:w['scheduled_for'])
        later=workouts[1]
        old=send({'workout_ids':[later['id']],'timezone':TZ},self.path,self.factory,NOW)
        original=self.client.upload_workout
        def upload(payload):
            result=original(payload)
            self.client.workouts[str(result['workoutId'])]['workoutName']='Unexpected Garmin read-back'
            return result
        with patch.object(self.client,'upload_workout',side_effect=upload):run(old['id'],self.path,self.factory)
        failed=view(old['id'],self.path)['items'][0]
        self.assertEqual(failed['state'],'retryable')
        self.assertIsNotNone(failed['remote_workout_id'])
        with connect(self.path) as c:
            self.assertIsNone(c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=?',(later['id'],)).fetchone())
            link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(today['id'],)).fetchone()
            yesterday=(NOW.date()-timedelta(days=1)).isoformat()
            c.execute('UPDATE garmin_publication_links SET scheduled_date=? WHERE workout_id=?',(yesterday,today['id']))
            self.client.calendar[link['remote_schedule_id']]['date']=yesterday
        count=self.client.creates
        result=send({'next_days':7,'timezone':TZ},self.path,self.factory,NOW)
        self.assertEqual(result['status'],'queued',result)
        self.assertNotEqual(result['id'],old['id'])
        self.assertTrue(result['blocked'])
        self.assertNotIn(later['id'],[item['workout_id'] for item in result['items']])
        self.assertIn(today['id'],[item['workout_id'] for item in result['items']])
        run(result['id'],self.path,self.factory)
        self.assertEqual(view(result['id'],self.path)['status'],'verified')
        with connect(self.path) as c:link=c.execute('SELECT * FROM garmin_publication_links WHERE workout_id=?',(today['id'],)).fetchone()
        self.assertEqual(self.client.calendar[link['remote_schedule_id']]['date'],NOW.date().isoformat())
        self.assertEqual(view(old['id'],self.path)['items'][0]['remote_workout_id'],failed['remote_workout_id'])
        self.assertEqual(self.client.creates,count+2)  # Only the two other, new workouts.
