import sys
sys.path.insert(0, 'src')
import sqlalchemy as sa
from sqlalchemy.orm import Session
from db.models import Account

e = sa.create_engine(
    'postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/yelp_factory')
print('model columns:', [c.name for c in Account.__table__.columns])
with e.connect() as c:
    print('prod alembic =', [r[0] for r in c.execute(sa.text('select version_num from alembic_version'))])
    dbcols = {r[0] for r in c.execute(sa.text(
        "select column_name from information_schema.columns where table_name='accounts'"))}
missing = [c for c in [x.name for x in Account.__table__.columns] if c not in dbcols]
print('MISSING in prod:', missing)
try:
    with Session(e) as s:
        rows = s.execute(sa.select(Account)).all()
    print('ORM select OK rows =', len(rows))
except Exception as ex:
    print('ORM select CRASH ->', type(ex).__name__, str(ex).split(chr(10))[0][:250])
