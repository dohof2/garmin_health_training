"""Additional read-only Garmin data. Retain full payloads even before normalization."""
from __future__ import annotations
import math
from .sync import SyncError

DAILY_METHODS = (
    'get_hydration_data', 'get_stress_data', 'get_respiration_data', 'get_spo2_data',
    'get_training_status', 'get_daily_training_status', 'get_body_battery',
    'get_body_battery_events', 'get_heart_rates', 'get_steps_data', 'get_floors',
    'get_intensity_minutes_data', 'get_fitnessage_data', 'get_all_day_events',
    'get_all_day_stress', 'get_lifestyle_logging_data', 'get_morning_training_readiness',
    'get_training_readiness', 'get_training_four_week_load_balance',
    'get_endurance_score', 'get_hill_score', 'get_rhr_day', 'get_daily_weigh_ins',
    'get_nutrition_daily_food_log', 'get_nutrition_daily_meals', 'get_nutrition_daily_settings',
    'get_stats', 'get_stats_and_body', 'get_max_metrics', 'get_activities_fordate', 'get_menstrual_reports',
    'get_menstrual_data_for_date', 'get_menstrual_cycle_summary', 'get_menstrual_last_confirmed',
)
RANGE_METHODS = ('get_blood_pressure', 'get_body_composition', 'get_training_load_activities',
                 'get_running_tolerance', 'get_daily_steps', 'get_calories_daily',
                 'get_functional_threshold_power_range', 'get_race_predictions',
                 'get_menstrual_calendar_data', 'get_hrv_data_range', 'get_rhr_daily', 'get_sleep_daily',
                 'get_weekly_intensity_minutes', 'get_progress_summary_between_dates')
STATIC_METHODS = ('get_user_profile', 'get_userprofile_settings', 'get_devices',
    'get_primary_training_device', 'get_heart_rate_zones', 'get_power_zones',
    'get_cycling_ftp', 'get_personal_record', 'get_training_plans', 'get_device_last_used',
    'get_device_alarms', 'get_pregnancy_summary', 'get_available_badges',
    'get_earned_badges', 'get_in_progress_badges', 'get_golf_user_stats',
    'get_golf_club_stats', 'get_next_scheduled_workout', 'get_activity_types',
    'get_full_name', 'get_unit_system', 'get_last_activity')
ACTIVITY_METHODS = ('get_activity_details', 'get_activity_splits', 'get_activity_typed_splits',
    'get_activity_split_summaries', 'get_activity_weather', 'get_activity_gear',
    'get_activity_hr_in_timezones', 'get_activity_power_in_timezones', 'get_activity_exercise_sets')


def fetch_supplementary(client, start, end):
    """Fetch independently so one unavailable family cannot prevent other reads.

    Missing methods are explicitly reported for older clients. Endpoint exceptions
    remain failures (including access/feature errors), never verified empty days.
    """
    result = {'endpoints': {}, 'failures': {}, 'unsupported': [], 'unavailable': {}}
    for name in DAILY_METHODS + RANGE_METHODS + STATIC_METHODS:
        method = getattr(client, name, None)
        if not callable(method):
            result['unsupported'].append(name)
            continue
        args = () if name in STATIC_METHODS else (start, end) if name in RANGE_METHODS else (start,)
        try:
            payload = method(*args, _type='daily') if name=='get_race_predictions' else method(*args)
            if payload is not None and not isinstance(payload, (dict, list, str, int, float, bool)):
                raise SyncError(f'{name} returned an unexpected payload')
            result['endpoints'][name] = payload
        except Exception as error:
            result['failures'][name] = str(error)
    # Collections are paginated; never treat a first page as the whole dataset.
    for name, first in (('get_activities',0),('get_workouts',0),('get_goals',1),('get_golf_summary',0),
                        ('get_adhoc_challenges',0),('get_available_badge_challenges',1),
                        ('get_badge_challenges',1),('get_inprogress_virtual_challenges',1),
                        ('get_non_completed_badge_challenges',1)):
        method = getattr(client,name,None)
        if not callable(method):
            result['unsupported'].append(name)
            continue
        pages = []
        result['endpoints'][name] = pages
        try:
            previous_page = None
            for offset in range(first,first+100000,100):
                page = method(start=offset,limit=100)
                from .activity_metrics import encoded
                signature = encoded(page)
                if previous_page == signature: raise SyncError(f'{name}: pagination repeated a page; collection is incomplete')
                previous_page = signature
                pages.append(page)
                if isinstance(page,list): rows = page
                elif isinstance(page,dict):
                    candidates = [v for v in page.values() if isinstance(v,list)]
                    if not candidates and page.get('totalRows')==0: rows=[]
                    elif len(candidates)==1: rows=candidates[0]
                    else: raise SyncError(f'{name}: cannot verify collection pagination')
                else: raise SyncError(f'{name}: malformed collection response')
                if len(rows)<100: break
            else: raise SyncError(f'{name}: pagination limit reached; collection is incomplete')
        except Exception as error:
            result['failures'][name] = str(error)
    def ids(value,key):
        if isinstance(value,dict):
            if key in value and value[key] is not None: yield value[key]
            for child in value.values(): yield from ids(child,key)
        elif isinstance(value,list):
            for child in value: yield from ids(child,key)
    # Follow identifiers explicitly provided by Garmin, never guessed IDs.
    for parent,key,methods in (
        ('get_workouts','workoutId',('get_workout_by_id',)),
        ('get_devices','deviceId',('get_device_settings',)),
        ('get_training_plans','trainingPlanId',('get_training_plan_by_id',)),
        ('get_training_plans','adaptiveTrainingPlanId',('get_adaptive_training_plan_by_id',)),
        ('get_golf_summary','scorecardId',('get_golf_scorecard','get_golf_shot_data')),
    ):
        for identifier in set(ids(result['endpoints'].get(parent),key)):
            for name in methods:
                method=getattr(client,name,None)
                if callable(method):
                    label=name+':'+str(identifier)
                    try: result['endpoints'][label]=method(identifier)
                    except Exception as error:
                        if name=='get_training_plan_by_id' and 'Not a phased plan' in str(error):
                            result['unavailable'][label]='This plan is not phased; the full plan-list record is retained.'
                        else: result['failures'][label]=str(error)
    if callable(getattr(client,'get_scheduled_workouts',None)):
        year,month = map(int,start.split('-')[:2])
        try:
            schedules=client.get_scheduled_workouts(year,month)
            result['endpoints']['get_scheduled_workouts']=schedules
            fetcher=getattr(client,'get_scheduled_workout_by_id',None)
            if callable(fetcher):
                for identifier in set(ids(schedules,'scheduledWorkoutId')):
                    result['endpoints']['get_scheduled_workout_by_id:'+str(identifier)]=fetcher(identifier)
        except Exception as error:result['failures']['get_scheduled_workouts']=str(error)
    def collect(label,name,*args,**kwargs):
        fetcher=getattr(client,name,None)
        if not callable(fetcher):
            if name not in result['unsupported']:result['unsupported'].append(name)
            return None
        try:
            response=fetcher(*args,**kwargs)
            result['endpoints'][label]=response
            return response
        except Exception as error:
            result['failures'][label]=str(error)
            return None
    collect('get_lactate_threshold:history','get_lactate_threshold',latest=False,start_date=start,end_date=end)
    collect('get_lactate_threshold:latest','get_lactate_threshold')
    collect('get_weekly_steps','get_weekly_steps',end)
    collect('get_weekly_stress','get_weekly_stress',end)
    for sport in ('RUNNING','CYCLING'):
        collect('get_power_zones_for_sport:'+sport,'get_power_zones_for_sport',sport)
        collect('get_functional_threshold_power_range:'+sport,'get_functional_threshold_power_range',start,end,sport=sport)
    for identifier in set(ids(result['endpoints'].get('get_devices'),'deviceId')):
        collect('get_device_solar_data:'+str(identifier),'get_device_solar_data',identifier,start,end)
    profile_ids=set(ids(result['endpoints'].get('get_user_profile'),'userProfileNumber'))
    profile_id=getattr(client,'profile_id',None)
    if isinstance(profile_id,int):profile_ids.add(profile_id)
    for identifier in profile_ids:
        gear=collect('get_gear:'+str(identifier),'get_gear',str(identifier))
        collect('get_gear_defaults:'+str(identifier),'get_gear_defaults',str(identifier))
        gear_ids=set(ids(gear,'uuid'))|set(ids(gear,'gearUUID'))|set(ids(gear,'gearUuid'))
        for gear_id in gear_ids:
            collect('get_gear_stats:'+str(gear_id),'get_gear_stats',gear_id)
            rows=collect('get_gear_activities:'+str(gear_id),'get_gear_activities',gear_id)
            if isinstance(rows,list) and len(rows)>=1000:
                # The installed wrapper caps the first page at 1,000 and has no
                # offset parameter. Read subsequent pages using its documented URL.
                label='get_gear_activities:'+str(gear_id)
                try:
                    from uuid import UUID
                    safe_id=str(UUID(str(gear_id)))
                    for offset in range(1000,100000,1000):
                        page=client.connectapi(f"{client.garmin_connect_activities_baseurl}{safe_id}/gear",params={'start':offset,'limit':1000})
                        if not isinstance(page,list):raise SyncError('Malformed gear activity page')
                        rows.extend(page)
                        if len(page)<1000:break
                    else:raise SyncError('Gear pagination limit reached')
                except Exception as error:result['failures'][label]=str(error)
    for status in ('future','past'):
        method=getattr(client,'get_goals',None)
        if not callable(method):continue
        label='get_goals:'+status
        pages=[];result['endpoints'][label]=pages
        try:
            for offset in range(1,100001,100):
                rows=method(status=status,start=offset,limit=100)
                pages.append(rows)
                if not isinstance(rows,list):raise SyncError('Malformed goal page')
                if len(rows)<100:break
            else:raise SyncError('Goal pagination limit reached')
        except Exception as error:result['failures'][label]=str(error)
    return result


def normalized_metrics(payload, day):
    metrics = []
    hydration = payload['endpoints'].get('get_hydration_data')
    if isinstance(hydration, dict):
        value = hydration.get('valueInML')
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            metrics.append(dict(source_record_id='hydration:'+day, metric_type='hydration', recorded_at=day,
                                value=value, unit='mL', period_start=day, period_end=day))
    return metrics
