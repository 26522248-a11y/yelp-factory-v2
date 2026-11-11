import sqlalchemy as sa

BASE = 'postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/'
LIFECOL = ['supplier', 'home_city', 'city_changed_at', 'use_count', 'tier',
           'friend_count', 'tip_count', 'checkin_count', 'blacklisted', 'adopted_at']

for db in ['yelp_factory', 'yelp_factory_test']:
    e = sa.create_engine(BASE + db)
    with e.connect() as c:
        try:
            rows = [r[0] for r in c.execute(sa.text('select version_num from alembic_version'))]
        except Exception as ex:
            rows = 'ERR:' + str(ex)[:80]
        try:
            cols = {r[0] for r in c.execute(sa.text(
                "select column_name from information_schema.columns "
                "where table_name='accounts' and table_schema='public'"))}
        except Exception as ex:
            cols = set()
            print(db, 'cols ERR', str(ex)[:80])
        present = [k for k in LIFECOL if k in cols]
        tier_def = None
        if 'tier' in cols:
            tier_def = c.execute(sa.text(
                "select character_maximum_length from information_schema.columns "
                "where table_name='accounts' and column_name='tier'")).scalar()
        nacc = None
        try:
            nacc = c.execute(sa.text('select count(*) from accounts')).scalar()
        except Exception as ex:
            nacc = 'ERR'
        cons = [r[0] for r in c.execute(sa.text(
            "select conname from pg_constraint where conrelid = 'public.accounts'::regclass"))] \
            if cols else []
        print('DB', db)
        print('  alembic_version =', rows)
        print('  accounts rows =', nacc, '| n cols =', len(cols))
        print('  lifecycle cols present =', present)
        print('  tier max_len =', tier_def)
        print('  tier/check constraints =', [x for x in cons if 'tier' in x or 'ck_' in x])
