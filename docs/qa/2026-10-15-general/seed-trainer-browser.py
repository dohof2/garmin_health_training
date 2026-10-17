"""Run with HT_APP_DATA_DIR set to an EMPTY disposable directory; seeds no active plan."""
import os,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend/tests'))
from test_training_questionnaire import QuestionnaireTests,OPENING
root=Path(os.environ['HT_APP_DATA_DIR']);root.mkdir(parents=True,exist_ok=True);destination=root/'health_training.sqlite3'
if destination.exists():raise SystemExit('Refusing to overwrite existing database')
fixture=QuestionnaireTests();fixture.setUp()
for message in (OPENING,'Use 60 minutes','All sessions at 08:00','yes','Weekly budget cycling 480 minutes and strength 120 minutes. No restrictions. Secondary strength for cycling support. I can do 4 pull-ups and 6 dips.'):
 result=fixture.say(message)
source=sqlite3.connect(fixture.path);target=sqlite3.connect(destination);source.backup(target);target.close();source.close()
print('Disposable questionnaire ready; no saved preferences or active plan. Ask trainer: Review my 16 weeks FTP training plan.')
fixture.doCleanups()
