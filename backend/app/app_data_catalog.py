"""Explicit user-data coverage, separate from actual record availability."""
CATALOG=[
 ('strength_catalog','Complete pinned Garmin strength repertoire and reviewed planning metadata','get_garmin_strength_catalog','Paginated search/category lookup; unreviewed equipment/capacity is not inferred'),
 ('health','Normalized health metrics, including sleep, HRV, weight and recorded recovery snapshots','query_app_data','metric_type discovers/filters available fields'),
 ('health_samples','Recorded continuous wellness heart rate, stress and respiration','query_app_data','Up to seven local days; timestamped samples with units and pagination'),
 ('hydration','Recorded hydration events and sweat-loss fields','query_app_data','Local event dates; milliliters and recorded duration seconds'),
 ('abnormal_heart_rate','Recorded threshold alerts, not diagnoses','query_app_data','Local event dates; recorded bpm and threshold bpm'),
 ('nutrition','Local meals, calories/macros, saved day targets and remaining intake','query_app_data','Up to 31 local days; partial nutrients remain explicit'),
 ('garmin_nutrition','Imported Garmin intake/goal summaries, separate from local food logs','query_app_data','Source calendar dates; never added again to local intake'),
 ('food_library','Saved recipes/reusable meals and serving definitions','query_app_data','Current saved library, not a historical as-of snapshot'),
 ('profile','Current profile and active goals','query_app_data','Current saved snapshot, not historical profile reconstruction'),
 ('goals','Current goals including archived goals and dated goal revisions','query_app_data','Current goals plus revisions recorded in the requested local period'),
 ('training','Saved plans/workouts, feedback and actual strength sets','query_app_data','Local scheduled dates; bounded dated workouts, including past/canceled states'),
 ('load_focus','Recorded load-focus totals/target ranges and source availability','get_training_context','Device/account scope; not a Cycling Ability score'),
 ('readiness','Readiness evidence, deductions and tomorrow projection','get_training_readiness / get_projected_training_readiness','App estimates; source/freshness and missing evidence remain explicit'),
 ('activities','Activity history and recorded sensor summaries','list_activities / assess_ride','User-local dates; stable activity identifiers'),
 ('activity_sections','Recorded sections, laps, terrain/effort candidates and comparisons','analyze_activity_sections','Elapsed seconds or recorded kilometers; coverage-aware metrics'),
 ('activity_streams','Continuous recorded activity sensors and FIT laps','get_activity_stream','Bounded elapsed-time selection; missing/gapped data disclosed'),
 ('fit_fields','Retained original FIT messages/developer fields','find_fit_fields / get_fit_activity_data','Field discovery and pagination; unknown semantics are not invented'),
 ('archive','Extended imported Garmin categories and dated records','query_app_data','Category discovery; bounded payloads, explicit dates/truncation'),
 ('maintenance','Equipment, maintenance events and costs','list_maintenance','Date/equipment filters; currencies remain separate'),
 ('publication','Workout/weight send statuses and reasons','query_app_data','Local send evidence only; no credentials, account identity or automatic retry'),
 ('dashboard','Saved chart/card configuration and health/dashboard widget layouts','query_app_data','Current saved configuration; no queries or actions are executed'),
 ('sync','Sync checkpoints, coverage/freshness and latest job state','query_app_data','Current local status, not a new Garmin sync'),
]


def catalog(arguments=None,path=None):
 return {'tool':'get_app_data_catalog','datasets':[{'dataset':dataset,'description':description,'read_tools':tool.split(' / '),'date_and_scope':scope} for dataset,description,tool,scope in CATALOG],
         'support_is_not_availability':True,'note':'This lists supported read paths, not proof that this account has records for each dataset. Query the relevant period/fields; distinguish no records, missing values and unsupported sources.',
         'unavailable':[{'dataset':'cycling_ability','reason':'No verified source mapping is available; load-focus totals must not be relabelled as Cycling Ability.'}],
         'excluded':['Credentials, access/refresh tokens, account identity and secret settings','Raw SQL, arbitrary tables or filesystem access','Writes, publication retries and background actions']}
