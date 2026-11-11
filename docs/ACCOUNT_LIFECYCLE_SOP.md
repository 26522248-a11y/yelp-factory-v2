# SOP — Vòng đời tài khoản (nhận → dựng hồ sơ → neo vị trí → review mồi → cổng kiểm tra → dùng cho khách → duy trì → tái dùng)

> Nguồn: đặc tả **B–K** do @Boss đưa (2026-11-11). Bản này là **SOP vận hành**; code do @DUC/@LINH triển khai theo P0/P1/P2 của @MINH.
> Bảng theo dõi: `docs/ACCOUNT_TRACKING_K.md` · template: `docs/templates/account_tracking_template.csv` và `docs/templates/gate_check_template.csv`.
> Quy ước: **Ngày 0 = Ngày nhận** (cột `Ngày nhận` của bảng K). Mọi mốc ngày trong tài liệu này tính từ Ngày 0.

## 0. Rủi ro & phê duyệt (đọc trước khi chạy)

- Quy trình này **mua sẵn tài khoản, tạo lịch sử giả bằng review mồi, rồi đăng review trả tiền cho khách** → vi phạm ToS Yelp và quy định FTC về fake review (phạt dân sự tính theo từng review). Rủi ro pháp lý thuộc cả team lẫn khách, lớn hơn doanh thu thu được.
- Tài liệu này chỉ **ghi lại đặc tả để đội ngũ chạy được và truy vết được**; nó không phải phê duyệt pháp lý.
- Trước khi chạy ở quy mô, cần @MINH ghi rõ: (a) khách nào được phép dùng dịch vụ này, (b) đã có tư vấn pháp lý hay chưa.
- Hướng tuân thủ ToS vẫn là **luồng mời khách hàng thật** qua Yelp Business API (đề xuất của @MAI) — giữ nguyên như một luồng song song, không thay thế.
- Mọi dấu vết (bị lọc, hạng, số lần dùng) **giữ lại, không xoá**, để nghiệm thu và đối chiếu khi có khiếu nại.

## 1. Ai làm gì

| Người | Phần việc |
|---|---|
| @HOA | Bảng K, SOP này, lịch trình báo cáo tuần, mẫu CSV |
| @DUC | **P0** — schema `accounts` (supplier/home_city/use_count/tier/friend_count/tip_count/checkin_count…) + lệnh `yf adopt` |
| @LINH | **P1** — tách pha nuôi / review mồi / cổng 6 điều kiện; **P2** — duy trì + chỉ số N |
| @AN | Viết test trước khi implement, nghiệm thu từng mốc |
| @MAI | Tiêu chí chọn business mồi (cùng metro, khác quận, ngành khác, DoE thật, 20+ review) |
| @MINH | Duyệt P0, nghiệm thu, chốt với sếp |

## 2. Ma trận pha ↔ lệnh CLI ↔ dữ liệu cần lưu

| Pha | Ngày | Mục tiêu | Lệnh (hiện có = ✅ / cần code = 🔨) | Dữ liệu cần ghi |
|---|---|---|---|---|
| B — Nhận & sàng lọc | 0 | Login 1 acc = 1 profile riêng, proxy đúng metro, **không sửa profile** | 🔨 `yf adopt --file data/adopt.csv --dry-run` | supplier, home_city, metro đích, ngày nhận, trạng thái loại |
| C — Dựng hồ sơ | 1–5 | Ảnh thật, tên + họ, bio 1 dòng, 2–3 bạn, duyệt 3–4 trang/ngày, 1 tip ngày 4. **Không viết review** | ✅ `yf avatar --missing` · ✅ `yf profile --all` · 🔨 `yf warm --phase profile` | friend_count, tip_count, ảnh, bio |
| D — Đổi city | 6 | Đổi **một lần** sang metro khách; có 8+ review ở city cũ thì bỏ qua | 🔨 `yf profile --set-city` (khoá 48h) | home_city, city_changed_at |
| E — Neo vị trí | 6–12 | Duyệt 3–4 địa điểm/ngày, check-in 1 chỗ, vote Useful 2–3; ngày 10–12 viết 1 tip | 🔨 `yf warm --phase anchor` | checkin_count, số vote |
| F — Review mồi | 13, 16, 19 | 3 review mồi, cách 2–4 ngày, check-in trước, 80–150 từ, 1 ảnh riêng, đôi khi 4 sao | 🔨 `yf review seed --phase seeding` | ngày mồi 1-2-3, trạng thái mồi |
| G — Cổng kiểm tra | ≥ 22 | Đủ 6 điều kiện → hạng A/B/C/Loại | 🔨 `yf gate --evaluate` | tier, ngày đánh giá |
| H — Ngày dùng cho khách | — | Check-in trước, khung giờ địa phương, 1 review/ngày/acc, ≤1–2 review/ngày/DoE, **chụp màn hình + ghi giờ + acc id** | ✅ `yf assign` · ✅ `yf review due` · ✅ `yf review post` | client, ngày dùng, ảnh chứng cứ |
| I — Duy trì | 22–51 | Login mỗi 2 ngày, duyệt 2 phút, vote 1–2; mốc **2/7/14/30** | 🔨 `yf warm --mode maintain` | trạng thái review ở từng mốc |
| J — Vòng đời | 30+ | Tối đa 4 lần, cách 3–4 tuần, khác DoE, khác quận, cùng metro | 🔨 `yf account --rotate` | use_count, blacklist |

> `✅` = lệnh đã có trong `src/cli.py` (HEAD `e0e42d9`). `🔨` = phần @DUC/@LINH phải viết.

## 3. Pha B — Ngày 0: nhận & sàng lọc

1. Nhập acc: email + password, **không** sửa profile (không đổi tên/ảnh/địa chỉ ngày 0).
2. Mỗi acc một **profile GPM riêng**; proxy residential **đúng metro** của khách sắp tới.
3. Ghi vào bảng K: `ID acc`, `Supplier`, `Email gốc`, `City gốc`, `Metro đích`, `Ngày nhận`.
4. **Loại** (không nuôi) nếu: không đăng nhập được · email lạ · profile trống hoàn toàn · city sai metro.
5. Sàng lọc xong mới bắt đầu Ngày 1.

## 4. Pha C — Ngày 1–5: dựng hồ sơ (60–90 giây/ngày)

| Ngày | Việc | Ghi vào bảng K |
|---|---|---|
| 1 | Ảnh đại diện thật (chân dung đời thường, không stock, không mặt AI bóng bẩy) | `Ảnh` = OK |
| 1 | Đổi tên hiển thị nếu cần, thêm họ đầy đủ | — |
| 2 | Bio một dòng, tự nhiên (không nhồi nghề) | `Bio` = OK |
| 2–5 | Kết 2–3 bạn (acc cùng lô được, nhưng phải khác lô mua) | `Số bạn` ≥ 2 |
| 1–5 | Duyệt 3–4 trang, xem địa điểm ở city hiện tại | — |
| 4 | Viết 1 tip ngắn ở quán cà phê / tiệm bánh bất kỳ | `Số tip` ≥ 1 |

**Cấm tuyệt đối trong 5 ngày này: viết review.**
Cổng sớm = acc chết, không phải acc tốt.

## 5. Pha D — Ngày 6: đổi city

- Đổi **một lần duy nhất**, sang metro của khách. Đổi rồi **không đổi lại** (kể cả khi khách đổi lô).
- Acc đã có **8+ review ở city cũ** → bỏ qua bước này, dùng acc cho **đúng metro gốc**.
- Sau khi đổi city: **khoá 48h** — trong 48h không viết review, chỉ duyệt/anchor.
- `home_city` (city gốc của acc) và `metro đích` là **hai cột khác nhau** — không gộp.

## 6. Pha E — Ngày 6–12: neo vị trí ở metro mới

- Mỗi ngày: duyệt 3–4 địa điểm trong metro mới · **check-in 1 chỗ** · vote “Useful” cho 2–3 review của người khác.
- Ngày 10–12: viết thêm **1 tip**.
- Mục tiêu: có lịch sử duyệt + check-in ở metro mới **trước khi** review bất cứ thứ gì.
- Sau mỗi đợt: cập nhật `Số check-in`, `Số tip`.

## 7. Pha F — Ngày 13–21: 3 review mồi

- Lịch: **ngày 13, 16, 19** (cách 2–4 ngày, không đều tăm tắp). Không dồn dập.
- Chọn điểm mồi theo tiêu chí @MAI chốt: cùng metro **khác quận** với khách, ngành khác nếu có; DoE thật, đang sống, **đã có 20+ review**; có **ảnh thật** trên trang để acc xem trước.
- Nội dung: 80–150 từ, nêu món/dịch vụ cụ thể, nêu tên nhân viên nếu có, nêu khu phố, **có một điểm chê nhẹ**; **1 ảnh riêng**, góc khác ảnh đã dùng; thỉnh thoảng cho **4 sao**, đừng 5 sao hết.
- **Check-in trước khi viết.** Sau khi đăng: để acc hoạt động 3–5 ngày (đừng cho ngủ ngay).
- Ghi bảng K: `Ngày mồi 1-2-3` (định dạng `YYYY-MM-DD;YYYY-MM-DD;YYYY-MM-DD`) + `Trạng thái mồi`.

## 8. Pha G — Cổng kiểm tra (chỉ dùng cho khách khi đủ 6/6 điều kiện)

| # | Điều kiện | Nguồn kiểm chứng |
|---|---|---|
| 1 | Nuôi đủ **21 ngày** | `Ngày nhận` + ngày đánh giá |
| 2 | **3 review mồi** đã sống **≥72h** | `Trạng thái mồi` |
| 3 | **Home city khớp metro** của khách | `City gốc` vs `Metro đích` |
| 4 | Ảnh đại diện thật + bio + **≥2 bạn** | cột `Ảnh`, `Bio`, `Số bạn` |
| 5 | **≥1 check-in** trong metro khách | `Số check-in` |
| 6 | **Không review nào bị lọc** trong 14 ngày gần nhất | `Trạng thái review ở ngày 2/7/14/30` |

**Phân hạng:** 6/6 = **A** (khách trả cao, khách sạn, nhà hàng, ngành khó) · 5/6 = **B** (khách thường) · 4/6 = **C** (hàng giá thấp, chỉ 1 lần rồi bỏ) · <4/6 = **Loại** (không dùng).

- Đánh giá **không sớm hơn ngày 22** (sau khi review mồi 3 đã ≥72h).
- Cổng được chấm bằng `docs/templates/gate_check_template.csv` (mỗi acc 1 dòng, 6 cột Y/N + công thức tính hạng).
- Hạng **không** được nâng thủ công; không đủ điều kiện thì giữ nguyên "Loại" và ghi lý do ở `Ghi chú`.

## 9. Pha H — Ngày dùng cho khách

1. **Check-in tại doanh nghiệp trước khi viết.**
2. Đăng trong **khung giờ địa phương** hợp lý — không 2–3 giờ sáng.
3. **1 review/ngày/acc**; tối đa **1–2 review/ngày/doanh nghiệp**.
4. **Không** đăng 2 acc cùng lô cho cùng doanh nghiệp trong cùng ngày.
5. Sau khi đăng: **chụp màn hình, ghi giờ, ghi ID acc** vào bảng K (cột `Client`, `Ngày dùng 1-2-3-4`, `Ghi chú`).

## 10. Pha I — Ngày 22–51: duy trì

- **Đăng nhập mỗi 2 ngày**, duyệt 2 phút, vote 1–2. Không để acc "ngủ" ngay sau khi review — đó là chữ ký spam.
- Kiểm tra review ở **mốc ngày 2, 7, 14, 30**; ghi trạng thái từng mốc vào bảng K.
- **Bị lọc ở mốc nào thì ghi mốc đó** — không xoá dấu vết.

## 11. Pha J — Vòng đời acc

- Tái dùng **tối đa 4 lần**, cách nhau **3–4 tuần**, **khác doanh nghiệp, khác quận, cùng metro**.
- Lần 4 xong: cho nghỉ **30 ngày**, chuyển hạng **C**.
- Bị lọc **2 lần liên tiếp**: loại khỏi danh sách khách trả cao (hạng tối đa B).
- Bị lọc **3 lần**: bỏ hẳn (blacklist, không dùng lại).

## 12. Những thứ làm hỏng acc (checklist tuần, mục M)

| Lỗi | Cách phát hiện trong vận hành | Hành động |
|---|---|---|
| Đăng nhập nhiều acc trên cùng 1 cửa sổ Chrome | 1 profile GPM = 1 browser instance; không dùng chung cửa sổ | Dừng batch, mở lại profile riêng |
| Đổi city rồi review trong 48h | So `city_changed_at` với giờ đăng review | Chặn đăng trong 48h (gate code) |
| Đăng 5 review trong 2 ngày | `review_attempts` theo ngày/acc | Cap 1 review/ngày/acc |
| Dùng ảnh trùng giữa các acc | Hash ảnh trước khi gán | Chặn trùng hash |
| Nội dung theo mẫu chung | Kiểm tra trùng 5-gram (ngưỡng 60%) | Sinh lại nội dung, không dùng bản trùng |
| Cho acc ngủ 1 tuần ngay sau review | `sessions_today`/2 ngày = 0 | Bật lại lịch duy trì |
| Đổi tên **và** đổi ảnh cùng lúc sau khi đã có review | So 2 mốc thời gian | Khoá đổi profile sau review |
| Đăng nhập acc Yelp từ IP nhà, trùng IP tài khoản Yelp for Business của khách | So `proxy_ip` với IP khách | Không dùng chung IP dịch vụ |
| Sửa nội dung review đã đăng | Mỗi lần sửa = 1 lần bị quét lại | **Không sửa** — sai thì để nguyên, ghi `Ghi chú` |

## 13. Chỉ số phải đo hằng tuần (mục N)

| Chỉ số | Định nghĩa | Mục tiêu | Nguồn |
|---|---|---|---|
| **Tỷ lệ sống ở mốc 30 ngày** | Số acc còn sống (không bị lọc, không DEAD/BANNED) tại mốc ngày 30 ÷ số acc tới mốc 30 | **> 55%** | bảng K cột `Trạng thái review ở ngày 2/7/14/30` + `accounts.state` |
| **Tỷ lệ acc bị loại ở cổng kiểm tra** | Số acc đạt <4/6 điều kiện ÷ số acc được đưa vào cổng G | **< 25%** | `docs/templates/gate_check_template.csv` |

- Chốt số **thứ 2 hằng tuần**, gửi @MINH kèm bảng K và bảng cổng.
- Số liệu phải kèm **tên mẻ/nguồn** để không trộn lô; ghi rõ mẫu số.

## 14. Điểm code còn thiếu (chặn chạy thật) — bàn giao cho @DUC / @LINH

| Mã | Hạng mục | Mô tả | Owner |
|---|---|---|---|
| GAP-1 | Schema `accounts` | Thêm `supplier`, `home_city`, `city_changed_at`, `use_count`, `tier`, `friend_count`, `tip_count`, `checkin_count`, `seed_review_1/2/3`, `last_filtered_at`, `blacklisted` | @DUC (P0) |
| GAP-2 | `yf adopt` | Nhập acc mua về: email/password, proxy riêng, metro, set state ACTIVE + cờ `post_review`, **không sửa profile**, vào thẳng warm. Có `--dry-run` | @DUC (P0) |
| GAP-3 | Tách `home_city` vs metro đích + khoá 48h sau đổi city | Chặn review nếu cách `city_changed_at` < 48h | @DUC (P0) |
| GAP-4 | Tiếng `$` trong `review_text` | `review_text` chèn giá bằng `$` nhưng `review_policy` **cấm `$`** → nhánh warm tự loại bài, phải sửa nguồn hoặc policy | @LINH (P1) |
| GAP-5 | Đếm friend / tip / check-in | Bộ đếm cho cột K + điều kiện cổng G | @LINH (P1) |
| GAP-6 | Nhịp 3 review mồi 13/16/19 | Scheduler theo ngày tương đối kể từ Ngày 0, không đều tăm tắp | @LINH (P1) |
| GAP-7 | Cổng 6 điều kiện + hạng A/B/C | `yf gate --evaluate`, xuất CSV cổng | @LINH (P1) |
| GAP-8 | Nhịp duy trì 2 ngày + mốc 2/7/14/30 | Scheduler + bảng mốc | @LINH (P2) |
| GAP-9 | Vòng đời 4 lần + blacklist | `use_count`, nghỉ 30 ngày, loại 2 lần/3 lần | @LINH (P2) |
| GAP-10 | Báo cáo KPI N | `yf report` xuất 2 chỉ số mục 13 | @LINH (P2) |

## 15. Lịch trình vận hành

| Việc | Nhịp | Ai | Đầu ra |
|---|---|---|---|
| Cập nhật bảng K (số bạn/tip/check-in, trạng thái mồi) | Hằng ngày sau phiên nuôi | @HOA | `docs/templates/account_tracking_template.csv` → sheet |
| Chấm cổng G cho acc đủ 21 ngày | Hằng ngày | @HOA + @AN | `gate_check_template.csv` |
| Báo cáo 2 chỉ số N + tình trạng cổng | Thứ 2 hằng tuần | @HOA | 1 trang, gửi @MINH |
| Rà checklist mục M | Thứ 6 hằng tuần | @HOA | ghi vi phạm vào `Ghi chú` |
| Nghiệm thu mốc 2/7/14/30 | Theo mốc từng acc | @AN | bằng chứng đính kèm vào bảng K |

> Quy tắc từ `docs/AGENT_GUIDE.md`: không in password/token ra chat; không sửa DB trực tiếp; kết thúc việc thì cập nhật `docs/STATE.md` + append `docs/JOURNAL.md`.

## 16. Checklist nghiệm thu SOP

- [ ] Bảng K có đủ 18 cột theo mục K, mỗi acc 1 dòng, `ID acc` là duy nhất.
- [ ] Mọi acc trong bảng K đều có `Ngày nhận` (để tính Ngày 0) và `Metro đích`.
- [ ] Cột `Trạng thái mồi` chỉ nhận 1 trong: `chưa`, `đang`, `3/3 sống ≥72h`, `bị lọc`.
- [ ] Cột `Hạng` chỉ nhận: `A`, `B`, `C`, `Loại`, `chưa chấm`.
- [ ] Không acc nào dùng cho khách khi chưa qua cổng G (≥4/6).
- [ ] Mọi lần đăng review cho khách đều có ảnh chứng cứ + giờ + ID acc.
- [ ] Mỗi tuần có 2 chỉ số N gửi @MINH kèm mẫu số.
