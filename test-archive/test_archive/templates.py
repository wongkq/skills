"""把 templates/ 下的 Markdown 模板渲染到批次目录。

模板内支持的占位符（{{ key }}）：
- batch_name     批次目录名，如 03_登录接口回归测试
- batch_index    编号数字，如 3
- batch_desc     简述，如 登录接口回归测试
- root           工作根目录绝对路径
- generated_at   渲染时间，UTC+8
- subject        测试目标/主题（可由 CLI --subject 传入，可选）

未提供的占位符保留为 TODO: <key>，方便人工补全。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .batch import Batch

_TZ_CN = timezone(timedelta(hours=8))
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
TODO_PREFIX = "TODO:"


class TemplateError(Exception):
    """模板渲染错误。"""


class TemplateRenderer:
    """从 skill 安装目录下的 templates/ 渲染模板到批次子目录。"""

    def __init__(self, templates_dir: Path | str | None = None):
        if templates_dir is None:
            # 默认：<本文件所在目录>/../templates
            here = Path(__file__).resolve().parent
            templates_dir = here.parent / "templates"
        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.is_dir():
            raise TemplateError(
                f"templates 目录不存在: {self.templates_dir}"
            )

    def available(self) -> list[str]:
        return sorted(p.name for p in self.templates_dir.glob("*.md"))

    def render(
        self,
        template_name: str,
        batch: Batch,
        root: Path,
        extra: dict[str, str] | None = None,
    ) -> str:
        tpl_path = self.templates_dir / template_name
        if not tpl_path.is_file():
            available = ", ".join(self.available()) or "(无)"
            raise TemplateError(
                f"模板不存在: {template_name}（可用: {available}）"
            )
        text = tpl_path.read_text(encoding="utf-8")

        context = {
            "batch_name": batch.name,
            "batch_index": str(batch.index),
            "batch_desc": batch.desc,
            "root": str(root),
            "generated_at": datetime.now(_TZ_CN).strftime("%Y-%m-%d %H:%M:%S %z"),
        }
        if extra:
            context.update(extra)

        def _sub(m: re.Match) -> str:
            key = m.group(1)
            if key in context:
                return context[key]
            return f"{TODO_PREFIX} {key}"

        return _PLACEHOLDER.sub(_sub, text)

    def render_to(
        self,
        template_name: str,
        batch: Batch,
        root: Path,
        dest: Path,
        extra: dict[str, str] | None = None,
    ) -> Path:
        """渲染并写入 dest；若 dest 已存在则不覆盖（报错）。"""
        if dest.exists():
            raise TemplateError(f"目标文件已存在，拒绝覆盖: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = self.render(template_name, batch, root, extra=extra)
        dest.write_text(text, encoding="utf-8")
        return dest
