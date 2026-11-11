"""QA v2: rebuild a scratch DB from the EDITED 0013 and prove up/down + constraints + backfill."""
import os
import subprocess
import psycopg

BASE = "postgresql://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/postgres"
NEWDB = "yf_qa_0013_v2"
URL = "postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/" + NEWDB
DSN = URL.replace("+psycopg", "")

with psycopg.connect(BASE, autocommit=True) as c:
    c.execute("DROP DATABASE IF EXISTS " + NEWDB)
    c.execute("CREATE DATABASE " + NEWDB)
print("created", NEWDB, flush=True)

env = dict(os.environ, YF_DATABASE_URL=URL)


def run(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, cwd=os.getcwd())
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    print("$", cmd, "rc=", p.returncode, flush=True)
    print(out[-700:], flush=True)
    return p.returncode


run("alembic upgrade 0012_email_pool_lower_unique")

SEED = """
INSERT INTO accounts (id,email,first_name,last_name,zip,city,state,profile_complete,
  reviews_done,retry_count,created_at)
VALUES
 (gen_random_uuid(),$$qa.blank@example.invalid$$,$$QA$$,$$Blank$$,$$10001$$,$$   $$,$$ACTIVE$$,false,false,0,now()),
 (gen_random_uuid(),$$qa.phx@example.invalid$$,$$QA$$,$$Phx$$,$$10001$$,$$ Phoenix, AZ $$,$$ACTIVE$$,false,false,0,now());
"""
with psycopg.connect(DSN, autocommit=True) as c:
    c.execute("DELETE FROM accounts WHERE email LIKE 'qa.%'")
    c.execute(SEED)
print("seeded 2 legacy rows (blank city + padded city)", flush=True)

run("alembic upgrade head")

with psycopg.connect(DSN) as c:
    cur = c.cursor()
    cur.execute("SELECT email, city, home_city, tier, use_count, blacklisted FROM accounts WHERE email LIKE 'qa.%' ORDER BY email")
    print("BACKFILL RESULT:", flush=True)
    for r in cur.fetchall():
        print("  ", r, flush=True)

E = "$$qa.phx@example.invalid$$"
cases = [
    ("tier='Lo\u1ea1i' (m\u1ecdi theo ch\u1ea5t MINH)", "UPDATE accounts SET tier=$$Lo\u1ea1i$$ WHERE email=" + E),
    ("tier='A'", "UPDATE accounts SET tier=$$A$$ WHERE email=" + E),
    ("tier='D' (v\u1eabn ph\u1ea3i b\u1ecb ch\u1ed1n)", "UPDATE accounts SET tier=$$D$$ WHERE email=" + E),
    ("tier='Loai' (ASCII, kh\u00f4ng thu\u1ed9c enum)", "UPDATE accounts SET tier=$$Loai$$ WHERE email=" + E),
    ("tier='ABCDEF01' d\u00e0i 8 (enum ch\u1ed1n tr\u01b0\u1edbc \u0111\u1ed9 d\u00e0i)", "UPDATE accounts SET tier=$$ABCDEF01$$ WHERE email=" + E),
    ("use_count=5", "UPDATE accounts SET use_count=5 WHERE email=" + E),
    ("home_city='' (blank ph\u1ea3i b\u1ecb ch\u1ed1n)", "UPDATE accounts SET home_city=$$$$ WHERE email=" + E),
    ("home_city='  ' (whitespace-only b\u1ecb ch\u1ed1n)", "UPDATE accounts SET home_city=$$  $$ WHERE email=" + E),
    ("home_city=NULL (unknown, h\u1ee3p l\u1ec7)", "UPDATE accounts SET home_city=NULL WHERE email=" + E),
    ("friend_count=-1", "UPDATE accounts SET friend_count=-1 WHERE email=" + E),
]
print("CONSTRAINT PROBES (edit v2):", flush=True)
with psycopg.connect(DSN) as c:
    cur = c.cursor()
    for tag, sql in cases:
        try:
            cur.execute(sql)
            print("  ACCEPTED  %-40s rows=%s" % (tag, cur.rowcount), flush=True)
        except Exception as exc:
            print("  REJECTED  %-40s : %s" % (tag, str(exc).splitlines()[0][:110]), flush=True)
        c.rollback()

run("alembic downgrade 0012_email_pool_lower_unique")
with psycopg.connect(DSN) as c:
    cur = c.cursor()
    cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='accounts'")
    print("after downgrade: accounts cols =", cur.fetchone()[0], flush=True)
    cur.execute("SELECT city, home_city FROM accounts WHERE email LIKE 'qa.%'" if False else
                "SELECT email, city FROM accounts WHERE email LIKE 'qa.%' ORDER BY email")
    print("rows survive downgrade:", cur.fetchall(), flush=True)
run("alembic upgrade head")
