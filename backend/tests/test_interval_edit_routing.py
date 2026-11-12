import copy
import unittest
from unittest.mock import patch

from app.endurance_extensions import requested as extension_requested
from app.workout_edits import requested,parse,edit,EditError,work_step
from app.training_prescriptions import endurance
from app.training_coach import DEFAULT
from app.session_changes import preview
from app.training_adjustments import save
from app.training import list_training
from test_training_adjustments import NOW
import test_workout_edit_followthrough as fixtures

EXACT='Add one more 3:00 VO2 work repetition, progressing from 3 to 4 repetitions at the same existing power targets, with 3:00 easy recovery between efforts. Preserve warm-up, cool-down and other targets; accommodate within existing duration by shortening steady endurance if needed. User reports they could easily have done another repetition in their last session.'
NORMAL={'level':'normal','quality_allowed':True,'reasons':[]}


class IntervalEditRoutingTests(unittest.TestCase):
    def test_exact_failed_request_is_interval_edit_and_parses_clocks(self):
        self.assertFalse(extension_requested(EXACT))
        self.assertTrue(requested(EXACT))
        self.assertEqual(parse(EXACT),{'count':4,'work_seconds':180,'recovery_seconds':180})
        self.assertEqual(parse('Change to 4 × 3:00, recovery to 3:00'),{'count':4,'work_seconds':180,'recovery_seconds':180})
        self.assertTrue(extension_requested('Keep the 3 x 3:00 VO2 intervals and add 15 minutes to endurance'))

    def test_actual_fourth_effort_limit_describes_hard_work_not_endurance_extension(self):
        original=endurance('vo2',60,DEFAULT,today=NOW.date())
        before=copy.deepcopy(original)
        with self.assertRaises(EditError) as caught:edit(original,EXACT,NORMAL,True)
        message=str(caught.exception)
        self.assertIn('9:00 to 12:00',message)
        self.assertIn('33.3%',message)
        self.assertIn('20%',message)
        self.assertNotIn('adding endurance',message)
        self.assertEqual(original,before)

    def test_allowed_interval_increase_shrinks_only_endurance_and_keeps_power_and_total(self):
        original=endurance('vo2',60,{**DEFAULT,'ftp_watts':225,'calibration':{'power_access':'both','ftp_confirmed_on':'2026-10-01'}},today=NOW.date())
        warm,work,recovery=original['steps'][:3];cool=original['steps'][-1]
        fill=next(s for s in original['steps'] if s['name']=='Steady endurance')
        steps=[copy.deepcopy(warm)]
        for index in range(5):
            steps.append({**copy.deepcopy(work),'name':f'Work interval {index+1}'})
            if index<4:steps.append({**copy.deepcopy(recovery),'name':f'Recovery {index+1}'})
        steps.extend([{**copy.deepcopy(fill),'duration_seconds':1080},copy.deepcopy(cool)])
        original['steps']=steps
        updated,_=edit(original,'Change to 6 × 3:00, recovery to 3:00; shorten endurance to keep duration',NORMAL,True)
        self.assertEqual(sum(s['duration_seconds'] for s in updated['steps']),3600)
        self.assertEqual(updated['steps'][0],warm)
        self.assertEqual(updated['steps'][-1],cool)
        self.assertEqual(len([s for s in updated['steps'] if work_step(s)]),6)
        self.assertTrue(all(s['target']==work['target'] for s in updated['steps'] if work_step(s)))
        self.assertEqual(next(s['duration_seconds'] for s in updated['steps'] if s['name']=='Steady endurance'),720)

    def test_structured_interval_action_cannot_be_reclassified_by_request_text(self):
        case=fixtures.FollowthroughTests();case.setUp();self.addCleanup(case.doCleanups)
        case.set_definition(endurance('vo2',60,DEFAULT,today=NOW.date()))
        row=case.current();before=list_training(case.path)
        with patch('app.readiness.readiness_history',return_value={'latest':{'score':75,'date':NOW.date().isoformat(),'groups':[],'status':'complete'}}):
            blocked=preview({'workout_id':row['id'],'expected_revision':row['revision'],'action':'edit_intervals',
                             'intervals':{'count':4,'work_seconds':180,'recovery_seconds':180},'request':'Add another repetition and shorten endurance'},case.path,NOW)
            self.assertEqual(blocked['status'],'not_recommended',blocked)
            self.assertIn('33.3%',blocked['message'])
            result=preview({'workout_id':row['id'],'expected_revision':row['revision'],'action':'edit_intervals',
                            'intervals':{'count':2,'work_seconds':180,'recovery_seconds':180},'request':'Keep duration; change endurance to fit'},case.path,NOW)
            self.assertEqual(result['status'],'proposal',result)
            self.assertEqual(list_training(case.path),before)
            save({'message':result['request'],'fingerprint':result['fingerprint']},case.path,NOW)
            self.assertEqual(len([s for s in case.current()['definition']['steps'] if work_step(s)]),2)

    def test_manual_fourth_effort_warns_and_preserves_duration_and_targets(self):
        original=endurance('vo2',60,DEFAULT,today=NOW.date())
        before=copy.deepcopy(original)
        updated,summary=edit(original,EXACT,NORMAL,False,manual_override=True)
        work=[s for s in updated['steps'] if work_step(s)]
        self.assertEqual(len(work),4)
        self.assertTrue(all(s['duration_seconds']==180 and s['target']==original['steps'][1]['target'] for s in work))
        self.assertEqual(sum(s['duration_seconds'] for s in updated['steps']),3600)
        self.assertEqual(updated['steps'][0],original['steps'][0])
        self.assertEqual(updated['steps'][-1],original['steps'][-1])
        self.assertIn('33.3%', ' '.join(summary))
        self.assertIn('20%', ' '.join(summary))
        self.assertIn('Warning', ' '.join(summary))
        self.assertEqual(original,before)

    def test_manual_override_preserves_recovery_and_fit_validation(self):
        original=endurance('vo2',60,DEFAULT,today=NOW.date())
        with self.assertRaises(EditError):
            edit(original,EXACT,{'level':'hold','quality_allowed':False,'reasons':['Recovery hold']},False,manual_override=True)
        with self.assertRaises(EditError):
            edit(original,'Change to 20 × 3:00, recovery to 3:00',NORMAL,False,manual_override=True)

    def test_manual_proposal_saves_with_same_override_and_rechecks_revision(self):
        case=fixtures.FollowthroughTests();case.setUp();self.addCleanup(case.doCleanups)
        case.set_definition(endurance('vo2',60,DEFAULT,today=NOW.date()))
        row=case.current();before=list_training(case.path)
        args={'workout_id':row['id'],'expected_revision':row['revision'],'action':'edit_intervals',
              'intervals':{'count':4,'work_seconds':180,'recovery_seconds':180},'manual_override':True}
        with patch('app.readiness.readiness_history',return_value={'latest':{'score':75,'date':NOW.date().isoformat(),'groups':[],'status':'complete'}}):
            result=preview(args,case.path,NOW)
            self.assertEqual(result['status'],'proposal',result)
            self.assertIn('Warning',' '.join(result['adjustments'][0]['summary']))
            self.assertEqual(list_training(case.path),before)
            save({'message':result['request'],'fingerprint':result['fingerprint']},case.path,NOW)
            self.assertEqual(len([s for s in case.current()['definition']['steps'] if work_step(s)]),4)
            with self.assertRaises(ValueError):
                save({'message':result['request'],'fingerprint':result['fingerprint']},case.path,NOW)

    def test_manual_low_readiness_is_a_warning_while_automatic_increase_is_blocked(self):
        original=endurance('vo2',60,DEFAULT,today=NOW.date())
        policy={'level':'reduce','quality_allowed':False,'reasons':['Lower readiness']}
        updated,summary=edit(original,EXACT,policy,False,manual_override=True)
        self.assertEqual(len([s for s in updated['steps'] if work_step(s)]),4)
        self.assertIn('Lower readiness',' '.join(summary))
        with self.assertRaises(EditError):edit(original,EXACT,policy,False)
