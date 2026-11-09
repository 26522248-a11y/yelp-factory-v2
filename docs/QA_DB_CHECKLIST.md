# Checklist QA: chay full suite + E-93/E-95 tren DB that (may QA)

## 0. Moi truong (da dung san tren may QA)

- Postgres 16.6 portable: binaries `data/pg/pgsql`, cluster `data/pgdata`, port **5433**
- `.env` da co `YF_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/yelp_factory`
  va `YF_MASTER_KEY` random 32 byte
- May QA khong co `.venv` -> dung `python` 3.12 he thong
- May moi / dung lai tu dau:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_pg_portable.ps1`

## 1. Kiem tra DB that (khong duoc skip)

```powershell
cd E:\Default Project\ai-team-workspace\repo
python -m cli db-check
data\pg\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d yelp_factory -c "select version();"
```

Ky vong: `db-check` -> `"ok": true`, `drift: null`; psql ra PostgreSQL 16.6.

## 2. Full suite

```powershell
python -m pytest tests -q
```

- Bao cao dung so **thuc chay**: passed / failed / skipped + dong cuoi cua pytest.
- `skipped > 0` => KHONG duoc coi la pass (skip = DB chua that).
- Fail thì chay lai file: `python -m pytest tests/<file> -q -x`.
- Baseline vong nghiem thu trust (HEAD `daff69d`): **327 passed / 0 failed / 0 skipped**.

## 3. E-93 (trust reachable)

```powershell
python -m pytest tests/cases/E-93_trust_reachable.py -q -s
```

Ky vong: pass, gia tri trust >= 75, va seed `mode="warm"` (khong seed san `post_review`).

## 4. E-95 (warm gate counting)

```powershell
python -m pytest tests/cases/E-95_warm_gate_counting.py -q -s
```

Ky vong: **6 passed**, khong con xfail (xfail = gate chua khep kin).

Chay chung E-93 + E-95 (dung cho lan chay xac nhan):

```powershell
python -m pytest tests/cases/E-93_trust_reachable.py tests/cases/E-95_warm_gate_counting.py -q
```

Ky vong: **9 passed** (E-93 3 + E-95 6).

Pham vi ma E-95 khoa (acc chi co session `mode="warm"`):
- `session_count()` > 0 va `sessions_today()` >= 1 (khong con = 0 nhu truoc khi sua).
- Unlock ladder vuot P0 (vd `[P0,P1,P2,P4]`), khong chỉ `P0`.
- Row `meta.seed` va `mode` la khong duoc tinh vao `trust` / `session_count` / `sessions_today` / `days_active`.
- Session `warm` trong ngay -> `run_post_review_warm` tra `SKIPPED_TODAY` (cap 1 phien/ngay tinh ca warm).

## 5. Mailbox unique (case-insensitive) - kiem tra index that

`db-check` KHONG chung minh duoc index bieu thuc `lower(mailbox_email)` ton tai
(alembic autogenerate khong doc functional index - blind spot), nen phai hoi thang Postgres:

```powershell
set PGPASSWORD=postgres&& data\pg\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d yelp_factory -c "select indexname, indexdef from pg_indexes where tablename='email_pool'"
```

Ky vong thay `uq_email_pool_mailbox_email_lower` voi `UNIQUE ... (lower((mailbox_email)::text))`.
Da co test `tests/unit/test_pool_email_unique.py::test_lower_unique_index_exists_in_database`
assert dung dieu nay, chay: `python -m pytest tests/unit/test_pool_email_unique.py -q` -> **5 passed**.

Luu y migration `0012`: QA DB duoc dung bang `create_all` + `stamp head` nen phan DELETE gop
case-duplicate cua `0012` chua tung chay that. Muon test migration: dung mot DB probe rieng
(`createdb yf_probe`), `stamp 0011`, chen 2 row duplicate khac hoa/thuong, roi `upgrade head`.
**Tren DB co du lieu that: chay `scripts\backup_postgres.ps1` lay dump TRUOC khi upgrade** (0012 co DELETE).

## 6. Mau bao cao

```
Moi truong: <repo path>, PostgreSQL <version>, port 5433
Lenh: python -m pytest tests -q
Ket qua: X passed, Y failed, Z skipped trong Ns
E-93 + E-95: <pass/fail> (ky vong 9 passed)
Mailbox unique: index `uq_email_pool_mailbox_email_lower` co trong pg_indexes: <yes/no>
```
