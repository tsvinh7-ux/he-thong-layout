# Định dạng JSON đầu vào (dành cho hệ thống dịch bằng Claude)

Hệ thống dịch nên xuất bản dịch theo định dạng này. Khi đó cấu trúc sách (tiêu đề, bảng, chú thích…)
được giữ chính xác từ bản gốc, không phải đoán lại từ Word hay PDF. Ví dụ đầy đủ: `examples/sach-mau.json`.

```jsonc
{
  "title": "Tên sách",
  "chapters": [
    { "id": "ch01", "source": "tên file/chương gốc", "blocks": [ /* block theo đúng thứ tự đọc */ ] }
  ]
}
```

Nhiều file JSON (mỗi file một hoặc nhiều chương) được ghép theo thứ tự tên file.

## Block

### `paragraph`

```jsonc
{
  "type": "paragraph",
  "role": "body",          // xem bảng vai trò
  "level": 1,              // cấp danh sách (1..3), chỉ dùng cho list_*
  "label": "1.\t",         // nhãn đánh số CỐ ĐỊNH (nếu có) — là một phần nội dung
  "runs": [ /* run */ ]
}
```

### `run` (đoạn chữ cùng định dạng)

```jsonc
{ "text": "HbA", "bold": false, "italic": false, "underline": false,
  "sup": false, "sub": false, "smallcaps": false, "caps": false }
```

Chú thích chân trang là một run đặc biệt, đặt đúng vị trí số chú thích trong câu:

```jsonc
{ "footnote": [ { "type": "paragraph", "role": "footnote", "runs": [ { "text": "Nội dung chú thích." } ] } ] }
```

Ký tự đặc biệt trong `text`: `\t` (tab), ` ` (xuống dòng mềm, không tách đoạn), ` ` (cách không ngắt).

### `figure`

```jsonc
{ "type": "figure", "image": "anh-goc/fig03-01.tif", "source_name": "Figure 3.1" }
```

`image` là đường dẫn tương đối so với file JSON (hoặc đường dẫn tuyệt đối). Chú thích hình là một
`paragraph` với `role: "caption"` đặt ngay sau (hoặc trước) block hình.

### `table`

```jsonc
{
  "type": "table",
  "header_rows": 1,                 // số hàng tiêu đề (lặp lại khi bảng sang trang)
  "col_widths": [0.4, 0.3, 0.3],    // tỉ lệ bề rộng cột
  "rows": [
    [ {"blocks": [ /* paragraph */ ], "colspan": 2}, {"covered": true}, {"blocks": [...]} ],
    ...
  ]
}
```

Mỗi hàng phải có đủ số ô theo lưới. Ô bị gộp (nằm dưới `colspan`/`rowspan` của ô khác) ghi
`{"covered": true}`.

## Vai trò (`role`)

| role | Ý nghĩa |
|---|---|
| `chapter_number`, `chapter_title` | Số chương, tên chương |
| `h1` … `h4` | Tiêu đề mục các cấp |
| `body` | Đoạn văn thường (hệ thống tự chọn `body_first` cho đoạn đầu sau tiêu đề) |
| `list_bullet`, `list_number` | Danh sách (số thứ tự đặt trong `label`) |
| `quote` | Trích dẫn |
| `box_title`, `box` | Khung nội dung (Key points, Clinical pearls…) |
| `caption`, `table_caption`, `table_note` | Chú thích hình, tên bảng, ghi chú dưới bảng |
| `table_head`, `table_body` | Chữ trong ô bảng |
| `reference` | Tài liệu tham khảo |
| `footnote` | Đoạn trong chú thích chân trang |

## Yêu cầu với hệ thống dịch

1. **Giữ đúng thứ tự** block như bản gốc; không gộp/tách đoạn tùy ý.
2. **Không bỏ sót**: mọi đoạn, ô bảng, chú thích hình, chú thích chân trang của bản gốc đều có bản dịch.
3. Số chú thích, số trích dẫn (`12` dạng `sup`) giữ nguyên vị trí.
4. Tên thuốc, liều, đơn vị, ký hiệu (μg, ≥, ±, α, β) giữ nguyên ký tự Unicode, không dùng font Symbol.
5. Văn bản ở dạng Unicode NFC (hệ thống vẫn tự chuẩn hóa lại).
