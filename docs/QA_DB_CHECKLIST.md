# Checklist QA: chay full suite + E-93/E-95 tren DB TEST (may QA)

> Suite chay tren **DB TEST** `yelp_factory_test` (muc 0b) — KHONG phai DB that `yelp_factory`.
> `db-check`/`backup`/`fingerprint` (muc 1, 5, 6) van tro DB that.

## 0. Moi truong (da dung san tren may QA)

- Postgres 16.6 portable: binaries `data/pg/pgsql`, cluster `data/pgdata`, port **5433**
- `.env` (gitignored) co `YF_DATABASE_URL=postgresql+psycopg://postgres:<PWD>@127.0.0.1:5433/yelp_factory`
  va `YF_MASTER_KEY` random 32 byte
  - **Password Postgres DA ROTATE (11/11)** -> `<PWD>` KHONG con la `postgres`.
    `postgres:postgres` chi con hieu la default trong code cho may moi; LAY password tu `.env`, KHONG hardcode.
- May QA khong co `.venv` -> dung `python` 3.12 he thong
- May moi / dung lai tu dau:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_pg_portable.ps1`
- Lay password Postgres tu `.env` (cho `psql`/`pg_dump`/`pg_restore` ben duoi; chay 1 lan moi shell):
  ```powershell
  $env:PGPASSWORD = [uri]::UnescapeDataString((Select-String -Path .env -Pattern '^YF_DATABASE_URL=[^:]*://[^:@]*:(.+)@').Matches[0].Groups[1].Value)
  ```

### 0b. BUOC BAT BUOC TRUOC KHI CHAY SUITE (1 lan / may, idempotent)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1
```

- Doc superuser password tu `.env` (khong in ra man hinh), tao `CREATE ROLE yf_test LOGIN PASSWORD 'yf_test'`
  + `CREATE DATABASE yelp_factory_test OWNER yf_test`, roi `db-init` schema cho DB test.
- **Non-secret + chi additive**: khong sua `.env`, khong dung DB that `yelp_factory`.
- `tests/conftest.py` `setdefault("YF_DATABASE_URL", ...)` -> suite tro toi `yelp_factory_test`,
  nen suite **khong bao gio cham DB that** (ke ca khi chay trong `repo/` co `.env` that).
- Chay lai script khi role/DB da ton tai la an toan (idempotent).
- **Chua chay script nay** -> `db_ready` **FAIL** (khong con skip im lang) => suite do la LOI MOI TRUONG, khong phai loi code.

## 1. Kiem tra DB that (khong duoc skip)

Muc nay kiem tra **DB THAT** (`yelp_factory`). Suite khong dung DB nay — suite dung **DB TEST**
`yelp_factory_test` (muc 0b). `db-check`/`db-init` khi khong override `YF_DATABASE_URL` se tro DB that.

```powershell
cd E:\Default Project\ai-team-workspace\repo
python -m cli db-check
$env:PGPASSWORD = [uri]::UnescapeDataString((Select-String -Path .env -Pattern '^YF_DATABASE_URL=[^:]*://[^:@]*:(.+)@').Matches[0].Groups[1].Value)
data\pg\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d yelp_factory -c "select version();"
```

Ky vong: `db-check` -> `"ok": true`, `drift: null`; psql ra PostgreSQL 16.6.

## 2. Full suite (chay tren DB TEST `yelp_factory_test`)

```powershell
python -m pytest tests -q
```

- **DIEU KIEN TRUOC KHI CHAY**: da chay `scripts\setup_test_db.ps1` tren may nay (muc 0b).
  `db_ready` **fail** (khong skip) khi DB test chua co => suite do la LOI MOI TRUONG, khong phai loi code.
- Bao cao dung so **thuc chay**: passed / failed / skipped + dong cuoi cua pytest.
- `skipped > 0` => KHONG duoc coi la pass (skip = DB test chua san).
- Fail thì chay lai file: `python -m pytest tests/<file> -q -x`.
- Baseline vong nghiem thu (HEAD `2a6b219`, cay khong co `.env`): **358 passed / 0 failed / 0 skipped**.
  Con so o HEAD moi hon **CHUA** ghi vao baseline cho toi khi verify doc lap tren cay khong `.env` xanh.

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

`db-check` co bat duoc index functional **bi thieu** (tra `ok:false` + `add_index
uq_email_pool_mailbox_email_lower`) **neu DB da stamp**; nhung no KHONG phan anh **dinh nghia**
index sai (cung ten, khac bieu thuc) -> van phai hoi thang Postgres:

```powershell
$env:PGPASSWORD = [uri]::UnescapeDataString((Select-String -Path .env -Pattern '^YF_DATABASE_URL=[^:]*://[^:@]*:(.+)@').Matches[0].Groups[1].Value)
data\pg\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d yelp_factory -c "select indexname, indexdef from pg_indexes where tablename='email_pool'"
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

**CANH BAO - `alembic upgrade head` KHONG chay duoc tren DB trong / DB moi.**

Chain migration chet o `0002_account_profile` voi `DuplicateColumn: column "gender" of
relation "accounts" already exists` (vi `0001_initial` tao schema theo model hien tai;
`src/cli.py` cung ghi ro: "create the current schema and stamp the head instead of
replaying the broken chain").

- May moi / DB trong: dung `python -m cli db-init` (create_all + stamp head).
- Muon chay migration THAT: phai `stamp 0011` tren DB da co schema roi moi `upgrade head`;
  KHONG bao gio chay `upgrade head` tren DB trong.
- Sua `0001` de replay duoc ca chain la quyet dinh cua @MINH/@DUC, khong tu lam tren may QA.
0. Migration da commit vao git chua (khong deploy thang tu working tree):

   ```powershell
   git ls-files migrations/versions/
   ```
   Ky vong: thay `0012_email_pool_lower_unique.py`. Neu thieu -> migration chua nam trong git,
   `upgrade` tren may khac se khong co gi de chay: commit truoc khi deploy.

1. Backup (bat buoc, phai co file dump > 0 byte):
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\backup_postgres.ps1
   ```
   File dump: `C:\pgbackup\yelp_factory_<timestamp>.dump`; script ghi them
   `env_keys_<timestamp>.txt` chi chua **ten key**, khong co gia tri - `.env` phai luu rieng.
2. Kiem tra dump phuc hoi duoc (khong tin "co file dump" la du):
   ```powershell
   $env:PGPASSWORD = [uri]::UnescapeDataString((Select-String -Path .env -Pattern '^YF_DATABASE_URL=[^:]*://[^:@]*:(.+)@').Matches[0].Groups[1].Value)
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
6. Rollback (co canh bao):
   ```powershell
   $env:PGPASSWORD = [uri]::UnescapeDataString((Select-String -Path .env -Pattern '^YF_DATABASE_URL=[^:]*://[^:@]*:(.+)@').Matches[0].Groups[1].Value)
   data\pg\pgsql\bin\pg_dump.exe -h 127.0.0.1 -p 5433 -U postgres -d yelp_factory -t email_pool -f C:\pgbackup\email_pool_before_downgrade.sql
   python -m alembic downgrade 0011
   ```
   **Khi alembic da ve `0011` thi KHONG duoc chay traffic that**: index unique da bi drop,
   app co the ghi them row case-trung, va lan `upgrade` sau se **tinh xoa am tham** cac row
   do (khong canh bao, co the mat du lieu). Rollback an toan: restore lai dump buoc 1,
   khong chi `downgrade`.
7. Neu `upgrade` bao `ForeignKeyViolation` (row case-duplicate dang bi `accounts` tro toi):
   **KHONG xoa tay** de cho qua - migration co chu dong abort va giu nguyen du lieu.
   Phai tro account sang row trung khop truoc, roi chay lai `upgrade head`.
8. Don dep DB probe: `drop database yf_restore_probe;` va `drop database yf_probe;`.

Da verify tren may QA (03:49, 10/11): `backup_postgres.ps1` chay exit 0 -> dump 53.834 byte,
152 TOC entry, Postgres 16.6; `pg_restore -l` doc; restore round-trip vao `yf_restore_probe` ra
28 table khop het, `alembic_version = 0012_email_pool_lower_unique` khop DB nguon.
Da verify them tren may QA (probe rieng cua @AN: DB `yf_p5` / `yf_p6`, khong dung DB that):
- FK-abort dung: `upgrade head` chet voi `ForeignKeyViolation`, alembic kiet `0011`, du lieu nguyen (khong xoa am tham).
- `downgrade 0012 -> 0011` chay sach (`idx_after_down = 0`), re-upgrade lap lai duoc.
- Ca "chen row case-trung o `0011` roi `upgrade`" bi gop xoa am tham -> quy tac buoc 6.

### 6b. So sanh schema hai DB bang fingerprint (khong phu thuoc alembic)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schema_fingerprint.ps1 -DbName yf_chain_probe -CompareTo yelp_factory
```

Ky vong: `DIFF: 0` va cung `Fingerprint`. Baseline schema head `0012` + 2 index moi cua `models.py`
(bo qua `alembic_version`):
`3c784299f96b1668f15df0dba505e0e87fcdc3ede8cfe3f9755173caaa11c881` (**27 bang / 54 index / 60 constraint**).
Baseline CU (schema truoc khi them `ix_accounts_batch_id` + `ix_accounts_metro`):
`be09a238c9108890997e7bfc042ad6a8c8df098f7640d8072dfc5cc82f1b4f15` (27 / 52 / 60) - chi dung cho bang cu, da cu.

Dung script nay sau khi viet lai `0001` de chung minh replay ca chain ra dung schema, va de bat cac object
khong khai bao trong `models.py` (db-check chi so model voi DB). Ket qua verify tren may QA:
- `create_all` tren DB trong vs `yelp_factory` -> `DIFF: 0` (schema model = schema head).
- drop `uq_email_pool_mailbox_email_lower` tren probe -> `DIFF: 1`, liet ke dung index bi thieu.
- `db-check` **van bat** index do bi thieu (tra `ok:false` + `add_index uq_email_pool_mailbox_email_lower`)
  mien la DB da `stamp`; DB chua stamp thi tra `ok:false` voi "Target database is not up to date".
  => `db-check` khong mu voi functional index nhu lo ngai, nhung no doi DB da stamp va no chi so voi model.

### 6c. Diem mu: `DIFF: 0` mot minh la PASS GIA - phai kiem CA 2 cong

Tieu chi nghiem thu vong viet lai `0001` (chain replay 0001 -> 0012 tren DB probe rieng):
1. `schema_fingerprint` -> `DIFF: 0` so voi `yelp_factory` (baseline `3c784299...`, 27 / 54 / 60), VA
2. `python -m cli db-check` -> `ok: true`, `drift: null` tren chinh DB chain-replay do.

`DIFF: 0` **mot minh khong du**: fingerprint chi so `TABLE/INDEX/CONSTR`; `NOT NULL` cua cot khong
phai `pg_constraint` o Postgres nen fingerprint khong thay, va kieu cot (`json` vs `jsonb`) cung khong
thay. Do do DB chain-replay ra `DIFF: 0` ma van lech voi duong `db-init` o 6 cho:
- 5 cot bi nullable trong chain, `NOT NULL` o DB QA: `assignments.created_at`,
  `browser_slots.heartbeat_at`, `clients.created_at`, `metros.created_at`, `system_flags.updated_at`;
- `warming_sessions.meta`: chain de kieu `json`, DB QA de `jsonb`.

Khi viet `0001`/`0004`/`0005`/`0006` bang `op.create_table` phai khai bao `nullable=False` cho 5 cot
do va dung `JSONB` cho `warming_sessions.meta`; chi xanh khi ca 2 cong cung dat.

Diem mu **nguoc lai** cua `db-check`: predicate cua partial index (`postgresql_where`) - no KHONG bao
khi predicate `uq_runs_one_running_per_account` doi tu `state = 'RUNNING'` sang `'DONE'`, trong khi
fingerprint bat (`DIFF: 4`). Nguoc lai, `db-check` **bat** duoc functional index cung ten nhung sai
dinh nghia (`upper(mailbox_email)` thay cho `lower(...)`).
 => Quy tac: luon chay CA `schema_fingerprint` VA `db-check`, khong tin mot cai nao mot minh.

Ghi chu 2 index moi: `ix_accounts_batch_id` + `ix_accounts_metro` da duoc them vao `models.py` (de
`db-init` / install moi khong mat index). DB QA 0 dong nen da tao them 2 index nay tren
`yelp_factory` - len DB co du lieu that van phai lam buoc 1-2 cua muc 6 (backup truoc).

## 7. Mau bao cao

```
Moi truong: <repo path>, PostgreSQL <version>, port 5433
DB: suite=yelp_factory_test | that=yelp_factory | setup_test_db.ps1 da chay: <yes/no>
Lenh: python -m pytest tests -q
Ket qua: X passed, Y failed, Z skipped trong Ns
E-93 + E-95: <pass/fail> (ky vong 9 passed)
Mailbox unique: index `uq_email_pool_mailbox_email_lower` co trong pg_indexes: <yes/no>
Rollback window: da dump rieng bang `email_pool` truoc downgrade, khong chay traffic o `0011`: <yes/no>
Fingerprint baseline: <3c784299... 27/54/60> | DIFF vs yelp_factory: <n>
db-check tren DB chain-replay: ok:<true/false> (ca 2 moi tinh la khop schema)
```
