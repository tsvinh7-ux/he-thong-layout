# Hướng dẫn designer: làm file mẫu `.indt` và tinh chỉnh file dựng

## 1. Làm file mẫu `.indt` cho một dòng sách

File mẫu quyết định toàn bộ hình thức của sách. Hệ thống chỉ "rót" nội dung vào.

1. **Document Setup**: khổ thành phẩm, Facing Pages, Bleed (đúng như `template.yaml`).
2. **Margins and Columns**: đúng như `margins_mm` và `columns` trong `template.yaml`
   (script tạo khung chữ theo lề của trang).
3. **Edit > Color Settings**: CMYK Working Space = ICC profile của nhà in.
   Tên profile phải trùng với `color.cmyk_profile`.
4. **Master page** (A-Master): số trang, tiêu đề chạy (dùng Text Variable
   *Running Header – Paragraph Style* trỏ tới style `Chapter Title`/`H1`).
   Không cần khung chữ chính (primary text frame); script tự tạo.
   Nếu dùng master khác tên, khai báo `body_master: "B-Body"` trong `template.yaml`.
5. **Paragraph Styles**: tạo các style có **đúng tên** như mục `roles` trong `template.yaml`:

   | Vai trò | Tên style mặc định | Ghi chú |
   |---|---|---|
   | chapter_number | Chapter Number | |
   | chapter_title | Chapter Title | |
   | h1 … h4 | H1 … H4 | Keep with next |
   | body / body_first | Body / Body First | Body First: đoạn đầu sau tiêu đề, không thụt dòng |
   | list_bullet, list_bullet_2 | List Bullet, List Bullet 2 | Bullets and Numbering: Bullets |
   | list_number, list_number_2 | List Number, List Number 2 | **Không bật Numbering**: số đã có sẵn trong chữ (`1.` + Tab). Dùng thụt treo (hanging indent). |
   | quote | Quote | |
   | box_title / box | Box Title / Box Body | Có thể dùng Paragraph Shading/Border |
   | caption / table_caption | Figure Caption / Table Caption | |
   | table_head / table_body / table_note | Table Head / Table Body / Table Note | |
   | reference | Reference | Tài liệu tham khảo |
   | footnote | Footnote | |
   | figure | Figure | Đoạn chứa ảnh: cỡ chữ/leading rất nhỏ (2 pt), căn giữa, Keep with next = 1 |
   | table | Table Anchor | Đoạn chứa bảng |

6. **Character Styles**: `Bold`, `Italic`, `Bold Italic` (chỉ đổi Font Style).
7. **Table Style**: `HTL Table` (cell style cho header/body, nét kẻ).
8. **Object Style**: `HTL Figure` (Anchored Object Options: *Above Line*, căn giữa).
9. **Tiếng Việt**: tắt Hyphenation trong các style chữ tiếng Việt. Dùng font có đủ dấu tiếng Việt
   (Noto Serif/Sans, Source Serif, Minion Pro, Myriad Pro…), kiểm bằng mẫu
   "ỗ ặ ữ ỹ Ẩ Ặ Ỡ ợ ự".
10. Lưu thành `.indt` (File > Save As > InDesign Template) trong thư mục mẫu, rồi khai báo
    `indt: ten-file.indt` trong `template.yaml`.

Style nào thiếu, script sẽ tự tạo và ghi cảnh báo trong `indesign_report.json`.

## 2. Chạy dựng tự động

1. Nhận thư mục `build/` (gồm `run_in_indesign.jsx`, `htl_build.jsx`, `stories/`, `images/`).
2. Mở InDesign → File > Scripts > Browse… → chọn `run_in_indesign.jsx`.
3. Chờ thông báo kết thúc. Kết quả nằm trong `build/output/`:
   - `sach.indd`: file dàn trang hoàn chỉnh để tinh chỉnh.
   - `sach.pdf`: chỉ xuất khi không có lỗi.
   - `indesign_report.json`: lỗi/cảnh báo, trang bắt đầu/kết thúc của từng chương.

## 3. Tinh chỉnh — những điều KHÔNG được làm

- Không sửa, xóa, thêm chữ (kể cả "sửa lỗi chính tả"): mọi thay đổi nội dung phải sửa ở bản thảo rồi dựng lại.
  `htl verify` sẽ phát hiện mọi khác biệt.
- Không để chữ tràn khung (dấu + đỏ).
- Không đổi ảnh sang RGB, không scale ảnh lên quá 100% so với kích thước đặt
  (xem *Effective PPI* trong bảng Links ≥ 300).

Được làm: chỉnh vị trí ảnh, kích thước ảnh (trong giới hạn ppi), ngắt trang, khoảng cách,
tracking/kerning để tránh dòng mồ côi/góa, đổi master, thêm trang trắng.

## 4. Xuất PDF cuối

File > Export > Adobe PDF (Print), preset **HTL Offset PDF-X4** (script đã tạo sẵn).
Sau đó gửi file PDF cho người vận hành chạy `htl verify` và `htl preflight`.
