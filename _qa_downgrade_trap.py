"""QA: does the NEW 0013.downgrade() run on a DB that was built with the OLD 0013 body?"""
import os
import subprocess
import psycopg

DB = "yf_qa_0013_scratch"
URL = "postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/" + DB
DSN = URL.replace("+psycopg", "")

with psycopg.connect(DSN) as c:
    cur = c.cursor()
    cur.execute("select version_num from alembic_version")
    print("stamped at:", cur.fetchall(), flush=True)
    cur.execute("select conname from pg_constraint where conrelid='public.accounts'::regclass order by 1")
    print("check constraints in DB:", [r[0] for r in cur.fetchall() if r[0].startswith('ck_')], flush=True)
    cur.execute("select character_maximum_length from information_schema.columns where table_name='accounts' and column_name='tier'")
    print("tier len in DB:", cur.fetchone()[0], flush=True)

env = dict(os.environ, YF_DATABASE_URL=URL)
p = subprocess.run("alembic downgrade 0012_email_pool_lower_unique", shell=True,
                   capture_output=True, text=True, env=env, cwd=os.getcwd())
print("downgrade rc=", p.returncode, flush=True)
print(((p.stdout or "") + (p.stderr or "")).strip()[-900:], flush=True)
