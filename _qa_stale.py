"""QA: state of existing DBs vs the EDITED 0013 (tier String(8)+'Loại', home_city not-blank)."""
import sqlalchemy as sa

BASE = 'postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/'

for db in ['yelp_factory_test']:
    e = sa.create_engine(BASE + db)
    with e.connect() as c:
        ver = [r[0] for r in c.execute(sa.text('select version_num from alembic_version'))]
        ln = c.execute(sa.text(
            "select character_maximum_length from information_schema.columns "
            "where table_name='accounts' and column_name='tier'")).scalar()
        cons = {r[0] for r in c.execute(sa.text(
            "select conname from pg_constraint where conrelid='public.accounts'::regclass"))}
        expr = None
        if 'ck_accounts_tier_enum' in cons:
            expr = c.execute(sa.text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conname='ck_accounts_tier_enum' and conrelid='public.accounts'::regclass'".replace(
                    "regclass'", "regclass"))).scalar()
        print('==', db, 'ver=', ver, '| tier max_len=', ln)
        print('   ck_accounts_home_city_not_blank present:', 'ck_accounts_home_city_not_blank' in cons)
        print('   tier constraint def:', expr)
