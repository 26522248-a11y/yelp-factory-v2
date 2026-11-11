import psycopg
DSN = "postgresql://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/yf_qa_0013_scratch"
E = "$$qa.probe@example.invalid$$"
cases = [
    ("use_count=5 (spec J: max 4)", "UPDATE accounts SET use_count=5 WHERE email=" + E),
    ("use_count=-1", "UPDATE accounts SET use_count=-1 WHERE email=" + E),
    ("tier=D (ASCII, spec Loai)", "UPDATE accounts SET tier=$$D$$ WHERE email=" + E),
    ("tier=Lo (4-char ASCII would be Loai)", "UPDATE accounts SET tier=$$Lo$$ WHERE email=" + E),
    ("friend_count=-1", "UPDATE accounts SET friend_count=-1 WHERE email=" + E),
    ("valid tier=A use_count=4", "UPDATE accounts SET tier=$$A$$, use_count=4, blacklisted=true, adopted_at=now() WHERE email=" + E),
]
with psycopg.connect(DSN) as c:
    cur = c.cursor()
    cur.execute("DELETE FROM accounts WHERE email=" + E)
    cur.execute("INSERT INTO accounts (id,email,first_name,last_name,zip,city,state,profile_complete,reviews_done,retry_count) VALUES (gen_random_uuid()," + E + ", $$QA$$, $$Probe$$, $$10001$$, $$Phoenix, AZ$$, $$ACTIVE$$, false, false, 0)")
    c.commit()
    print("seeded probe row")
    for tag, sql in cases:
        try:
            cur.execute(sql)
            print("  ACCEPTED   %-34s rows=%s" % (tag, cur.rowcount))
        except Exception as exc:
            print("  REJECTED   %-34s : %s" % (tag, str(exc).splitlines()[0]))
        c.rollback()
    cur.execute("UPDATE accounts SET tier=$$A$$, use_count=4, blacklisted=true, adopted_at=now() WHERE email=" + E)
    c.commit()
    cur.execute("SELECT email, city, home_city, tier, use_count, blacklisted FROM accounts WHERE email=" + E)
    print("final row:", cur.fetchone())
