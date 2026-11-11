import sqlalchemy as sa
from sqlalchemy.orm import Session

BASE = 'postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/'

e = sa.create_engine(BASE + 'postgres')
with e.connect() as c:
    dbs = [r[0] for r in c.execute(sa.text('select datname from pg_database order by 1'))]
print('DBs:', dbs)
