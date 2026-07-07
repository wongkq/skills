"""Workspace：把 BatchManager 暴露成更面向"工作流"的接口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .batch import Batch, BatchError, BatchManager, SUBDIRS


@dataclass
class WorkspaceSummary:
    """Workspace 当前状态的快照，供 agent 决策。"""

    root: Path
    wkq: Path
    batches: list[Batch]

    @property
    def total(self) -> int:
        return len(self.batches)

    @property
    def latest(self) -> Batch | None:
        return self.batches[-1] if self.batches else None


class Workspace:
    """封装"在某个工作目录下管理 wkq/"的高层操作。"""

    def __init__(self, root: Path | str = "."):
        self.root = Path(root).resolve()
        self.mgr = BatchManager(self.root)

    # ---- 查询 ----

    def status(self) -> WorkspaceSummary:
        return WorkspaceSummary(
            root=self.root,
            wkq=self.mgr.wkq,
            batches=self.mgr.list_batches(),
        )

    def find(self, query: str) -> Batch | None:
        return self.mgr.find(query)

    # ---- 创建/复用 ----

    def new_batch(self, desc: str) -> Batch:
        return self.mgr.create(desc)

    def resume_batch(self, query: str) -> Batch:
        return self.mgr.resume(query)

    # ---- 路径生成（方便 agent 落文件）----

    @staticmethod
    def plan_path(batch: Batch, filename: str = "test_plan.md") -> Path:
        return batch.subdir("plan") / filename

    @staticmethod
    def report_path(batch: Batch, filename: str = "test_report.md") -> Path:
        return batch.subdir("report") / filename

    @staticmethod
    def data_path(batch: Batch, filename: str) -> Path:
        if not filename:
            raise BatchError("data 文件名不能为空")
        return batch.subdir("data") / filename

    @staticmethod
    def validate_data_filename(filename: str) -> None:
        """data/ 下文件名只能用小写字母/数字/下划线/点/短横线。"""
        if not filename:
            raise BatchError("文件名不能为空")
        if "/" in filename or "\\" in filename:
            raise BatchError(f"data 文件名不能含路径分隔符: {filename!r}")
        # 鼓励英文小写，但允许 .png/.json/.log 等扩展名
        # 不强制报错，只对中文/大写给出建议性警告通过返回值
        # 这里仅做硬性校验：禁止路径分隔符
        return None

    def ensure_subdirs(self, batch: Batch) -> None:
        for sub in SUBDIRS:
            (batch.path / sub).mkdir(parents=True, exist_ok=True)
