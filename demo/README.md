# Demo: 2 chương sách y khoa → gói InDesign + PDF xem trước

> Nội dung và hình trong demo do máy soạn/vẽ để minh họa quy trình, **không dùng làm tài liệu chuyên môn**.
> Ảnh "X-quang" là ảnh tổng hợp, không phải ảnh bệnh nhân.

## Chạy

```bash
python -m pip install -e .        # ở thư mục gốc repo (một lần)
python demo/chay_demo.py
```

## Đầu vào

| Thư mục | Nội dung |
|---|---|
| `ban-thao/chuong-01.docx`, `chuong-02.docx` | Bản thảo Word (giả lập file dịch nhận về): tiêu đề, khung "Điểm chính", bảng, danh sách, trích dẫn, chú thích chân trang, tài liệu tham khảo, chỉ số trên/dưới (Na⁺, HbA₁c) |
| `nguon/anh-nhung/` | Ảnh nhúng trong Word: **độ phân giải thấp** (như bản thảo thật) |
| `anh-goc/` | Ảnh gốc độ phân giải cao (tạo tự động khi chạy demo). Hình 2.2 **cố ý không có ảnh gốc** để thấy cảnh báo |
| `nguon/*.md` | Nguồn soạn bản thảo (tạo lại .docx bằng `python demo/tao_du_lieu_demo.py`, cần pandoc) |

## Kết quả (`ket-qua/`)

| File | Là gì |
|---|---|
| `goi-indesign.zip` | **Gói dựng cho InDesign**: giải nén, mở InDesign → File > Scripts > Browse… → `run_in_indesign.jsx` → ra `output/sach.indd` + `output/sach.pdf` (PDF/X-4) |
| `xem-truoc.pdf` | PDF xem trước dựng không cần InDesign — để duyệt nội dung, **không dùng để in** |
| `bao-cao-dung.md` | Báo cáo bước dựng: ảnh gốc được ghép, ảnh thiếu chất lượng, style… |
| `doi-chieu.md` | Đối chiếu PDF xem trước với bản thảo: khớp 100% |
| `doi-chieu-ban-bi-sua.md` | Thử xóa cụm "1,28 tỷ" khỏi PDF → hệ thống chỉ ra đúng chỗ thiếu |
| `preflight-xem-truoc.md` | Preflight bản xem trước: báo "không phải PDF/X" — đúng như mong đợi, vì file in phải xuất từ InDesign |

## Những gì demo cho thấy

1. Style Word được nhận diện tự động → vai trò (chương, tiêu đề, khung, bảng, chú thích…).
2. Ảnh nhúng độ phân giải thấp được **tự thay bằng ảnh gốc** nhờ khớp số hình trong chú thích ("Hình 1.1" ↔ `hinh-1-1-goc.tif`).
3. Ảnh không có bản gốc (Hình 2.2) → cảnh báo, và **không bị phóng to** quá 300 ppi.
4. Ảnh X-quang grayscale giữ nguyên grayscale (in bằng mực K).
5. Đối chiếu nội dung: khớp 1439/1439 từ; chỉ cần mất một cụm từ là bị phát hiện.

## Thay bằng dữ liệu thật

1. Đặt các file `.docx` của sách vào một thư mục (đặt tên theo thứ tự: `ch01.docx`, `ch02.docx`…).
2. `htl inspect <thư mục>` → bổ sung style của NXB vào `templates/y-khoa-19x27/style_map.yaml`.
3. Điền thông số nhà in vào `templates/y-khoa-19x27/template.yaml` (ICC profile, bleed, TAC), thêm file `.indt` của designer.
4. `htl build <thư mục> -t templates/y-khoa-19x27 -o du-an/ten-sach/build --images <thư mục ảnh gốc>`
