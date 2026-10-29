import os,psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine,text
from app.db.session import sqlalchemy_url
from app.core.config import get_settings
cfg=Config("alembic.ini")
assert ScriptDirectory.from_config(cfg).get_heads()==["0031_contact_erasure"]
for name,steps in [
 ("saas_empty_test",[("upgrade","head"),("check",None)]),
 ("saas_0022_test",[("upgrade","0022_knowledge_hygiene"),("upgrade","head"),("check",None)]),
 ("saas_rehearsal_test",[("upgrade","head"),("downgrade","0022_knowledge_hygiene"),("downgrade","base"),("upgrade","head"),("check",None)])
]:
 with psycopg.connect(os.environ["TEST_DATABASE_URL"],autocommit=True) as c:
  c.execute(f'CREATE DATABASE "{name}"')
 url=f"postgresql://postgres@127.0.0.1:55587/{name}"
 os.environ["DATABASE_URL"]=url
 get_settings.cache_clear()
 cfg.set_main_option("sqlalchemy.url",sqlalchemy_url(url))
 with create_engine(sqlalchemy_url(url)).connect() as c:
  assert c.scalar(text("select current_database()"))==name
 print(f"DB host=127.0.0.1:55587 database={name}",flush=True)
 for action,target in steps:
  print(action,target,flush=True)
  if target is None: getattr(command,action)(cfg)
  else: getattr(command,action)(cfg,target)
 print(name,"PASS",flush=True)
