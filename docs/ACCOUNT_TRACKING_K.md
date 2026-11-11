# Bảng K — bảng theo dõi tài khoản (18 cột bắt buộc)

> Nguồn: mục **K** của đặc tả @Boss (2026-11-11). SOP vận hành: `docs/ACCOUNT_LIFECYCLE_SOP.md`.
> File mẫu: `docs/templates/account_tracking_template.csv` (copy ra `data/account_tracking.csv` — `data/` đã gitignore).
> Quy tắc: **1 acc = 1 dòng**, `ID acc` duy nhất, không dòng trùng, không xoá dòng (chỉ đổi trạng thái).

## 1. Danh sách cột

| # | Tên cột (đúng tên trong file) | Kiểu | Nguồn | Quy tắc ràng buộc |
|---|---|---|---|---|
| 1 | `ID acc` | uuid | DB `accounts.id` | Bắt buộc, duy nhất, không đổi |
| 2 | `Supplier` | text | Nhà cung cấp acc | Bắt buộc; dùng để tách lô khi tính KPI |
| 3 | `Email gốc` | text | Email mua về | Bắt buộc; 1 inbox = 1 acc |
| 4 | `City gốc` | text | City thật của acc khi nhận | Bắt buộc; **không** phải metro đích |
| 5 | `Metro đích` | text | Metro của khách | Bắt buộc; phải khớp `yf clients metros` |
| 6 | `Ngày nhận` | `YYYY-MM-DD` | Ngày nhận acc | Bắt buộc = **Ngày 0**; mọi mốc ngày tính từ đây |
| 7 | `Ảnh` | `OK` / `CHƯA` | Avatar thật đã upload | `OK` khi có ảnh chân dung thật (không stock, không AI) |
| 8 | `Bio` | `OK` / `CHƯA` | Bio 1 dòng tự nhiên | Không nhồi nghề, không khoá |
| 9 | `Số bạn` | int | Số friend đã kết | Cần ≥ 2 để qua cổng G |
| 10 | `Số tip` | int | Số tip đã viết | Cần ≥ 1 ở ngày 4 và ≥ 1 ở ngày 10–12 |
| 11 | `Số check-in` | int | Số check-in trong metro đích | Cần ≥ 1 trong metro khách để qua cổng G |
| 12 | `Ngày mồi 1-2-3` | `d1;d2;d3` | Ngày đăng 3 review mồi | Chuỗi ngày phân tách bằng `;`; dự kiến D13/D16/D19 |
| 13 | `Trạng thái mồi` | enum | Kiểm tra sau ≥72h | Chỉ nhận: `chưa` · `đang` · `3/3 sống ≥72h` · `bị lọc` |
| 14 | `Hạng` | enum | Cổng G | Chỉ nhận: `chưa chấm` · `A` (6/6) · `B` (5/6) · `C` (4/6) · `Loại` (<4/6) |
| 15 | `Ngày dùng 1-2-3-4` | `d1;d2;d3;d4` | Ngày dùng cho khách | Tối đa 4 lần (mục J), cách 3–4 tuần |
| 16 | `Client` | text | Business khách | Tên business (khách) mà acc đã đăng review |
| 17 | `Trạng thái review ở ngày 2/7/14/30` | text | Mốc kiểm tra | Định dạng `D2: OK \| D7: OK \| D14: \| D30:` — **bị lọc ở mốc nào ghi mốc đó, không xoá** |
| 18 | `Ghi chú` | text | Bất kỳ | Bắt buộc ghi khi: bị lọc, vi phạm mục M, acc đổi lô, acc hết hạn dùng |

## 2. Quy tắc nghiệm thu bảng

1. Đủ **18 cột**, đúng tên, đúng thứ tự — không thêm cột tạm, không đổi tên.
2. Mỗi acc có đúng 1 dòng; `ID acc` không trùng.
3. `Ngày nhận` luôn có mặt (không để trống) — không có ngày nhận thì không tính được cổng G.
4. `Trạng thái mồi` và `Hạng` chỉ chấp nhận giá trị trong danh sách enum ở mục 1.
5. `Ngày dùng 1-2-3-4` không có quá 4 phần tử; mỗi lần cách lần trước ≥ 21 ngày.
6. **Chỉ dùng cho khách khi `Hạng` = A/B/C** (≥4/6). `chưa chấm`/`Loại` → không assign.
7. Với mỗi lần đăng review cho khách: phải có ảnh chụp màn hình + giờ đăng + `ID acc` lưu kèm `Ghi chú`.

## 3. Trạng thái mốc 2/7/14/30 (mục I)

| Mốc | Hành động | Ghi vào cột 17 |
|---|---|---|
| D+2 | Kiểm tra review còn hiển thị không | `D2: OK` hoặc `D2: bị lọc` |
| D+7 | Kiểm tra lại | `D7: OK` / `D7: bị lọc` |
| D+14 | Kiểm tra lại | `D14: OK` / `D14: bị lọc` |
| D+30 | Kiểm tra lại + chấm "sống ở mốc 30 ngày" | `D30: OK` / `D30: bị lọc` |

- Bị lọc **2 lần liên tiếp** → hạng tối đa **B** (loại khỏi khách trả cao).
- Bị lọc **3 lần** → `Hạng` = `Loại`, không dùng lại, ghi vào `Ghi chú`.

## 4. Ví dụ 4 dòng (dữ liệu giả, không phải acc thật)

```
ID acc                                   | Supplier | Email gốc            | City gốc   | Metro đích     | Ngày nhận | Ảnh | Bio | Số bạn | Số tip | Số check-in | Ngày mồi 1-2-3                  | Trạng thái mồi    | Hạng      | Ngày dùng 1-2-3-4               | Client        | Trạng thái review ở ngày 2/7/14/30            | Ghi chú
00000000-0000-0000-0000-000000000001   | lotA     | a1@example.invalid  | Phoenix,AZ | New York, NY   | 2026-11-01 | OK  | OK  | 3       | 2      | 2            | 2026-11-14;2026-11-17;2026-11-20 | 3/3 sống ≥72h    | A         | 2026-11-24                        | "Corner Cafe"  | D2: OK | D7: OK | D14: OK | D30:      | hạng A đủ 6/6
00000000-0000-0000-0000-000000000002   | lotA     | a2@example.invalid  | Phoenix,AZ | New York, NY   | 2026-11-01 | OK  | OK  | 2       | 1      | 1            | 2026-11-14;2026-11-17;2026-11-20 | 3/3 sống ≥72h    | B         | 2026-11-25                        | "Corner Cafe"  | D2: OK | D7: bị lọc | D14: | D30: | bị lọc lần 1 ở D7, hạng tối đa B
00000000-0000-0000-0000-000000000003   | lotB     | a3@example.invalid  | Austin,TX  | Chicago, IL    | 2026-11-08 | CHƯA| CHƯA| 0       | 0      | 0            |                                | chưa              | chưa chấm |                                    |                |                                          | chưa đủ 21 ngày
00000000-0000-0000-0000-000000000004   | lotB     | a4@example.invalid  | Denver,CO  | Chicago, IL    | 2026-10-20 | OK  | OK  | 2       | 1      | 0            | 2026-11-02;2026-11-05;2026-11-08 | 3/3 sống ≥72h    | Loại     |                                    |                | D2: OK | D7: OK | D14: bị lọc | D30: bị lọc | không có check-in ở metro đích → Loại, dùng 3 lần → bỏ
```

## 5. Cách dùng file

```powershell
# Copy mẫu ra data/ (data/ đã gitignore -> không lên git)
Copy-Item docs\templates\account_tracking_template.csv data\account_tracking.csv

# Cổng kiểm tra G
Copy-Item docs\templates\gate_check_template.csv data\gate_check.csv

# KPI tuần (mục N)
Copy-Item docs\templates\weekly_kpi_template.csv data\weekly_kpi.csv
```

- Export ra Google Sheet khi @Boss yêu cầu (không tự đẩy).
- **Không in password/token** vào bất kỳ cột nào của bảng K.
