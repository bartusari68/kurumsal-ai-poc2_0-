from pathlib import Path
import os, sqlite3, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
source=ROOT/'tmp/e2e-20260907-084313/validation.db'
folder=ROOT/'tmp/experience-preview'
folder.mkdir(exist_ok=True)
target=folder/'preview.db'
if not target.exists():
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target) as new:
        old.backup(new)
os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
os.environ['PDF_DIR']=str(source.parent/'pdfs')
from app import portal_auth
# Browser cookies are host-scoped, not port-scoped: isolate preview sign-in too.
portal_auth.COOKIE='learning_experience_preview_session'
from app.main import app
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=8011)
