# Checklist QA: chay full suite + E-93 tren DB that (may QA)

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

## 3. E-93 (trust reachable)

```powershell
python -m pytest tests/cases/E-93_trust_reachable.py -q -s
```

Ky vong: pass, gia tri trust >= 75, va seed `mode="warm"` (khong seed san `post_review`).

## 4. Mau bao cao

```
Moi truong: <repo path>, PostgreSQL <version>, port 5433
Lenh: python -m pytest tests -q
Ket qua: X passed, Y failed, Z skipped trong Ns
E-93: <pass/fail> (trust thuc te)
```