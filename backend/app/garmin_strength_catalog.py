"""Full pinned client repertoire plus explicitly reviewed planning metadata.

Catalog presence establishes an export identifier, not user suitability or device
delivery. Never infer equipment, restrictions or capacity from catalog spelling.
"""
from functools import lru_cache
from importlib.metadata import version

# Order is the conservative default preference within each movement/equipment.
# Existing saved IDs are retained only for the same exact exercise.
SPECS=(
 ('pullup_progression','pull','pull_up_bar','PULL_UP','PULL_UP'),
 ('dip_progression','push','dip_bars','TRICEPS_EXTENSION','BODY_WEIGHT_DIP'),
 ('air_squat','squat','bodyweight','SQUAT','AIR_SQUAT'),
 ('hip_raise','hinge','bodyweight','HIP_RAISE','HIP_RAISE'),
 ('kneeling_pushup','push','bodyweight','PUSH_UP','KNEELING_PUSH_UP'),
 ('dead_bug','core','bodyweight','HIP_STABILITY','DEAD_BUG'),
 ('dumbbell_row','pull','dumbbells','ROW','DUMBBELL_ROW'),
 ('band_row','pull','bands','BANDED_EXERCISES','ROW'),
 ('seated_cable_row','pull','gym','ROW','SEATED_CABLE_ROW'),
 ('dumbbell_squat','squat','dumbbells','SQUAT','DUMBBELL_SQUAT'),
 ('dumbbell_press','push','dumbbells','BENCH_PRESS','DUMBBELL_FLOOR_PRESS'),
 ('band_chest_press','push','bands','PUSH_UP','CHEST_PRESS_WITH_BAND'),
 ('machine_leg_press','squat','gym','SQUAT','LEG_PRESS'),
 ('barbell_squat','squat','barbell','SQUAT','BARBELL_BACK_SQUAT'),
 ('barbell_row','pull','barbell','ROW','BARBELL_ROW'),
 ('dumbbell_deadlift','hinge','dumbbells','DEADLIFT','DUMBBELL_DEADLIFT'),
 ('barbell_deadlift','hinge','barbell','DEADLIFT','BARBELL_DEADLIFT'),
 ('band_squat','squat','bands','BANDED_EXERCISES','SQUAT'),
 ('pushup','push','bodyweight','PUSH_UP','PUSH_UP'),
)
ADDITIONAL_SPECS=(('calf_raise','calf','bodyweight','CALF_RAISE','CALF_RAISE'),)


@lru_cache(maxsize=1)
def repertoire():
 from garminconnect.exercises import _RAW
 return tuple((name,category,exercise) for name,category,exercise in _RAW)


def planner_exercises(include_additions=False):
 names={(category,exercise):name for name,category,exercise in repertoire()}
 # Missing entries after a dependency update are ineligible, never approximated.
 return tuple(dict(id=identifier,name=names[(category,exercise)],movement=movement,
                   equipment=equipment,garmin_category=category,garmin_exercise=exercise)
              for identifier,movement,equipment,category,exercise in SPECS+(ADDITIONAL_SPECS if include_additions else ()) if (category,exercise) in names)


def mappings():
 return {e['id']:(e['garmin_category'],e['garmin_exercise']) for e in planner_exercises(include_additions=True)}


def catalog(arguments=None,path=None):
 args=arguments or {};query=args.get('query','');category=args.get('category')
 limit=args.get('limit',100);offset=args.get('offset',0)
 if not isinstance(query,str) or len(query)>200:raise ValueError('Search must be text of at most 200 characters')
 if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0:raise ValueError('Use limit 1–100 and a nonnegative offset')
 if category is not None and not isinstance(category,str):raise ValueError('Choose a catalog category')
 if type(args.get('planner_only',False)) is not bool:raise ValueError('planner_only must be boolean')
 reviewed={(e['garmin_category'],e['garmin_exercise']):e for e in planner_exercises(include_additions=True)}
 rows=[]
 for name,group,exercise in repertoire():
  metadata=reviewed.get((group,exercise))
  if category and group!=category:continue
  if query and query.casefold() not in (' '.join((name,group,exercise))).casefold():continue
  if args.get('planner_only') and not metadata:continue
  rows.append(dict(name=name,category=group,exercise=exercise,planning_metadata=dict(metadata) if metadata else None))
 selected=rows[offset:offset+limit];next_offset=offset+len(selected) if offset+len(selected)<len(rows) else None
 return dict(tool='get_garmin_strength_catalog',source='Installed garminconnect exercise catalog',client_version=version('garminconnect'),
             catalog_count=len(repertoire()),categories=sorted({r[1] for r in repertoire()}),
             planner_count=len(reviewed),records=selected,total_matches=len(rows),limit=limit,offset=offset,
             next_offset=next_offset,truncated=next_offset is not None,
             limitations=['Catalog identifiers are from the pinned installed client, not a freshly queried Garmin/device inventory.',
                          'Unreviewed entries have unknown planning metadata and are excluded from automatic plans.',
                          'Equipment, excluded movements, confirmed capacity and recovery gates still apply. Hip raise fills the hip-dominant/hinge planning slot.',
                          'Catalog presence does not prove delivery or execution on a particular device.'])
