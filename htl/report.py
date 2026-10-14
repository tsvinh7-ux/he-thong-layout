"""Thu thập cảnh báo/lỗi trong quá trình dựng, xuất báo cáo cho người duyệt."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    style_usage: Counter = field(default_factory=Counter)  # (style, role) -> số đoạn
    unmapped_styles: Counter = field(default_factory=Counter)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_markdown(self, title: str = "Báo cáo dựng sách") -> str:
        lines = [f"# {title}", ""]
        lines.append(f"**Kết quả:** {'ĐẠT' if self.ok else 'CÓ LỖI — phải xử lý trước khi dàn trang'}")
        lines.append("")
        for head, items in (("Lỗi", self.errors), ("Cảnh báo", self.warnings), ("Thông tin", self.infos)):
            lines.append(f"## {head} ({len(items)})")
            lines += [f"- {m}" for m in items] or ["- (không có)"]
            lines.append("")
        if self.unmapped_styles:
            lines.append("## Style Word chưa có trong bảng ánh xạ (đang xử lý như đoạn thường)")
            lines.append("Bổ sung các style này vào `style_map.yaml` của dự án nếu cần vai trò khác.")
            lines.append("")
            for s, n in self.unmapped_styles.most_common():
                lines.append(f"- `{s}`: {n} đoạn")
            lines.append("")
        if self.style_usage:
            lines.append("## Thống kê style -> vai trò")
            lines.append("")
            lines.append("| Style Word | Vai trò | Số đoạn |")
            lines.append("|---|---|---|")
            for (s, r), n in sorted(self.style_usage.items(), key=lambda x: -x[1]):
                lines.append(f"| {s or '(không style)'} | {r} | {n} |")
            lines.append("")
        return "\n".join(lines)
