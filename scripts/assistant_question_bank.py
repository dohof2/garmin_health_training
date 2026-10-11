"""Human-language acceptance cases; expected behavior is independent of routing code."""
CASES = []


def add(category, message, **expected):
    CASES.append({'id':f'{category}-{sum(c["category"]==category for c in CASES)+1:02}',
                  'category':category,'message':message,**expected})


for question in [
    'How was my last ride compared to other rides this year?',
    'how was my last ride compared to the rides in the last year?',
    'Compare my latest ride with other rides this month.',
    'How does my most recent bike ride stack up against rides in the past 12 months?',
    'Compare my last cycling ride to other rides last year.',
    'How was my latest ride versus other rides this week?',
    'Compare my most recent ride with other rides over the past three months.',
    'Compare my latest bicycle ride to other rides.']:
    add('default-comparison',question,tool='compare_latest_ride',oracle='ride') if not question.endswith('other rides.') else add('clarification',question,clarify='Which period')

for case,bounds in zip([c for c in CASES if c['category']=='default-comparison'],[
    ['2026-01-01','2026-10-11'],['2025-10-11','2026-10-11'],['2026-10-01','2026-10-11'],
    ['2025-10-11','2026-10-11'],['2025-01-01','2025-12-31'],['2026-10-05','2026-10-11'],
    ['2026-07-11','2026-10-11']]):
    case['period']=bounds

PERIODS = [('this year','2026-01-01','2026-10-11'),('the last year','2025-10-11','2026-10-11'),
           ('last year','2025-01-01','2025-12-31'),('this month','2026-10-01','2026-10-11'),
           ('the past three months','2026-07-11','2026-10-11'),('last month','2026-09-01','2026-09-30')]
for phrase,start,end in PERIODS:
    for prefix in ['How was my last ride compared to all other rides',
                   'Compare my latest bike ride with general records',
                   'How does my most recent ride stack up against all rides']:
        add('ride',f'{prefix} {phrase}?',tool='compare_latest_ride',period=[start,end],oracle='ride')

for metric,metric_id in [('weight','weight'),('resting heart rate','resting_heart_rate'),
                         ('steps','steps'),('sleep score','sleep_score'),('sleep duration','sleep_duration'),
                         ('hydration','hydration'),('acute training load','acute_training_load'),
                         ('cycling cadence','activity_cadence'),('cycling power','activity_power'),
                         ('cycling VO2 max','vo2_cycling')]:
    for phrase,start,end in [PERIODS[0],PERIODS[1]]:
        add('plot',f'Plot my {metric} over {phrase}.',tool='create_plots',metrics=[metric_id],period=[start,end])
for message,metrics,extra in [
    ('Plot weekly median weight this year.',['weight'],{'aggregation':'weekly_median'}),
    ('Plot steps as a monthly sum this year.',['steps'],{'aggregation':'monthly_sum'}),
    ('Plot daily mean resting heart rate this month.',['resting_heart_rate'],{'aggregation':'daily_mean'}),
    ('Plot weight with a 7-day rolling average this year.',['weight'],{'rolling_days':7}),
    ('Plot hydration with a 14-day moving average this month.',['hydration'],{'rolling_days':14}),
    ('Plot steps as a bar chart this month.',['steps'],{'kind':'bar'}),
    ('Plot cycling power versus speed across all rides this year.',['activity_power','activity_speed'],{'kind':'scatter'}),
    ('Plot resting heart rate versus cycling VO2 max this year with correlation.',['resting_heart_rate','vo2_cycling'],{'kind':'scatter','correlation':True}),
    ('Plot sleep duration against cycling power on the same date this year.',['sleep_duration','activity_power'],{'kind':'scatter'}),
    ('Plot body battery latest versus sleep score this month.',['body_battery_latest','sleep_score'],{'kind':'scatter'}),
    ('Plot weight versus date this year.',['weight'],{'kind':'scatter','x_metric':'date'}),
    ('Plot cadence against sleep score on the same date this month.',['activity_cadence','sleep_score'],{'kind':'scatter'})]:
    add('plot',message,tool='create_plots',metrics=metrics,spec=extra)

for metric,metric_id in [('steps','steps'),('sleep duration','sleep_duration'),('weight','weight'),
                         ('resting heart rate','resting_heart_rate'),('sleep score','sleep_score'),('hydration','hydration')]:
    for prefix in ['Summarize my','What was my average']:
        add('summary',f'{prefix} {metric} over the last seven days?',tool='get_health_summary',
            period=['2026-10-05','2026-10-11'],summary_metric=metric_id,oracle='summary')
for message,period in [('How many steps did I record yesterday?',['2026-10-10','2026-10-10']),
                       ('How was my sleep this week?',['2026-10-05','2026-10-11']),
                       ('What was my average weight last month?',['2026-09-01','2026-09-30']),
                       ('Summarize my hydration this year.',['2026-01-01','2026-10-11'])]:
    add('summary',message,tool='get_health_summary',period=period,oracle='summary')

for reply in ['All rides','General records','all rides please','the general comparison please','overall','All rides this year']:
    add('followup',reply,seed='How was my last ride compared to other rides this year?',
        tool='compare_latest_ride',period=['2026-01-01','2026-10-11'],oracle='ride')
for reply in ['Same route','GPS','only rides on the same GPS route','matching routes please']:
    add('followup',reply,seed='How was my last ride compared to other rides this year?',
        tool='find_same_course_rides',period=['2026-01-01','2026-10-11'])
add('default-comparison','Compare my latest ride with other rides this year without GPS.',tool='compare_latest_ride',period=['2026-01-01','2026-10-11'],oracle='ride')
for message,spec in [('Add a trend line and correlation',{'trend_line':True,'correlation':True}),
                      ('Show it for this year',{'start':'2026-01-01','end':'2026-10-11'}),
                      ('Make it a bar chart',{'kind':'bar'}),('Show resting heart rate instead',{'metric':'resting_heart_rate'})]:
    add('followup',message,seed='Plot weight over the last year.',tool='create_plots',spec=spec,plot_context=True)

for message in ['What is my training readiness today?','Am I ready to train today?',
                'What was my readiness yesterday?','Show my readiness for 2026-09-27.',
                'What is my projected readiness tomorrow?','Forecast training readiness for tomorrow.']:
    add('readiness',message,tool='get_projected_training_readiness' if 'tomorrow' in message else 'get_training_readiness')
for message in ['I want to increase FTP.','Help me build endurance.',
                'Plan my week around a hard three-hour cycling trip on Wednesday at 08:00.',
                'I want to stay in shape.','Preview a training plan for the next 12 weeks.',
                'I want to improve FTP and have a hard 180 minute ride on Wednesday starting at 08:00.',
                'Build endurance with a running training plan.',
                'Adjust my training plan around a hard trip on Friday.']:
    add('training',message,tool='preview_training_plan')

for message,clarify in [('Plot body battery versus sleep score this year.','Which Body Battery'),
                       ('Plot weight with a rolling average.','How many days'),
                       ('Plot median weight.','daily, weekly or monthly'),
                       ('Plot weekly median weight and a 7-day rolling average.','separate plots'),
                       ('Plot sleep score versus blood glucose this year.','two supported metrics'),
                       ('Compare my latest ride with all rides.','Which period')]:
    add('unsupported',message,clarify=clarify,controlled_error=True)

# These intentionally exercise live model selection rather than only explicit commands.
for message,tool in [('How were my steps?','get_health_summary'),
                      ('Have I been sleeping enough recently?','get_health_summary'),
                      ('What data do you have about my rides?','list_activities'),
                      ('Has my weight changed recently?','get_health_summary'),
                      ('How has my HRV been lately?','get_health_summary'),
                      ('Do I have any goals saved?','get_training_context'),
                      ('What is missing from my training preferences?','get_training_context'),
                      ('Was my latest ride effective?','assess_ride'),
                      ('Show my running volume for the last four weeks.','running_volume_trend'),
                      ('List my three most recent activities and available heart rate and power.','list_activities'),
                      ('Can you plot metrics beyond the dashboard presets?','get_chart_catalog'),
                      ('What measurements can I explore?','get_chart_catalog')]:
    if message=='How were my steps?':
        add('model',message,clarify='Which period',review_required=True)
    else:
        add('model',message,tool=tool,review_required=True)

for message,metrics in [('Plot weight from 2026-01-01 to 2026-02-01 and steps from 2026-03-01 to 2026-04-01.',['weight','steps']),
                         ('Plot sleep score; plot steps; plot weight.',['sleep_score','steps','weight']),
                         ('Plot hydration this year; plot acute training load this month.',['hydration','acute_training_load']),
                         ('Graph steps and weight this year.',['steps','weight'])]:
    add('multiplot',message,tool='create_plots',metrics=metrics)

for message,seed,tool,spec in [
    ('latest','Plot body battery versus sleep score this year.','create_plots',{'metric':'body_battery_latest'}),
    ('7 days','Plot weight with a rolling average this year.','create_plots',{'rolling_days':7}),
    ('weekly please','Plot median weight this year.','create_plots',{'aggregation':'weekly_median'}),
    ('last seven days','How were my steps?','get_health_summary',None)]:
    add('clarification-followup',message,seed=seed,tool=tool,**({'spec':spec} if spec else {'period':['2026-10-05','2026-10-11']}))

for message in ['What was the main training benefit of my last ride?', 'What was the primary benefit of my latest ride?']:
    add('benefit',message,tool='compare_latest_ride')
for message in ['I want two hard rides Tuesday and wedensday. Long ride on firday and I can train today. I want FTP improvement.', 'Preview a training plan with a hard ride Tuesday for 3.5 hours and an easy ride Friday for 45 minutes.']:
    add('training',message,tool='preview_training_plan')

assert len(CASES) >= 100
add('default-comparison','how was my ride compared to other rides in the kast 3 months?',tool='compare_latest_ride',period=['2026-07-11','2026-10-11'],oracle='ride')
