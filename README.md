# yelp-factory

Tự động hoá vòng đời tài khoản Yelp (đăng ký → verify → onboarding → nuôi 30 ngày) trên
browser thật qua GPM Login Global, điều khiển bằng Playwright CDP.

Spec gốc: `SPEC` v1.0 (mục 1-19). Các điểm lệch spec: `docs/DEVIATIONS.md`.
Ma trận edge case: `docs/EDGE_CASES.md`. Vận hành: `docs/RUNBOOK.md`.
**Hướng dẫn sử dụng A–Z: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)**

## Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Scaffold + config + logging + redact | ✅ |
| Schema Postgres (12 bảng + bảng phụ) + Alembic | ✅ |
| GPM HTTP adapter (envelope, port discovery, schema drift) | ✅ |
| GPM MCP adapter (streamable HTTP) + fallback | ✅ |
| Idempotent profile create (E-20, D-02) | ✅ |
| CDP attach (không tạo context mới) | ✅ |
| Proxy probe (geo/latency/ASN) | ✅ |
| Email: Graph OAuth2 + IMAP XOAUTH2 + fake | ✅ (mailbox đang bị Microsoft suspend) |
| Captcha: Capsolver + 2captcha + HITL + chain | ✅ |
| SMS: sms-activate + fake | ✅ |
| Selector registry + resolver + fallback | ✅ |
| State machine + checkpoint + lock + reaper + governor + budget | ✅ |
| Signup flow 12 state | ✅ (chưa chạy live Yelp) |
| Warming P0-P4 + review generator (5-gram dedupe) | ✅ |
| Warming scheduler (yf schedule) 1-3 session/ngày theo timezone | ✅ |
| Reauth flow | ✅ |
| Login flow — password + passwordless email-link (fakemailo, E-60…E-66) | ✅ |
| Post-review warm mode — 1 phiên/ngày 25–90' ngẫu nhiên, P0→P4, profile-fill/ảnh/friend/metro, không review | ✅ |
| Account pool DB — metros/clients/assignments/system_flags, lifecycle READY/COOLDOWN/RETIRED/NEEDS_MANUAL/BANNED | ✅ |
| Review phase — text ≥3 câu + chi tiết thật + khuyết điểm nhẹ + ảnh bắt buộc, 30% 4★, dedupe mở bài+5-gram | ✅ |
| Volume governor — lazy weeks, filter-rate throttle, time-of-day, jitter | ✅ |
| Alerts Telegram/Discord + file | ✅ |
| Ops — DB browser slots (race-safe), account/proxy/lock CLI, restore drill, artifact cleanup | ✅ |
| CLI + admin API | ✅ |
| Test | 316 passed (0 skipped, strict markers) |

## Cài đặt

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env    # điền secrets
.\.venv\Scripts\yf.exe db-init
```

## Dùng nhanh

```powershell
.\.venv\Scripts\yf.exe gpm-health
.\.venv\Scripts\yf.exe signup --count 1 --city "Austin, TX" --dry-run
.\.venv\Scripts\yf.exe report --since 24h
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pytest tests -q --cov=src/core --cov=src/flows --cov-report=term-missing
```

## Giao diện vận hành (yfcp)

Desktop console (Tauri 2 + React) nằm trong [`yfcp/`](yfcp/). Nó **không sửa engine**:
mọi thao tác đọc/ghi đi qua admin API do `yf serve` mở tại `127.0.0.1:8787`.

```powershell
# 1) chạy engine API (trong .venv của engine)
.\.venv\Scripts\yf.exe serve

# 2) chạy console
cd yfcp
rustup show              # phải là 1.90.0 (pin trong rust-toolchain.toml)
npm install
npm run desktop:dev      # Tauri dev
npm run desktop:build    # NSIS installer → yfcp/src-tauri/target/release/bundle/nsis/
```

Mở **Workspace settings → Console connection** để nhập admin URL + bearer token
(`YF_ADMIN_TOKEN` trong `.env`). Token được lưu trong Windows Credential Manager,
`settings.json` chỉ giữ URL. Console tự probe `/health`: khi engine tắt, các trang
rơi về bộ dữ liệu mẫu (badge "sample data") thay vì lỗi. Import accounts/proxies từ
`.txt` được lưu qua tauri-plugin-store và đẩy vào proxy pool bằng
`POST /api/pool/import` khi API sẵn sàng.

Chạy nhiều máy (1 engine + Postgres trung tâm, nhiều console): xem
[`yfcp/docs/multi-machine.md`](yfcp/docs/multi-machine.md). Mỗi console lưu
endpoint remote đã được duyệt; dữ liệu (accounts, report, events, pool) đọc từ
cùng một engine nên cập nhật đồng nhất. Trang **Nodes** hiển thị mọi máy đang
online/offline, version và lần heartbeat cuối.

## Cấu trúc

```
src/
  core/            state_machine, checkpoints, lock, backoff, budget, governor, reaper, orchestrator, report, crypto
  adapters/        gpm_http, gpm_mcp, gpm_ops, browser, proxy_probe, email, captcha, sms
  flows/           signup, onboarding, reauth, warmup, pools, login_flow, post_review_warm
  selector_registry/  registry.yaml + resolver (đổi tên từ selectors/, xem D-05)
  human/           typing, mouse, scroll, timing
  obs/             log, metrics, redact
  api/             admin, schemas
  db/              models, session
  cli.py
tests/
  unit/ integration/ e2e/ chaos/ cases/E-xx_*.py
```
