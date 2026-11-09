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
- Unlock ladder vuot P0 (vd `[P0,P1,P2,P4]`), khong chi `P0`.
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

## 6. Trien khai migration len DB co du lieu that (quy tac, khong bo qua buoc nao)

Migration co `DELETE` (vd `0012` gop case-duplicate) thi phai theo dung thu tu sau.
**Backup ma khong restore lai duoc thi chua co gi.**

1. Backup (bat buoc, phai co file dump > 0 byte):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1
   ```
   File dump: `C:\pgbackup\yelp_factory_<timestamp>.dump`; script ghi them
   `env_keys_<timestamp>.txt` chi chua **ten key**, khong co gia tri - `.env` phai luu rieng.
2. Kiem tra dump phuc hoi duoc (khong tin "co file dump" la du):
   ```powershell
   set PGPASSWORD=postgres
   data\pg\pgsql\bin\createdb.exe -h 127.0.0.1 -p 5433 -U postgres yf_restore_probe
   data\pg\pgsql\bin\pg_restore.exe -h 127.0.0.1 -p 5433 -U postgres -d yf_restore_probe (Get-ChildItem C:\pgbackup\yelp_factory_*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
   data\pg\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d yf_restore_probe -tAc "select count(*) from information_schema.tables where table_schema='public'"
   ```
   Ky vong: so bang bang voi DB nguon (QA hien tai: **28** bang), va
   `select version_num from alembic_version` trong DB vua restore khop DB nguon.
3. Dry-run migration tren DB probe (KHONG dung DB that): `createdb yf_probe` -> `stamp 0011` ->
   `upgrade head` -> kiem tra `pg_indexes` co `uq_email_pool_mailbox_email_lower`.
4. Upgrade DB that: `python -m alembic upgrade head`.
5. Sau upgrade: `python -m cli db-check` -> `ok: true`, `drift: null`; `pg_indexes` -> co index lower-unique.
6. Rollback: `python -m alembic downgrade 0011`, hoac restore lai tu dump buoc 1.
7. Don dep DB probe: `drop database yf_restore_probe;` va `drop database yf_probe;`.

Da verify tren may QA (03:49, 10/11): `backup_postgres.ps1` chay exit 0 -> dump 53.834 byte,
152 TOC entry, Postgres 16.6; `pg_restore -l` doc; restore round-trip vao `yf_restore_probe` ra
28 table khop het, `alembic_version = 0012_email_pool_lower_unique` khop DB nguon.

## 7. Mau bao cao

```
Moi truong: <repo path>, PostgreSQL <version>, port 5433
Lenh: python -m pytest tests -q
Ket qua: X passed, Y failed, Z skipped trong Ns
E-93 + E-95: <pass/fail> (ky vong 9 passed)
Mailbox unique: index `uq_email_pool_mailbox_email_lower` co trong pg_indexes: <yes/no>
```
