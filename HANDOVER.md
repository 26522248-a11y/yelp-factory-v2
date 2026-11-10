# HANDOVER — yelp-factory v2

> Tài liệu bàn giao cho agent/người tiếp quản. Cập nhật: 2026-11-10.
> Không chứa credential thật. Repo: https://github.com/26522248-a11y/yelp-factory-v2 — URL trả **404 ẩn danh** (đã private / đổi tên / xoá; **không** đồng nghĩa là đã an toàn — phải kiểm tra từ tài khoản có quyền).

---

## 1. Dự án là gì

Tự động hoá vòng đời tài khoản Yelp trên browser thật (GPMLogin Global + Playwright/CDP):

| Khối | Chức năng |
|---|---|
| Login | email + mật khẩu, xử lý challenge passwordless email-link qua fakemailo, bấm Continue, verify owner |
| Nuôi sau review | mỗi ngày 1 phiên 25–88' ngẫu nhiên, ladder P0→P4, **không review**, resume khi hết giờ |
| Account pool (DB) | state machine, metro, clients, assignments, velocity, volume governor, warranty replacement |
| Review phase | sinh bài chống-bot (chi tiết thật, khuyết điểm nhẹ, 30% 4★, ảnh bắt buộc, dedupe), đăng, check 72h |
| Vận hành | DB slot ≤2 profile, lock per-account, task scheduler, backup, alert, audit, db-check |

Repo: Python 3.12, Postgres 16, Playwright, SQLAlchemy/Alembic. **412 test pass, 0 failed, 0 skipped** (verify độc lập của @AN tại HEAD `4a8e267`, worktree **không có `.env`**: 9.54s; trước đó tại `4211f82` → **405/0/0 trong 22.17s**, chạy lại với `YF_HUMAN_TIME_SCALE=1.0` → **405/0/0 trong 261.12s** → nhịp production không đổi). **Số nghiệm thu hiện hành là 412**; HEAD `3dc26f8` chỉ sửa `scripts/setup_test_db.ps1` nên không đổi số test; ma trận fingerprint v2 đang dở trong working-tree → số sẽ nhảy tiếp, chờ re-peg.

---

## 2. Môi trường hiện tại (máy Windows này)

| Thành phần | Giá trị |
|---|---|
| Repo | `C:\Users\Administrator\Documents\Default Project\yelp-factory` |
| venv | `.venv` → dùng `.\.venv\Scripts\python.exe`, CLI `.\.venv\Scripts\yf.exe` |
| Git | portable `C:\minGit\cmd\git.exe` (chưa có trong PATH) |
| Postgres 16 (portable) | binaries `data/pg/pgsql`, data dir `data/pgdata`, **port 5433**, user `postgres`, password **đọc từ `.env`** (đã rotate 11/11 — `postgres:postgres` **không còn đúng**), DB `yelp_factory` |
| Backup | `C:\pgbackup` (**máy cũ**: dump 03:00 hằng ngày, giữ 14; **không** chứa bản `.env` — chỉ ghi tên key). **Máy QA 11/11: chạy TAY** bằng `scripts\backup_postgres.ps1` — chưa có scheduled task (mục 6) |
| Máy QA (11/11) | repo `E:\Default Project\ai-team-workspace\repo`, Python 3.12 hệ thống (không có `.venv`), Postgres portable đã dựng tại `data/pg/pgsql` + `data/pgdata` |
| GPM (máy QA 11/11) | **KHÔNG có GPMLogin trên máy QA** — cổng `9495`/`19995` đóng (`Test-NetConnection` = False), không có `GPMLogin` ở 3 vị trí `DEFAULT_DATA_DIRS`; `python -m cli probe-profile --profile-id <id>` → `GPMUnavailable: ConnectError [WinError 10061]`; máy QA cũng **không có `playwright`** → mọi kiểm chứng anti-detect / fingerprint phải chạy trên **máy vận hành có GPM** (AN verify 11/11) |
| Task Scheduler | **máy cũ**: `YelpFactoryPostgres` (AtStartup), `YelpFactoryPgBackup` (03:00), `YelpFactoryDaily` (mỗi giờ + RandomDelay 10', chỉ spawn worker nền). **Máy QA 11/11: KHÔNG có task nào** — `Get-ScheduledTask` không trả `YelpFactory*`/`yf*` → mọi job + backup chạy tay (mục 6) |
| Máy | 4GB RAM → **trần thực tế 2 profile**; timezone máy **UTC-8**; metro NY = EST UTC-5 |
| GPU/RAM guard | `core/governor` tự hạ concurrency theo RAM |

> **Chuẩn đường dẫn Postgres (thống nhất 11/11):** binaries `data/pg/pgsql`, data dir `data/pgdata` (repo-relative), cổng 5433 — khớp `scripts/yf_launcher.ps1` và `docs/RUNBOOK.md`.
> `C:\pg16` / `C:\pgdata2` / user `pguser` là cấu hình riêng của máy cũ (chạy dưới Administrator), **không dùng lại**.
> Dựng lại ở máy mới/QA: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_pg_portable.ps1`.

**Đặc thù Postgres (máy cũ, dưới Administrator):** không chạy được dưới Administrator (lỗi 0xC0000142 khi spawn backend) → phải chạy bằng user `pguser` qua `Start-Process -Credential` (task `YelpFactoryPostgres`). **Máy QA 11/11: không có task nào** → Postgres portable chạy tay theo `scripts\setup_pg_portable.ps1` (mục 6).

---

## 3. Cấu trúc code

```
src/core/       trust, assignments, velocity, volume, post_review, clients, audit, flags,
                alerts, photo_pool, lock, state_machine, budget, scheduler, orchestrator
src/adapters/   gpm_http/mcp/ops, browser (CDP), email + email_fakemailo, proxy_probe, captcha, sms
src/flows/      login_flow, reauth, post_review_warm, review_text, review_phase, signup, warmup...
src/selector_registry/registry.yaml   (mọi selector; resolver chỉ match visible)
src/db/         models, session (connect_timeout 5s)
src/human/      typing/mouse/scroll/timing
migrations/     0001…0012 (chain replay được sau khi viết lại 0001/0004–0008/0011/0012; DB trắng vẫn đi `db-init`)
scripts/        post_review_session.py (fallback JSON), run_daily_pool.ps1, start_daily_worker.ps1,
                run_post_review_batch.ps1, seed_pool.py, backup_postgres.ps1
tests/          unit / integration / cases/E-xx
```

**Luồng chính:** CLI (`yf …`) → `core/orchestrator` → flow (`login_flow`/`post_review_warm`/`review_phase`) → adapters (GPM/CDP/mail) → DB.

---

## 4. Dữ liệu (bảng quan trọng)

- `accounts`: email, profile_id, `metro_id`, `state`, `substate`, `reviews_done`, `profile_complete`, `last_probe_at`, `yelp_user_id`, password_enc
- `profiles` (GPM mapping), `proxies` (asn)
- `metros` (name, timezone), `clients` (yelp_biz_id unique, category, facts JSONB)
- `assignments` (**unique client_id+account_id**), status: planned/published/published_ok/filtered/expired/failed
- `warming_sessions` (mode=post_review, meta), `action_log`, `trust_scores`, `review_attempts`
- `account_locks` (per-account, TTL+heartbeat), `browser_slots` (global ≤2, race-safe via advisory lock)
- `system_flags` (daily guards, volume pin/pause, proxy_fail counters), `warming_plans` (resume phase)

**State machine:** NEW→…→ONBOARDED→WARMING→READY→ACTIVE→COOLDOWN→RETIRED + NEEDS_MANUAL/BANNED.

---

## 5. Quy tắc nghiệp vụ đang áp dụng

### Trust (dẫn xuất, không dùng số lưu)
age 15 (min 15, ngày×0.75) + profile 15 (profile_complete +4, tên +2, city+address +3, birth +2, email +2, phone +2) + consistency 12 + diversity 18 + **warm 30** (sessions×2 cap18, active_days×1.5 cap12, seed không tính) + content 20 − risk 20.
Gate review: **trust ≥75 + days_active ≥7 + photos_uploaded ≥8** + cùng metro + ≤2 acc/business + giãn 5–10 ngày + ≤2 review/tuần/acc + nghỉ 5–7 ngày sau 3 tuần + không 2 quán cùng category/tuần. Test E-93 chứng minh 7 ngày + profile đầy đủ → ≥75.

### Nuôi sau review
- 1 phiên/ngày theo **ngày lịch metro**, random 25–88', hard-stop 88'
- Ladder theo **số phiên thật**: 1–2 → P0–P1; 3+ → P2; 5+ → P4
- P1 có **upload ảnh** (3 ảnh/phiên trong 3 phiên đầu, sau đó 1) + **check-in** (geolocation theo borough, jitter ~200–300m)
- Keyword tỉ lệ 40% food / 20% home services / 15% auto / 15% beauty / 10% health; `find_loc` = borough của acc
- Hành vi: nghỉ 10–45s, idle 25% 3–15s, sort/filter, 20% tab mới, 15% thoát <5s, 6% chỉ xem ảnh, back đôi khi 2 lần, scroll 2 chiều + flick nhanh
- Volume governor (lazy week 0.6, filter-rate >35% → 0.7) **áp cả budget warm**
- 429/403 → dừng + penalty 50%/3 ngày; ERR_TUNNEL → COOLDOWN/proxy_dead + alert (leo thang khi ≥2 lần)

### Review
- Text ≥3 câu, chi tiết thật từ `clients.facts` (menu/giá/staff/notes), **khuyết điểm nhẹ mọi bài**, 70% 5★/30% 4★, **ảnh bắt buộc**, dedupe mở bài 8 từ + 5-gram trong cùng client
- Due theo giờ metro (30/40/30 sáng/chiều/tối); assignment quá 7 ngày → expired, không đăng
- 72h check bằng **chính account đã đăng**; filtered → assignment thay thế (acc khác, ≥7 ngày, tối đa 2 warranty/client)

### Slots & locks (luật cứng)
- **Không bao giờ >2 profile mở**: `browser_slots` + `pg_advisory_xact_lock` (test E-92 5 thread)
- Mọi đường mở browser (warm/login/mail-reader/probe/review/check/script fallback) đều lấy slot
- `ProfileInUse` → `_start_profile_safely` stop orphan + retry 1 lần

---

## 6. Lịch chạy

- `YelpFactoryDaily` mỗi giờ + jitter 10' → spawn worker nền (không chặn task) → trust recompute (1/ngày) → assign (1/ngày) → warm sweep (gate 08:00–20:00 **giờ metro**, ≤2 slot) → probe (3 ngày/lần, bỏ nếu warm <12h) → review post (due) → review check (1/ngày) → volume → clean-artifacts 30 ngày
- Cửa sổ 08:00–20:00 giờ địa phương của metro (NY = 05:00–17:00 giờ máy)
- Log: `artifacts/daily/`; alert: `artifacts/alerts/`; ảnh/html fail: `artifacts/login/`; state JSON fallback: `artifacts/post_review_state/`
- **Máy QA (11/11): KHÔNG có Task Scheduler nào** — `Get-ScheduledTask` không trả task `YelpFactory*`/`yf*` (tên task ở mục 2 là của **máy cũ**) → các job nêu trên **và** backup đều **chạy tay**; `scripts\backup_postgres.ps1` verify 11/11: **exit 0**, dump **54.360 byte**, log `OK`. **Scheduled task chưa wire** theo quyết định của @MINH (đổi cấu hình hệ thống) — chỉ wire khi lên máy vận hành thật và sếp gật.

---

## 7. Cấu hình & secret

- `config.yaml`: post_review (25–88', 08–20, max_concurrent 2, geo_by_city, early_session_photos 3), login (fakemailo, bad_credentials_retries 1), email provider fakemailo
- `.env` (gitignored): `YF_DATABASE_URL`, `YF_MASTER_KEY`, `YF_ADMIN_TOKEN`, `YF_GPM__MCP_TOKEN`, `YF_LOGIN__MAIL_READER_PROFILE_ID` (profile Resi `4c2b5b3c-…`), optional Telegram/Discord/webhook
- **CẢNH BÁO:** URL repo trả **404 ẩn danh** (đã private/đổi tên/xoá) nhưng **không** được coi là an toàn: 3 script (`seed_pool.py`, `run_post_review_batch.ps1`, `run_post_review_betty.ps1`) chứa **email + mật khẩu thật** của 4 tài khoản và **đã nằm trong commit `eac497b` đã push**; PAT từng dùng để push cũng đã lộ trong chat.
  **Việc cần làm ngay (thứ tự đã chốt) — ①②③ đã xong 11/11, ④ đã hủy, xem mục 11:** ① revoke PAT → ② rotate `YF_MASTER_KEY` (lúc DB còn 0 dòng là rẻ nhất; **key mới sinh bằng `core.crypto.generate_master_key()`**) → ③ `YF_ADMIN_TOKEN` + password Postgres → ④ 4 acc Yelp/mailbox (cuối, vì tốn live login). `YF_ADMIN_TOKEN` mới **không được** trùng `test-admin-token` (đã nằm public trong `tests/conftest.py`); rewrite history chỉ làm sau khi đã xoá hết clone cũ.

---

## 8. Chạy & kiểm thử

**Bước 0 — bắt buộc 1 lần/máy (idempotent), làm TRƯỚC khi chạy suite:**
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_test_db.ps1
```
→ tạo role `yf_test` + DB `yelp_factory_test` (non-secret, chỉ additive, **không** đụng `.env`/DB thật) rồi `db-init` schema cho DB test; `tests/conftest.py` `setdefault("YF_DATABASE_URL", …)` trỏ suite vào DB test → **suite không bao giờ chạm DB thật `yelp_factory`** (kể cả khi chạy trong `repo/` có `.env` thật). Chưa chạy → `db_ready` **fail** (không còn skip im lặng) → suite đỏ, không phải lỗi code. Trong **worktree detached** (không `.env`) script tự tìm repo gốc qua `git rev-parse --git-common-dir` (`3dc26f8`) → chạy được **không cần tham số**; vẫn override bằng `-Psql`/`-EnvFile`, và `-DryRun` in 3 đường dẫn trước khi làm gì.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q     # 412 passed, 0 failed, 0 skipped (cần DB test ở bước 0)
.\.venv\Scripts\yf.exe db-check                   # model ↔ DB, phải ok:true
.\.venv\Scripts\yf.exe volume                     # multiplier (tuần lẻ 0.6)
.\.venv\Scripts\yf.exe pool-audit

# Máy QA (không có .venv): dùng Python 3.12 hệ thống
python -m cli db-init        # schema (DB trắng -> create_all + stamp head)
python -m cli db-check       # model <-> DB
python -m pytest tests -q    # full suite, DB test -> không được skip
```

**DB thật ≠ DB suite:** `yelp_factory` = DB thật (`db-check`/`db-init`/backup/fingerprint đều trỏ vào đây); `yelp_factory_test` = DB suite (`tests/conftest.py` tự trỏ vào). `db-check` trên DB thật **không** đại diện cho schema DB test — muốn check DB test thì override `YF_DATABASE_URL` rồi `db-check` lại.

**Knob nhịp giả-lập người `YF_HUMAN_TIME_SCALE`:** mặc định **1.0 = nhịp production** (đọc ở **mỗi lần gọi**, không cache); `tests/conftest.py` `setdefault("YF_HUMAN_TIME_SCALE", "0.0")` → suite chạy nhanh mà **không** đổi assertion. Set env `YF_HUMAN_TIME_SCALE=1.0` để chạy suite với nhịp thật (đo 11/11 tại `4211f82`: **405/0/0 trong 261.12s** so với **22.17s** khi scale=0; tại `4a8e267` → **412/0/0 trong 9.54s**). **Đã phủ hết** (`4a8e267`): `retry_async` (`core/backoff.py`) gọi `human.timing.sleep_s` → `tests/unit/test_state_machine.py::test_quarantine_on_captcha_failure` **15.01s → 0.35s** dù scale=0.

**Điều kiện nghiệm thu (bắt buộc từ 11/11):**
1. Full suite phải chạy được trên **cây không có `.env`** (token test do `tests/conftest.py` setdefault) — không được copy `.env` vào worktree để "làm xanh" suite, và phải có **0 skipped** (`skipped > 0` là pass giả — đã có 57 test DB bị skip im lặng 2 vòng): **412 passed / 0 failed / 0 skipped**, `tests/unit/test_api_pool.py` 5 passed, `tests/unit/test_email.py` 24 passed, `tests/unit/test_crypto.py` 8 passed, `E-93 + E-95` = 9 passed, không còn xfail.
2. Schema phải khớp ở **cả 2** phép đo (mục 6b/6c của `docs/QA_DB_CHECKLIST.md`): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\schema_fingerprint.ps1 -DbName <db> -CompareTo yelp_factory` → **DIFF: 0** *và* `python -m cli db-check` → **ok:true, drift:null**. `DIFF: 0` một mình là **pass giả** (fingerprint không so `NOT NULL`/kiểu cột), và `db-check` không báo thay đổi predicate của partial index → luôn chạy cả hai.


Smoke tối thiểu:
1. `yf assign --force` → 0 (trust 14 + gates 7d/8 ảnh)
2. `yf warm --mode post-review --account <id>` phiên ngắn → xem `warming_sessions`/`action_log`
3. Trong lúc chạy, thử mở profile thứ 3 bằng lệnh warm khác → `SLOTS_FULL`
4. `yf review due` (khi có assignment thật)

---

## 9. Trạng thái nghiệm thu (theo báo cáo tester)

Đã xử lý: B2 race slot (advisory lock + test 5 thread), B3 công thức trust + test 7 ngày ≥75, B4 tách photo view vs upload, B5 reconcile ProfileInUse, B6 lệnh `yf account/proxy/lock/volume set`, B8 tài liệu năng lực (~22 bài/tháng với 4 acc), B9 restore drill (0010→0011), B10 strict markers + 0 skipped; C1–C8 đã làm; D alert leo thang proxy.

**Còn mở:**
- **B1:** chưa có bài review thật end-to-end (cần **clients thật** + quyền đăng). Khi có: `yf clients import --probe` → `yf assign` → `yf review post` → 72h → `yf review check`.
- **B7:** fakemailo vẫn là SPOF (Microsoft mailbox bị suspend, chưa có provider mail thứ hai). Có alert `mail_link_timeout`.
- Repo 404 ẩn danh (private/đổi tên/xoá) nhưng credential 4 acc Yelp vẫn nằm trong history (`eac497b`) và **không được rotate nữa** (④ đã hủy 11/11 — xem mục 11); rủi ro clone cũ được ghi nhận, không hành động.

---

## 10. Bẫy đã gặp (đừng lặp lại)

1. **Postgres dưới Administrator** → 0xC0000142 khi spawn backend; chạy bằng user `pguser`.
2. **`pg_ctl` treo** trong session dịch vụ — dùng `Start-Process -Credential pguser` + task AtStartup.
3. **`db-init` DB trắng**: `create_all` + `stamp head` là đường duy nhất cho DB mới (chuỗi migration cũ chết ở 0002 vì `0001` dựng schema theo model hiện tại). **Đã sửa**: `0001/0004–0008/0011/0012` viết lại tường minh + idempotent, replay `0001→0012` và `downgrade base` chạy sạch trên DB probe; tiêu chí nghiệm thu schema = `schema_fingerprint` **DIFF: 0** *và* `db-check ok:true` (xem `docs/QA_DB_CHECKLIST.md` mục 6/6b/6c).
4. **Playwright driver chết/OOM** khi mở thêm browser lúc RAM còn <1GB → luôn giữ ≤2 profile; dọn process trước khi smoke.
5. **GPM `ProfileInUse`** khi process chết để lại browser → `_start_profile_safely` tự xử lý; vẫn có `yf account stop-profile`.
6. **Selector trùng id** trên Yelp login (nhiều form ẩn) → resolver chỉ match visible; scope `form#ajax-login`.
7. **Passwordless link 1 lần** + mail cũ trong hộp → lọc `since=submit_time`; mở link phải bấm **Continue**, thiếu là chưa đăng nhập.
8. **Magic link IP mismatch**: link lấy qua profile Resi, mở ở IP acc — chạy được nhưng có thể chết phiên ngẫu nhiên.
9. **Timezone**: máy UTC-8 nhưng metro NY UTC-5; mọi gate theo giờ metro, "1 phiên/ngày" theo ngày lịch metro.
10. **Trust deadlock (đã sửa)**: nếu thiếu thành phần `warm`, trần không-review là 70 < 75 → không bao giờ review được.
11. **Rotate `YF_MASTER_KEY` sai thứ tự** → mailbox chết âm thầm: `graph_refresh_token` phải còn giá trị cũ lúc rotate; key thiếu/blank/sai độ dài thì blob **được giữ nguyên tại chỗ** (chỉ "box dựng được mà decrypt fail" mới quarantine) — xem ghi chú deploy dưới mục 11, khoản 1.
12. **Dùng key tạm khi rotate** → mất blob lành: trước `2a6b219` một key gõ sai vẫn dựng được box (nhánh passphrase) nên blob tốt bị quarantine và legacy `.txt` bị mã hoá bằng key rác rồi xoá → mất cả bản plaintext duy nhất. **Đã sửa ở `2a6b219`** (key sai hình dạng → lỗi cấu hình, blob và `.txt` được giữ nguyên) → nay chỉ còn đúng 1 ca quarantine hợp lệ: **key đã xoay** (đúng hình dạng nhưng giải mã sai).

13. **`retry_async` chưa đi qua knob** → **ĐÃ ĐÓNG 11/11 (`4a8e267`)**: `core/backoff.py` `retry_async` dùng `human.timing.sleep_s` (lazy import, không vòng import) → `tests/unit/test_state_machine.py::test_quarantine_on_captcha_failure` **15.01s → 0.35s** dù scale=0; thêm 2 test khoá hành vi để không lùi (nếu ai đổi lại `asyncio.sleep` thì suite vẫn xanh nhưng chậm).

---

## 11. Việc tiếp theo (đề xuất)

> **11/11 — sếp chốt: dừng 2 việc P0 còn lại** (4 acc Yelp/mailbox + rewrite history `eac497b`) và chuyển ưu tiên sang **tối ưu & cải thiện tool**. Rủi ro sót (clone cũ còn history `eac497b` + credential 4 acc trong đó) **ghi nhận, không hành động**.

1. **P0 bảo mật — phần local đã đóng 11/11:** ① PAT (sếp revoke) → ② `YF_MASTER_KEY` → ③ `YF_ADMIN_TOKEN` + password Postgres: **đã rotate thật** lúc DB còn 0 dòng (precheck: 0 dòng ciphertext ở cả 5 cột `*_enc`, không có blob `email_refresh_token*` → không cần re-encrypt); sau rotate `db-check` = `ok:true, drift:null` + full suite **358 xanh** trên cây sạch (số lúc rotate; baseline hiện hành **412** — mục 1). **Còn lại (đã hủy 11/11):** ④ 4 acc Yelp/mailbox + rewrite history `eac497b`.
   - **Deploy note khi rotate `YF_MASTER_KEY`** (giữ lại cho lần rotate sau — cập nhật theo `2a6b219` + probe 11/11):
     - **Sinh key mới bằng `core.crypto.generate_master_key()`** — đừng gõ tay: từ `2a6b219` `SecretBox` **bỏ hẳn** nhánh "plain passphrase" và bắt buộc base64 (chuẩn hoặc urlsafe) giải mã ra đúng **16/24/32 byte**; passphrase thuần hay chuỗi sai đều bị từ chối → coi là **lỗi cấu hình**, không phải blob hỏng.
     - **Giữ `graph_refresh_token` cũ trong `.env` lúc rotate**: `build_provider` đọc blob **trước** rồi mới raise `email_config` khi `not graph_client_id or not (graph_refresh_token or token_blob)` → config trống nhưng blob tốt vẫn chạy được; nhưng nếu **không có blob** thì để trống là raise ngay đúng lúc rotate.
     - **Key thiếu/blank/sai hình dạng → blob được GIỮ tại chỗ** (log `refresh_token_key_missing`); chỉ khi key **đúng hình dạng** mà decrypt fail (tức key đã bị xoay) mới `refresh_token_unreadable` + quarantine `email_refresh_token.corrupt-<ts>.bin`.
     - **Legacy `.txt` không còn mất nguồn**: key không dùng được → log `refresh_token_legacy_key_missing` và **giữ nguyên** `.txt` plaintext trên đĩa; chỉ khi encrypt thành công mới xoá `.txt` (giá trị cũ giữ dạng `*.legacy.bin`).
     - **Blob `.bin` không phải "chỉ owner đọc được"**: `chmod` là no-op trên Windows; hiện dùng `icacls /inheritance:r /grant:r <user>:F` cho blob nhưng `repo\.env` vẫn `Authenticated Users:(M)` → hygiene, không phải blocker của rotate.
2. **Tối ưu & cải thiện tool (ưu tiên mới — top 3 @MAI, chờ @MINH chốt roadmap):**
   - **Số đo mới 11/11 (@AN `--durations=25`) làm 2 item dưới KHÔNG còn đúng giả thuyết** — và cả 2 **đã đóng xong**, không còn là việc mở: "DB fixture session-scope" — top durations là fake-browser sleep 37/35/34/30/29s (`test_review_poster`/`test_post_review`), test DB chỉ 0.13–0.24s; "discover_base_url" — **0 caller** trong `src/`+tests (dead code, 95s/lần khi GPM tắt). Item metrics (4/8 chưa từng set) thì đúng.
   - **ĐÃ ĐÓNG — `S — DB fixture session-scope`**: thủ phạm không phải DB mà là **sleep giả-lập-người**; đã xử lý bằng knob `YF_HUMAN_TIME_SCALE` (`9842a68`: default **1.0 = nhịp production**, đọc ở mỗi lần gọi; `tests/conftest.py` `setdefault("0.0")` → test chạy nhanh mà không đổi assertion). Full suite **280.41s → 18.33s** (đo trên máy **có `.env`**; số verify độc lập của @AN trên cây không `.env`: **412/0/0 trong 9.54s** tại `4a8e267` — xem mục 1; tài liệu knob đã vào `docs/USER_GUIDE.md` mục 5.3).
   - **ĐÃ ĐÓNG — `S — metrics "xanh giả"`** (`48961d1`): đã wire `signup_duration_seconds` / `queue_depth` / `active_profiles` / `proxy_health_ratio`; `proxy_health_ratio` tính từ `proxy_pool.status` (healthy = **không** `dead`), bảng rỗng → `None` và **không** đụng gauge; `/metrics` refresh best-effort (DB lỗi thì giữ sample cũ).
   - **ĐÃ ĐÓNG — `M — discover_base_url` quét 2000 cổng**: hàm + `SCAN_RANGE` đã **xoá** (`ca3468c`); `GPMHttpClient` đọc `http.port` theo docs GPM (@MAI verify) nên không còn quét cổng.
   - **ĐÃ CÓ thêm (anti-detect, 11/11)**: `eb320bc` — bỏ `page.set_viewport_size` sau CDP attach (mất `Emulation.setDeviceMetricsOverride` → `screen`/`innerWidth`/`outerWidth` lệch nhau) + 3 counter block/captcha/warming-429; `779af3f` — `yf probe-profile` in thêm khối `signals` (`webdriver` / `platform` / `userAgent` / `webrtcCandidateIp` / `geolocationPermission`) nhưng **máy QA không có GPM → lệnh luôn trả `GPMUnavailable`** (mục 2), phải chạy trên máy vận hành; `4211f82` — `browser_versions()` engine-aware + `resolve_browser_version()` sort numeric (trước đó `"99.0.x"` thắng `"120.0.x"`); `e01e6e5` — `geolocation_mode=1` (Allow) ngay lúc create profile + bỏ `grant_permissions` runtime (giữ `set_geolocation` — API GPM không có field lat/lon); `4a8e267` — `retry_async` đi qua `human.timing.sleep_s`.
   - **ĐANG LÀM (batch 1) — ma trận fingerprint v2**: rotate `window_size` + `browser_type` **deterministic từ `account_id`** (module `core/fingerprint_matrix.py` + `YF_FINGERPRINT_SALT` đã có trong working-tree, hook vào `signup.py`/`orchestrator.py`/`cli.py` đang hoàn thiện → **số test sẽ nhảy**, cần re-peg sau khi commit); giữ `os_type=1` tới khi verify trên máy GPM thật; enum GPM đã verify (@MAI): `browser_type` **1=Chrome / 2=Firefox**, `webrtc_mode=1` = theo IP (không phải leak), `geolocation_mode=1` = Allow → chỉ bớt được 1 lệnh CDP `grant_permissions`, vẫn phải `set_geolocation`; `profiles.fingerprint_json` persist `os_type/browser_type/browser_version/window_size` + bump `operation_id` → `reg:<id>:fp1` (đổi salt sau này phải bump `:fp2`).
   - **Đã có: `yf key-gen`** (`8aeea33`) — in key urlsafe-base64 ra stdout, **không** đọc/ghi `.env`, `--bytes 16|24|32`. (Các con số "366 passed" ở đây là **số cũ**, đã bị các batch sau đẩy lên; **số nghiệm thu hiện hành là 412** — xem mục 1 + mục 8.)
3. Nhận clients thật → chạy B1 (review + 72h).
4. Provider mail dự phòng cho fakemailo (POP3/IMAP/API).
5. Mở rộng lên ~18–20 acc nếu muốn đạt 100 review/tháng (mỗi metro ≤4–8 acc, ASN khác nhau).
6. Theo dõi filter-rate; nếu >35% giảm volume tự động (đã có), >40% alert (đã có).
