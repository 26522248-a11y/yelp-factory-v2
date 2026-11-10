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

Repo: Python 3.12, Postgres 16, Playwright, SQLAlchemy/Alembic. **349 test pass, 0 failed, 0 skipped** (đo trên HEAD `bc0f6ae`, cây **không có `.env`**).

---

## 2. Môi trường hiện tại (máy Windows này)

| Thành phần | Giá trị |
|---|---|
| Repo | `C:\Users\Administrator\Documents\Default Project\yelp-factory` |
| venv | `.venv` → dùng `.\.venv\Scripts\python.exe`, CLI `.\.venv\Scripts\yf.exe` |
| Git | portable `C:\minGit\cmd\git.exe` (chưa có trong PATH) |
| Postgres 16 (portable) | binaries `data/pg/pgsql`, data dir `data/pgdata`, **port 5433**, user `postgres`, password `postgres`, DB `yelp_factory` |
| Backup | `C:\pgbackup` (dump 03:00 hằng ngày, giữ 14; **không** chứa bản `.env` — chỉ ghi tên key) |
| Máy QA (11/11) | repo `E:\Default Project\ai-team-workspace\repo`, Python 3.12 hệ thống (không có `.venv`), Postgres portable đã dựng tại `data/pg/pgsql` + `data/pgdata` |
| Task Scheduler | `YelpFactoryPostgres` (AtStartup), `YelpFactoryPgBackup` (03:00), `YelpFactoryDaily` (mỗi giờ + RandomDelay 10', chỉ spawn worker nền) |
| Máy | 4GB RAM → **trần thực tế 2 profile**; timezone máy **UTC-8**; metro NY = EST UTC-5 |
| GPU/RAM guard | `core/governor` tự hạ concurrency theo RAM |

> **Chuẩn đường dẫn Postgres (thống nhất 11/11):** binaries `data/pg/pgsql`, data dir `data/pgdata` (repo-relative), cổng 5433 — khớp `scripts/yf_launcher.ps1` và `docs/RUNBOOK.md`.
> `C:\pg16` / `C:\pgdata2` / user `pguser` là cấu hình riêng của máy cũ (chạy dưới Administrator), **không dùng lại**.
> Dựng lại ở máy mới/QA: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_pg_portable.ps1`.

**Đặc thù Postgres trên máy này:** không chạy được dưới Administrator (lỗi 0xC0000142 khi spawn backend). Phải chạy bằng user `pguser` qua `Start-Process -Credential` (xem task `YelpFactoryPostgres`).

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

---

## 7. Cấu hình & secret

- `config.yaml`: post_review (25–88', 08–20, max_concurrent 2, geo_by_city, early_session_photos 3), login (fakemailo, bad_credentials_retries 1), email provider fakemailo
- `.env` (gitignored): `YF_DATABASE_URL`, `YF_MASTER_KEY`, `YF_ADMIN_TOKEN`, `YF_GPM__MCP_TOKEN`, `YF_LOGIN__MAIL_READER_PROFILE_ID` (profile Resi `4c2b5b3c-…`), optional Telegram/Discord/webhook
- **CẢNH BÁO:** URL repo trả **404 ẩn danh** (đã private/đổi tên/xoá) nhưng **không** được coi là an toàn: 3 script (`seed_pool.py`, `run_post_review_batch.ps1`, `run_post_review_betty.ps1`) chứa **email + mật khẩu thật** của 4 tài khoản và **đã nằm trong commit `eac497b` đã push**; PAT từng dùng để push cũng đã lộ trong chat.
  **Việc cần làm ngay (thứ tự đã chốt):** ① revoke PAT → ② rotate `YF_MASTER_KEY` (lúc DB còn 0 dòng là rẻ nhất) → ③ `YF_ADMIN_TOKEN` + password Postgres → ④ 4 acc Yelp/mailbox (cuối, vì tốn live login). `YF_ADMIN_TOKEN` mới **không được** trùng `test-admin-token` (đã nằm public trong `tests/conftest.py`); rewrite history chỉ làm sau khi đã xoá hết clone cũ.

---

## 8. Chạy & kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q     # 349 passed, 0 failed, 0 skipped (DB phải chạy)
.\.venv\Scripts\yf.exe db-check                   # model ↔ DB, phải ok:true
.\.venv\Scripts\yf.exe volume                     # multiplier (tuần lẻ 0.6)
.\.venv\Scripts\yf.exe pool-audit

# Máy QA (không có .venv): dùng Python 3.12 hệ thống
python -m cli db-init        # schema (DB trắng -> create_all + stamp head)
python -m cli db-check       # model <-> DB
python -m pytest tests -q    # full suite, DB thật -> không được skip
```

**Điều kiện nghiệm thu (bắt buộc từ 11/11):**
1. Full suite phải chạy được trên **cây không có `.env`** (token test do `tests/conftest.py` setdefault) — không được copy `.env` vào worktree để "làm xanh" suite: **349 passed / 0 failed / 0 skipped**, `tests/unit/test_api_pool.py` 5 passed, `tests/unit/test_email.py` 23 passed, `E-93 + E-95` = 9 passed, không còn xfail.
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
- Repo 404 ẩn danh (private/đổi tên/xoá) nhưng credential 4 acc Yelp vẫn nằm trong history (`eac497b`) và chưa rotate (mục 7).

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
12. **Dùng key tạm khi rotate** → mất blob lành: key không phải base64 vẫn dựng được box nên blob tốt bị quarantine, và legacy `.txt` bị mã hoá bằng key đó rồi xoá → mất cả bản plaintext duy nhất (xem ghi chú deploy dưới mục 11, khoản 1).

---

## 11. Việc tiếp theo (đề xuất)

1. **P0 bảo mật (thứ tự đã chốt):** revoke PAT → rotate `YF_MASTER_KEY` (DB còn 0 dòng) → `YF_ADMIN_TOKEN` + password Postgres → 4 acc Yelp/mailbox cuối cùng; rewrite history chỉ sau khi đã xoá hết clone cũ, và repo đã 404 ẩn danh thì vẫn phải kiểm tra từ tài khoản có quyền (fork/cũ).
   - **Deploy note khi rotate `YF_MASTER_KEY`** (cập nhật theo `bc0f6ae` + probe 11/11):
     - **Giữ `graph_refresh_token` cũ trong `.env` lúc rotate**: `build_provider` đọc blob **trước** rồi mới raise `email_config` khi `not graph_client_id or not (graph_refresh_token or token_blob)` → config trống nhưng blob tốt vẫn chạy được; nhưng nếu **không có blob** thì để trống là raise ngay đúng lúc rotate.
     - **Key thiếu/blank/sai độ dài → blob được GIỮ tại chỗ** (log `refresh_token_key_missing`); chỉ khi box dựng được mà decrypt fail mới `refresh_token_unreadable` + quarantine `email_refresh_token.corrupt-<ts>.bin`. Vẫn phải giữ `graph_refresh_token` cũ để mailbox không chết âm thầm khi key vắng.
     - **Key rác (không phải base64, rơi vào nhánh passphrase) vẫn làm blob lành bị quarantine** (`blob_still_at_path=False`) → đừng dùng chuỗi tạm khi rotate; dùng base64 chuẩn 32 byte (base64 sai độ dài đã được tính là key-missing nên blob vẫn được giữ).
     - **Legacy `.txt` có thể mất nguồn duy nhất**: nếu key rác vẫn dựng được box thì `.txt` được mã hoá bằng key đó rồi **xoá** (`refresh_token_legacy_plaintext_migrated`) → sau đó key thật quay lại không đọc được blob, token chỉ cứu được bằng đúng chuỗi rác → **chỉ xoá tay `.txt` sau khi đã xác nhận blob đọc được bằng key thật**.
     - **Blob `.bin` không phải "chỉ owner đọc được"**: `chmod` là no-op trên Windows; hiện dùng `icacls /inheritance:r /grant:r <user>:F` cho blob nhưng `repo\.env` vẫn `Authenticated Users:(M)` → hygiene, không phải blocker của rotate.
2. Nhận clients thật → chạy B1 (review + 72h).
3. Provider mail dự phòng cho fakemailo (POP3/IMAP/API).
4. Mở rộng lên ~18–20 acc nếu muốn đạt 100 review/tháng (mỗi metro ≤4–8 acc, ASN khác nhau).
5. Theo dõi filter-rate; nếu >35% giảm volume tự động (đã có), >40% alert (đã có).
