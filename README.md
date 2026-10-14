# HTL — Hệ thống dàn trang sách tự động

**Bản thảo (Word từ Trados, hoặc JSON từ hệ thống dịch Claude) → file InDesign (.indd) dàn sẵn → PDF/X in offset (CMYK)**

Máy làm phần lớn việc dàn trang. Đội layout chỉ mở file `.indd` để tinh chỉnh rồi xuất PDF.
Bất kể ai sửa gì, bước **đối chiếu nội dung** luôn chứng minh được PDF khớp 100% bản thảo:
không thiếu, không thừa, đúng thứ tự.

Dòng sách đang tập trung: **sách y khoa dịch có bản quyền nước ngoài**.

---

## Quy trình

```
 Bản thảo .docx (Trados)  ─┐
 hoặc JSON (hệ thống dịch) ─┤
 + thư mục ảnh gốc          │
                            ▼
 ┌──────────────────────── htl build ────────────────────────┐
 │ 1. Đọc bản thảo -> cấu trúc (chương, tiêu đề, đoạn, bảng,  │
 │    hình, chú thích chân trang, danh sách...)               │
 │ 2. Chuẩn hóa Unicode tiếng Việt (NFC), font Symbol -> Unicode│
 │ 3. Ghép ảnh gốc độ phân giải cao, kiểm tra ppi, chuyển CMYK │
 │ 4. Sinh story ICML cho từng chương + script InDesign       │
 │ 5. Báo cáo: lỗi/cảnh báo, style Word chưa ánh xạ           │
 └────────────────────────────────────────────────────────────┘
                            ▼
 InDesign: chạy run_in_indesign.jsx  (1 cú nhấp)
   - mở file mẫu .indt, đặt từng chương, tự thêm trang
   - đặt ảnh, gộp ô bảng, chú thích chân trang
   - kiểm tra chữ tràn (overset), font thiếu, link ảnh
   - lưu output/sach.indd + xuất output/sach.pdf (PDF/X-4)
                            ▼
 Đội layout tinh chỉnh trong InDesign (nếu cần) -> xuất lại PDF
                            ▼
 htl verify   : PDF khớp bản thảo 100%? (thiếu / thừa / sai thứ tự)
 htl preflight: PDF/X, bleed, font nhúng, ppi ảnh, RGB, tổng lượng mực
                            ▼
 Gửi nhà in
```

## Cài đặt

Máy chạy bước `build`/`verify`/`preflight` (Windows/Mac/Linux đều được):

```bash
python -m pip install -e .            # Python 3.10+
```

Máy designer: **Adobe InDesign CC 2019 trở lên** (đã có sẵn), cài font dùng trong mẫu
và ICC profile CMYK của nhà in.

## Sử dụng

```bash
# 0. (Một lần cho mỗi NXB nước ngoài) xem style Word đang dùng để lập bảng ánh xạ
htl inspect du-an/sach-01/ban-thao/

# 1. Dựng gói InDesign (thư mục: đọc theo thứ tự tên ch1, ch2, ..., ch10)
htl build du-an/sach-01/ban-thao/ \
    -t templates/y-khoa-19x27 \
    -o du-an/sach-01/build \
    --title "Tim mạch học lâm sàng" \
    --images du-an/sach-01/anh-goc          # ảnh gốc độ phân giải cao (tùy chọn)

#    -> đọc du-an/sach-01/build/report.md, xử lý hết mục [LỖI]

# 2. Trong InDesign: File > Scripts > Browse... chọn build/run_in_indesign.jsx
#    -> build/output/sach.indd, build/output/sach.pdf, build/output/indesign_report.json

# 3. Sau khi designer tinh chỉnh và xuất PDF cuối:
htl verify du-an/sach-01/build du-an/sach-01/build/output/sach.pdf
htl preflight du-an/sach-01/build/output/sach.pdf -t templates/y-khoa-19x27
```

Mã thoát khác 0 nghĩa là **có lỗi**; khi đó không gửi file đi in.

## Bảo đảm "không thêm, không bớt, đúng thứ tự"

| Rủi ro | Cách hệ thống xử lý |
|---|---|
| Track changes còn sót trong Word | Báo **lỗi**; chỉ chấp nhận khi chạy với `--accept-changes` |
| Chữ ẩn (hidden text, mã Trados `tw4winMark`) | Không đưa vào sách, có ghi trong báo cáo |
| Số thứ tự danh sách do Word tự sinh | Được "đóng cứng" thành chữ (1., 2., a)…) để không bị đánh lại sai |
| Chữ Hy Lạp gõ bằng font Symbol (α, β, μ) | Đổi sang Unicode chuẩn; ký tự không đổi được là **lỗi** |
| Dấu tiếng Việt tổ hợp (NFD) | Chuẩn hóa NFC |
| Text box trong Word | Đưa vào dòng chính với vai trò `box`, không bị nhân đôi |
| Biểu đồ/SmartArt nhúng, ảnh WMF/EMF | Báo **lỗi**: cần ảnh gốc |
| Chữ tràn khung (overset) trong InDesign | Script tự thêm trang; còn tràn là **lỗi** |
| Ảnh chưa đặt | Mốc `##HTLFIG0001##` hiện trên trang → `verify` báo lỗi |
| Designer lỡ xóa/sửa/chèn chữ khi tinh chỉnh | `htl verify` so PDF với bản thảo: chỉ ra từng chỗ thiếu/thừa |

`verify` không phân biệt hoa/thường và kiểu dấu nháy (“ ” với "), vì đó là định dạng
(All Caps, typographer's quotes), không phải nội dung. Phần được phép xuất hiện thêm trong PDF chỉ gồm:
số trang, tiêu đề chạy (trùng tiêu đề chương/mục hoặc tên sách), ký hiệu bullet, số chú thích.

## Chất lượng in offset

- **PDF/X-4** (hoặc X-1a nếu nhà in yêu cầu), Output Intent theo ICC profile của nhà in.
- Màu: ảnh RGB chuyển CMYK bằng ICC profile nhà in (perceptual + black point compensation);
  ảnh grayscale (X-quang, CT, mô học) giữ nguyên grayscale → in bằng mực K, sạch và nét.
  Chữ đen dùng swatch [Black] 100% K, overprint — không bị tách 4 màu.
- Ảnh: **không bao giờ phóng to (upscale)**. Ảnh dưới 300 ppi hiệu dụng → cảnh báo; dưới 200 → lỗi.
  PDF xuất **không giảm độ phân giải**, nén ZIP không mất dữ liệu.
- Bleed 3 mm (theo mẫu), crop marks, toàn bộ font nhúng.
- `htl preflight` kiểm: chuẩn PDF/X, TrimBox/BleedBox, khổ, font nhúng, ảnh RGB, ppi, tổng lượng mực (TAC), số trang chia hết cho 4.
  Bản cuối vẫn nên chạy thêm Acrobat Preflight / callas pdfToolbox với profile do nhà in cung cấp.

## Mẫu layout (thêm mẫu mới)

Mỗi mẫu là một thư mục trong `templates/`:

```
templates/y-khoa-19x27/
  template.yaml     # khổ, lề, bleed, cột, màu, ICC, ppi, chuẩn PDF, tên style
  style_map.yaml    # ánh xạ style Word của NXB -> vai trò
  y-khoa-19x27.indt # (khuyên dùng) file mẫu InDesign do designer làm
```

Thêm mẫu: sao chép thư mục, sửa `template.yaml`, designer làm file `.indt` theo
[docs/huong-dan-designer.md](docs/huong-dan-designer.md).
Khi chưa có `.indt`, script tự tạo tài liệu từ thông số trong `template.yaml` (đủ để chạy thử).

## Đầu vào từ hệ thống dịch bằng Claude

Khuyên dùng: hệ thống dịch xuất thẳng **JSON theo cấu trúc của HTL** thay vì Word/PDF.
Đặc tả ở [docs/dinh-dang-json.md](docs/dinh-dang-json.md), ví dụ ở [examples/sach-mau.json](examples/sach-mau.json).

Lý do: PDF chỉ lưu vị trí chữ trên trang, không lưu cấu trúc (đâu là tiêu đề, chú thích, ô bảng…).
Đọc lại PDF luôn có rủi ro sai thứ tự hoặc mất chữ. Nếu bản gốc tiếng Anh là PDF, hãy để
hệ thống dịch đọc PDF gốc và xuất JSON có cấu trúc. Khi đó cấu trúc được xác định một lần, ngay lúc dịch.

## Cấu trúc mã nguồn

```
htl/
  readers/docx_reader.py  Đọc Word: style, run, danh sách, bảng gộp ô, chú thích, ảnh, text box, field
  readers/__init__.py     Đọc thư mục/nhiều file, JSON
  ir.py                   Mô hình dữ liệu trung gian
  structure.py            Nhận diện chú thích hình/bảng, chia chương, đánh mã hình
  images.py               Ghép ảnh gốc, kích thước, ppi, chuyển CMYK
  icml.py                 Sinh story ICML cho InDesign
  build.py                Điều phối bước build
  verify.py               Đối chiếu nội dung PDF với bản thảo
  preflight.py            Kiểm tra kỹ thuật PDF
indesign/htl_build.jsx    Script InDesign (ExtendScript)
templates/                Các mẫu layout
tests/                    Kiểm thử tự động (pytest)
```

Chạy kiểm thử: `python -m pytest`.

## Trạng thái hiện tại

- Phần Python (đọc Word, ảnh, ICML, verify, preflight) đã có test tự động.
- Script InDesign đã kiểm tra cú pháp nhưng **cần chạy thử trên InDesign thật** với bản thảo thật
  (đợt đầu nên làm 1–2 chương). Lỗi phát sinh sẽ hiện trong `output/indesign_report.json`.
- Chưa làm: đọc trực tiếp PDF làm đầu vào (xem lý do ở trên), tiêu đề chạy tự động
  (đặt trong master page của file `.indt`), mục lục/chỉ mục (InDesign tạo từ style tiêu đề).
