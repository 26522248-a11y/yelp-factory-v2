"""QA: prove the STALE test DB rejects what the edited model/migration now allows.

All writes happen in ONE transaction that is ROLLED BACK - nothing is committed,
so the shared suite DB (yf_test role) is left byte-identical.
"""
import psycopg

DSN = "postgresql://yf_test:yf_test@127.0.0.1:5433/yelp_factory_test"
E = "$$qa.tier@example.invalid$$"
with psycopg.connect(DSN) as c:          # autocommit OFF -> everything rolls back on close
    cur = c.cursor()
    cur.execute(
        "INSERT INTO accounts (id,email,first_name,last_name,zip,city,state,profile_complete,"
        "reviews_done,retry_count) VALUES (gen_random_uuid()," + E +
        ", $$QA$$, $$Tier$$, $$10001$$, $$Phoenix, AZ$$, $$ACTIVE$$, false, false, 0)")
    for tag, sql in [
        ("tier='Lo\u1ea1i' (enum m\u1edbi cho ph\u00e9p)", "UPDATE accounts SET tier=$$Lo\u1ea1i$$ WHERE email=" + E),
        ("tier='ABCDEFGH' d\u00e0i 8 (String(8) m\u1edbi)", "UPDATE accounts SET tier=$$ABCDEFGH$$ WHERE email=" + E),
        ("home_city='' (constraint m\u1edbi ch\u1ed1n)", "UPDATE accounts SET home_city=$$$$ WHERE email=" + E),
    ]:
        try:
            cur.execute(sql)
            print("  ACCEPTED  %-42s" % tag, flush=True)
        except Exception as exc:
            print("  REJECTED  %-42s : %s" % (tag, str(exc).splitlines()[0][:130]), flush=True)
        c.rollback()   # drop the failed statement AND the seed insert
    cur.execute("SELECT count(*) FROM accounts WHERE email=" + E)
    print("probe rows left after rollback:", cur.fetchone()[0], flush=True)
    c.commit()
