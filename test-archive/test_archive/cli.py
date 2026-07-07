"""test-archive CLI 入口。

子命令：
  init                                  确保 wkq/ 存在
  new <简述>                            新建批次目录（自动编号）
  list                                  列出已有批次
  resume <编号或简述>                    复用已有批次
  render <编号或简述> plan|report        渲染模板到批次目录

可选：
  --root <path>     工作根目录（默认当前目录）
  --json            以 JSON 输出（便于 agent 解析）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .batch import BatchError, BatchManager
from .templates import TemplateError, TemplateRenderer
from .workspace import Workspace


def _emit(data: dict, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        for line in _format_human(data):
            sys.stdout.write(line + "\n")


def _format_human(data: dict) -> list[str]:
    op = data.get("op")
    if op == "init":
        return [f"已就绪: {data['wkq']}"]
    if op == "new":
        b = data["batch"]
        return [
            f"已创建批次: {b['name']}",
            f"  路径: {b['path']}",
            "  子目录:",
            f"    plan/   → {b['plan']}",
            f"    data/   → {b['data']}",
            f"    report/ → {b['report']}",
        ]
    if op == "list":
        items = data["batches"]
        if not items:
            return [f"暂无批次。wkq 根目录: {data['wkq']}"]
        lines = [f"共 {len(items)} 个批次（{data['wkq']}）:"]
        for b in items:
            lines.append(f"  {b['name']}    {b['path']}")
        return lines
    if op == "resume":
        b = data["batch"]
        return [
            f"已定位批次: {b['name']}",
            f"  路径: {b['path']}",
            "  可继续追加内容到 plan/ data/ report/。",
        ]
    if op == "render":
        return [
            f"已渲染: {data['template']} → {data['dest']}",
            f"  批次: {data['batch_name']}",
        ]
    return [json.dumps(data, ensure_ascii=False)]


def _batch_to_dict(batch) -> dict:
    return {
        "name": batch.name,
        "index": batch.index,
        "desc": batch.desc,
        "path": str(batch.path),
        "plan": str(batch.subdir("plan")),
        "data": str(batch.subdir("data")),
        "report": str(batch.subdir("report")),
    }


def _err(message: str, as_json: bool) -> int:
    if as_json:
        sys.stdout.write(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stderr.write(f"error: {message}\n")
    return 1


def cmd_init(args, ws: Workspace) -> int:
    wkq = ws.mgr.ensure_root()
    _emit({"op": "init", "ok": True, "wkq": str(wkq)}, args.json)
    return 0


def cmd_new(args, ws: Workspace) -> int:
    try:
        batch = ws.new_batch(args.desc)
    except BatchError as e:
        return _err(str(e), args.json)
    _emit({"op": "new", "ok": True, "batch": _batch_to_dict(batch)}, args.json)
    return 0


def cmd_list(args, ws: Workspace) -> int:
    batches = ws.mgr.list_batches()
    _emit(
        {
            "op": "list",
            "ok": True,
            "wkq": str(ws.mgr.wkq),
            "batches": [
                {
                    "name": b.name,
                    "index": b.index,
                    "desc": b.desc,
                    "path": str(b.path),
                }
                for b in batches
            ],
        },
        args.json,
    )
    return 0


def cmd_resume(args, ws: Workspace) -> int:
    try:
        batch = ws.resume_batch(args.query)
    except BatchError as e:
        return _err(str(e), args.json)
    _emit({"op": "resume", "ok": True, "batch": _batch_to_dict(batch)}, args.json)
    return 0


def cmd_render(args, ws: Workspace) -> int:
    if args.kind not in ("plan", "report"):
        return _err(f"kind 必须是 plan 或 report，收到: {args.kind}", args.json)
    try:
        batch = ws.resume_batch(args.query)
    except BatchError as e:
        return _err(str(e), args.json)

    template_name = "test_plan.md" if args.kind == "plan" else "test_report.md"
    try:
        renderer = TemplateRenderer()
    except TemplateError as e:
        return _err(str(e), args.json)

    filename = args.out or ("test_plan.md" if args.kind == "plan" else "test_report.md")
    dest = batch.subdir(args.kind) / filename

    extra = {}
    if args.subject:
        extra["subject"] = args.subject

    try:
        renderer.render_to(template_name, batch, ws.root, dest, extra=extra)
    except TemplateError as e:
        return _err(str(e), args.json)

    _emit(
        {
            "op": "render",
            "ok": True,
            "batch_name": batch.name,
            "template": template_name,
            "dest": str(dest),
        },
        args.json,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="test_archive",
        description="wkq/ 批次目录三件套管理工具",
    )
    p.add_argument("--root", default=".", help="工作根目录（默认当前目录）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="确保 wkq/ 存在").set_defaults(func=cmd_init)

    sp_new = sub.add_parser("new", help="新建批次目录（自动编号）")
    sp_new.add_argument("desc", help="批次简述，例如 登录接口回归测试")
    sp_new.set_defaults(func=cmd_new)

    sub.add_parser("list", help="列出已有批次").set_defaults(func=cmd_list)

    sp_resume = sub.add_parser("resume", help="复用已有批次")
    sp_resume.add_argument("query", help="编号 / 简述 / 完整目录名")
    sp_resume.set_defaults(func=cmd_resume)

    sp_render = sub.add_parser("render", help="渲染模板到批次子目录")
    sp_render.add_argument("query", help="批次编号 / 简述 / 完整目录名")
    sp_render.add_argument("kind", choices=["plan", "report"], help="渲染到 plan/ 还是 report/")
    sp_render.add_argument("--out", default=None, help="输出文件名（默认 test_plan.md / test_report.md）")
    sp_render.add_argument("--subject", default=None, help="填充模板中的 {{ subject }} 占位符")
    sp_render.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ws = Workspace(args.root)
    rc: int = args.func(args, ws)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
