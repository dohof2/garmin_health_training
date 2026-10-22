import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from test_training_adjustments import fixture, NOW, TZ
from app.database import connect
from app.training import list_training, encoded
from app.training_prescriptions import endurance, KINDS
from app.training_coach import DEFAULT
from app.garmin_workout_mapping import workout_payload, canonical, digest
from app.garmin_training_publish import preview,approve,run,retry,view,history,recover


class FakeGarmin:
    display_name='fixture-account'
    def __init__(self):
        self.workouts={};self.calendar={};self.creates=0;self.schedules=0;self.updates=0
        self.create_timeout=False;self.schedule_timeout=False;self.fail_schedule=False;self.read_failure=False
    def upload_workout(self,payload):
        self.creates+=1;identifier=str(100+self.creates);self.workouts[identifier]={**copy.deepcopy(payload),'workoutId':int(identifier)}
        if self.create_timeout:self.create_timeout=False;raise TimeoutError('SECRET must not appear in stored errors')
        return {'workoutId':int(identifier)}
    def get_workout_by_id(self,identifier):
        if self.read_failure:raise ConnectionError('SECRET')
        return copy.deepcopy(self.workouts[str(identifier)])
    def get_workouts(self,start,limit):return list(self.workouts.values())[start:start+limit]
    def update_workout(self,identifier,payload):
        self.updates+=1;self.workouts[str(identifier)]={**copy.deepcopy(payload),'workoutId':int(identifier)}
        return self.workouts[str(identifier)]
    def schedule_workout(self,identifier,day):
        if self.fail_schedule:raise ConnectionError('SECRET')
        self.schedules+=1;key=str(200+self.schedules)
        self.calendar[key]={'workoutScheduleId':int(key),'workoutId':int(identifier),'date':day}
        if self.schedule_timeout:self.schedule_timeout=False;raise TimeoutError('SECRET')
        return self.calendar[key]
    def get_scheduled_workout_by_id(self,identifier):return self.calendar[str(identifier)]
    def get_scheduled_workouts(self,year,month):return {'calendarItems':[row for row in self.calendar.values() if row['date'].startswith(f'{year:04d}-{month:02d}')]}
    def unschedule_workout(self,identifier):self.calendar.pop(str(identifier))


class GarminPublicationQC(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'qc.sqlite';fixture(self.path)
        self.client=FakeGarmin();self.factory=lambda path:self.client
        self.workout=list_training(self.path)['workouts'][0]
    def preview(self,**extra):return preview({'workout_ids':[self.workout['id']],'timezone':TZ,**extra},self.path,self.factory,NOW)
    def send(self,**extra):
        p=self.preview(**extra);approve(p['id'],self.path,self.factory,NOW);run(p['id'],self.path,self.factory);return view(p['id'],self.path)

    def test_all_cycling_kinds_keep_targets_order_and_total_time(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                d=endurance(kind,60,DEFAULT,today=NOW.date());p,w=workout_payload(d,'fixture')
                self.assertEqual(sum(s['endConditionValue'] for s in p['workoutSegments'][0]['workoutSteps']),3600)
                self.assertEqual([s['stepOrder'] for s in p['workoutSegments'][0]['workoutSteps']],list(range(1,len(d['steps'])+1)))
                self.assertTrue(w)
        b={**DEFAULT,'ftp_watts':200,'calibration':{'power_access':'both','ftp_confirmed_on':'2026-10-01'}}
        p,w=workout_payload(endurance('tempo',60,b,today=NOW.date()),'fixture')
        self.assertFalse(w);self.assertEqual(p['workoutSegments'][0]['workoutSteps'][0]['targetType']['workoutTargetTypeId'],2)
        p['workoutSegments'][0]['workoutSteps'][0]['endConditionValue']=float(p['workoutSegments'][0]['workoutSteps'][0]['endConditionValue'])
        self.assertEqual(digest(canonical(p)),digest(canonical(copy.deepcopy(p))))
        d=endurance('endurance',45,DEFAULT,'running',today=NOW.date());self.assertEqual(workout_payload(d,'fixture')[0]['sportType']['sportTypeId'],1)

    def test_unsupported_targets_and_duration_mismatch_are_blocked(self):
        for change in ({'sport':'strength'},{'duration_minutes':61},{'steps':[]},{'duration_minutes':float('nan')}):
            with self.subTest(change=change),self.assertRaises(ValueError):workout_payload({**endurance('endurance',60,DEFAULT),**change},'fixture')
        d=endurance('endurance',60,DEFAULT);d['steps'][0]['target']={'type':'power','lower':100,'upper':150,'unit':'W (estimate)'}
        with self.assertRaises(ValueError):workout_payload(d,'fixture')

    def test_preview_no_writes_and_approval_readback_idempotency(self):
        before=list_training(self.path);p=self.preview();self.assertEqual(self.client.creates,0);self.assertEqual(before,list_training(self.path))
        approve(p['id'],self.path,self.factory,NOW);approve(p['id'],self.path,self.factory,NOW)
        run(p['id'],self.path,self.factory);run(p['id'],self.path,self.factory)
        self.assertEqual(view(p['id'],self.path)['status'],'verified');self.assertEqual((self.client.creates,self.client.schedules),(1,1))
        again=self.send();self.assertEqual(again['items'][0]['action'],'unchanged');self.assertEqual(self.client.creates,1)
        row=list_training(self.path)['workouts'][0];self.assertEqual(row['publish_status'],'published');self.assertEqual(row['garmin_workout_id'],'101')

    def test_stale_expired_and_changed_account_previews_rejected(self):
        p=self.preview()
        with self.assertRaises(ValueError):approve(p['id'],self.path,self.factory,NOW+timedelta(hours=1))
        self.client.display_name='another-account'
        with self.assertRaises(ValueError):approve(p['id'],self.path,self.factory,NOW)
        self.client.display_name='fixture-account'
        with connect(self.path) as c:c.execute('UPDATE planned_workouts SET revision=revision+1 WHERE id=?',(self.workout['id'],))
        with self.assertRaises(ValueError):approve(p['id'],self.path,self.factory,NOW)
        self.assertEqual(self.client.creates,0)

    def test_unknown_create_reconciles_without_duplicate(self):
        self.client.create_timeout=True;job=self.send(schedule=False)
        self.assertEqual(job['status'],'attention');self.assertEqual(job['items'][0]['state'],'unknown');self.assertNotIn('SECRET',json.dumps(job))
        retry(job['id'],self.path,self.factory);run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified');self.assertEqual(self.client.creates,1)

    def test_schedule_timeout_reconciles_without_duplicate(self):
        self.client.schedule_timeout=True;job=self.send()
        self.assertEqual(job['status'],'attention');self.assertEqual(job['items'][0]['remote_workout_id'],'101')
        retry(job['id'],self.path,self.factory);run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified');self.assertEqual((self.client.creates,self.client.schedules),(1,1))

    def test_unresolved_schedule_blocks_new_publication(self):
        self.client.fail_schedule=True;job=self.send();self.assertEqual(job['status'],'attention')
        self.client.fail_schedule=False;run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'attention');self.assertEqual(self.client.creates,1)
        p=self.preview()
        with self.assertRaises(ValueError):approve(p['id'],self.path,self.factory,NOW)

    def test_changed_workout_updates_same_remote_id_and_skipped_unschedules(self):
        job=self.send();original=job['items'][0]['remote_workout_id']
        from app.training_adjustments import propose,save
        p=propose('Make today easier',self.path,NOW);self.assertEqual(p['status'],'proposal')
        save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        self.assertTrue(history(self.path)['pending_updates'])
        updated=self.send();self.assertEqual(updated['status'],'verified');self.assertEqual(updated['items'][0]['action'],'update')
        self.assertEqual((self.client.creates,self.client.updates),(1,1));self.assertEqual(updated['items'][0]['remote_workout_id'],original)
        p=propose('Skip my ride today',self.path,NOW);save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        removed=self.send();self.assertEqual(removed['items'][0]['action'],'unschedule');self.assertEqual(removed['status'],'verified')
        self.assertFalse(self.client.calendar);self.assertEqual(len(self.client.workouts),1)

    def test_remote_edit_is_preserved_as_conflict(self):
        self.send();self.client.workouts['101']['workoutName']='Edited in Garmin'
        from app.training_adjustments import propose,save
        p=propose('Make today easier',self.path,NOW);save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        job=self.send();self.assertEqual(job['status'],'attention');self.assertEqual(self.client.updates,0)
        self.assertEqual(self.client.workouts['101']['workoutName'],'Edited in Garmin')

    def test_standalone_and_library_only(self):
        p=preview({'definition':endurance('endurance',30,DEFAULT),'timezone':TZ,'schedule':False},self.path,self.factory,NOW)
        approve(p['id'],self.path,self.factory,NOW);run(p['id'],self.path,self.factory)
        self.assertEqual(view(p['id'],self.path)['status'],'verified');self.assertEqual(self.client.schedules,0)
        self.assertFalse(list_training(self.path)['workouts'][0]['garmin_workout_id'])

    def test_crash_recovery_never_sends_automatically(self):
        p=self.preview();approve(p['id'],self.path,self.factory,NOW)
        with connect(self.path) as c:
            c.execute("UPDATE garmin_publication_jobs SET status='running' WHERE id=?",(p['id'],))
            c.execute("UPDATE garmin_publication_items SET state='creating' WHERE job_id=?",(p['id'],))
        recover(self.path);self.assertEqual(self.client.creates,0)
        self.assertEqual(view(p['id'],self.path)['items'][0]['state'],'unknown')
        run(p['id'],self.path,self.factory);self.assertEqual(self.client.creates,0)

    def test_batch_and_concurrent_approval_reserve_workouts(self):
        ids=[w['id'] for w in list_training(self.path)['workouts']]
        p=preview({'workout_ids':ids,'timezone':TZ},self.path,self.factory,NOW)
        other=self.preview()
        approve(p['id'],self.path,self.factory,NOW)
        with self.assertRaises(ValueError):approve(other['id'],self.path,self.factory,NOW)
        run(p['id'],self.path,self.factory)
        job=view(p['id'],self.path);self.assertEqual(job['status'],'verified');self.assertEqual(self.client.creates,len(ids))

    def test_reschedule_keeps_workout_id_and_replaces_only_owned_calendar_entry(self):
        self.send()
        from app.active_training import reschedule
        w=list_training(self.path)['workouts'][0]
        reschedule(w['id'],None,w['revision'],self.path,NOW,scheduled_date='2026-10-26')
        job=self.send();self.assertEqual(job['status'],'verified');self.assertEqual(job['items'][0]['action'],'reschedule')
        self.assertEqual(self.client.creates,1);self.assertEqual(len(self.client.calendar),1)
        self.assertEqual(next(iter(self.client.calendar.values()))['date'],'2026-10-26')

    def test_rate_limit_can_retry_without_recreating_workout(self):
        from garminconnect import GarminConnectTooManyRequestsError
        original=self.client.schedule_workout
        with patch.object(self.client,'schedule_workout',side_effect=GarminConnectTooManyRequestsError('SECRET')):
            job=self.send()
        self.assertEqual(job['items'][0]['state'],'retryable')
        retry(job['id'],self.path,self.factory);run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified');self.assertEqual(self.client.creates,1)

    def test_unchanged_workout_is_still_read_back(self):
        self.send();self.client.workouts['101']['workoutName']='Edited elsewhere'
        job=self.send();self.assertEqual(job['items'][0]['action'],'unchanged')
        self.assertEqual(job['status'],'attention');self.assertEqual(self.client.creates,1)

    def test_backup_preserves_receipts_but_does_not_resume_pending_writes(self):
        from app.exports import create_backup,restore_backup
        p=self.preview();approve(p['id'],self.path,self.factory,NOW)
        output=Path(self.directory.name)/'backup.zip';target=Path(self.directory.name)/'restored.sqlite'
        create_backup(output,self.path);restore_backup(output,target)
        self.assertEqual(view(p['id'],target)['status'],'restored_review')
        run(p['id'],target,self.factory);self.assertEqual(self.client.creates,0)

    def test_fractional_history_ceiling_does_not_break_active_plan_generation(self):
        from app.training import _context
        from app.training_coach import preview as plan_preview
        with connect(self.path) as c:context=_context(c,NOW,timezone_name=TZ)
        context['volume_estimates']['cycling']['long_session_minutes']=60.7
        with patch('app.training_coach._context',return_value=context):
            result=plan_preview({**DEFAULT,'goal':'ftp','duration_confirmed':True},NOW.date()+timedelta(days=7),TZ,self.path,NOW)
        self.assertTrue(result['sessions']);self.assertTrue(all(w['definition']['duration_minutes']<=60 for w in result['sessions']))

    def test_update_succeeded_but_readback_failed_does_not_repeat_update(self):
        self.send()
        from app.training_adjustments import propose,save
        p=propose('Make today easier',self.path,NOW);save({'message':p['request'],'fingerprint':p['fingerprint']},self.path,NOW)
        original=self.client.update_workout
        def update_then_disconnect(identifier,payload):
            result=original(identifier,payload);self.client.read_failure=True;return result
        with patch.object(self.client,'update_workout',side_effect=update_then_disconnect):job=self.send()
        self.assertEqual(job['status'],'attention');self.client.read_failure=False
        run(job['id'],self.path,self.factory)
        self.assertEqual(view(job['id'],self.path)['status'],'verified');self.assertEqual(self.client.updates,1)
