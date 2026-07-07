"""批次目录的编号生成与创建。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

WKQ_ROOT = "wkq"
PLAN_DIR = "plan"
DATA_DIR = "data"
REPORT_DIR = "report"
SUBDIRS = (PLAN_DIR, DATA_DIR, REPORT_DIR)

# 目录名格式：NN_<简述>，简述只允许字母数字下划线短横线、中文
_BATCH_RE = re.compile(r"^(\d{2,3})_(.+)$")
_DESC_INVALID = re.compile(r"[\/\s]")


class BatchError(Exception):
    """批次目录相关的错误。"""


@dataclass(frozen=True)
class Batch:
    """一个已存在的批次。"""

    index: int
    width: int  # 编号位数：2 或 3
    desc: str
    path: Path

    @property
    def name(self) -> str:
        return f"{str(self.index).zfill(self.width)}_{self.desc}"

    def subdir(self, kind: str) -> Path:
        if kind not in SUBDIRS:
            raise BatchError(f"unknown subdirectory kind: {kind!r} (allowed: {SUBDIRS})")
        return self.path / kind


class BatchManager:
    """管理 wkq/ 下的批次目录。"""

    def __init__(self, root: Path | str = ".", wkq_root: str = WKQ_ROOT):
        self.root = Path(root).resolve()
        self.wkq = self.root / wkq_root

    # ---- 根目录 ----

    def ensure_root(self) -> Path:
        """确保 wkq/ 存在。"""
        self.wkq.mkdir(parents=True, exist_ok=True)
        return self.wkq

    def root_exists(self) -> bool:
        return self.wkq.is_dir()

    # ---- 扫描 ----

    def list_batches(self) -> list[Batch]:
        """按编号升序列出所有批次。"""
        if not self.root_exists():
            return []
        batches: list[Batch] = []
        for entry in self.wkq.iterdir():
            if not entry.is_dir():
                continue
            m = _BATCH_RE.match(entry.name)
            if not m:
                continue
            index = int(m.group(1))
            width = len(m.group(1))
            desc = m.group(2)
            batches.append(Batch(index=index, width=width, desc=desc, path=entry))
        batches.sort(key=lambda b: (b.index, b.name))
        return batches

    def find(self, query: str) -> Batch | None:
        """按编号、编号+简述或纯简述查找。返回首个匹配。"""
        batches = self.list_batches()
        q = query.strip()

        # 纯数字 → 视为编号
        if q.isdigit():
            idx = int(q)
            for b in batches:
                if b.index == idx:
                    return b
            return None

        # 完整目录名 NN_<简述>
        for b in batches:
            if b.name == q:
                return b

        # 仅简述（精确匹配）
        exact = [b for b in batches if b.desc == q]
        if exact:
            return exact[0]

        # 简述子串匹配（去歧义：唯一匹配才返回）
        partial = [b for b in batches if q in b.desc]
        if len(partial) == 1:
            return partial[0]
        return None

    # ---- 创建 ----

    def next_index(self) -> tuple[int, int]:
        """返回 (下一个编号, 编号位数)。从 1 开始；超过 99 用三位。"""
        batches = self.list_batches()
        if not batches:
            return 1, 2
        max_index = max(b.index for b in batches)
        nxt = max_index + 1
        # 当已存在三位编号或下一个 > 99 时，统一用三位
        width = 3 if (max_index >= 100 or nxt > 99) else 2
        return nxt, width

    @staticmethod
    def sanitize_desc(desc: str) -> str:
        """规整简述：去前后空白；空格/斜杠 → 下划线；其余保留。

        允许中文，但禁止 / 和空格以保证路径安全。
        """
        d = desc.strip()
        if not d:
            raise BatchError("批次简述不能为空")
        if _DESC_INVALID.search(d):
            raise BatchError(
                f"批次简述含非法字符（空格或斜杠）: {d!r}，请用下划线连接词组"
            )
        # 多个连续下划线合并成一个
        d = re.sub(r"_+", "_", d)
        return d

    def create(self, desc: str) -> Batch:
        """创建新批次目录，含 plan/data/report 三个子目录。"""
        self.ensure_root()
        clean_desc = self.sanitize_desc(desc)
        index, width = self.next_index()
        name = f"{str(index).zfill(width)}_{clean_desc}"
        batch_path = self.wkq / name
        if batch_path.exists():
            raise BatchError(
                f"批次目录已存在: {batch_path}（编号生成逻辑异常，请检查 wkq/）"
            )
        for sub in SUBDIRS:
            (batch_path / sub).mkdir(parents=True, exist_ok=True)
        return Batch(index=index, width=width, desc=clean_desc, path=batch_path)

    def resume(self, query: str) -> Batch:
        """复用已有批次。找不到时报错。"""
        b = self.find(query)
        if b is None:
            raise BatchError(
                f"未找到匹配的批次: {query!r}\n已有批次:\n"
                + "\n".join(f"  - {x.name}" for x in self.list_batches())
                or "  (无)"
            )
        # 确保子目录都在
        for sub in SUBDIRS:
            (b.path / sub).mkdir(parents=True, exist_ok=True)
        return b
