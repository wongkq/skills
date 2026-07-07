---
name: test-archive
description: Use this skill when the user wants to design a test plan, deploy source code to a test server and run tests, execute/re-run a test plan, or produce a test report for an engineering project. Triggers include "测试一下这个工程", "给这个功能出个测试方案并测试", "部署到测试服务器跑一下测试", "继续之前的测试方案", "整理一下测试报告", "测试归档", "测试记录", "wkq 目录", "回归测试", "补测上一轮", or any request to organize test plan/data/report artifacts into a structured archive. The skill enforces a fixed directory layout — wkq/NN_<简述>/{plan,data,report}/ — auto-increments batch numbers, renders plan/report Markdown templates, and ensures every test round's deliverables are traceable and never mixed across batches or with project source code. Pure Python, no third-party dependencies.
version: 1.0.0
license: MIT
---

# test-archive Skill

为工程测试建立统一的归档结构：`wkq/NN_<简述>/{plan,data,report}/` 三件套。每一轮独立的测试方案对应一个批次目录，方案、原始数据、结论性报告严格分目录存放，可追溯、不混放。

## When to use this skill

- **设计测试方案** — 用户说"出个测试方案"、"帮我测一下这个工程"
- **部署后执行测试** — "部署到测试服务器跑一下测试"、"跑一下用例"
- **复用已有方案做补测/回归** — "继续跑之前的方案"、"补测上一轮"、"回归一下"
- **整理测试报告** — "整理一下测试报告"、"出个报告"
- **归档相关** — 用户提到"测试归档"、"测试记录"、"wkq 目录"

## 核心规则：目录结构（强制）

```
wkq/
  01_<方案简述>/
    plan/       # 测试方案文档
    data/       # 测试过程数据、日志、接口返回、截图等原始产出
    report/     # 测试报告（结论性文档）
  02_<方案简述>/
    plan/
    data/
    report/
  ...
```

- 所有测试产出**必须**归档在 `wkq/` 下，不得散落工程其他位置或与源码混放。
- 三个子目录职责不可混淆：方案→`plan/`、原始数据→`data/`、结论→`report/`。
- 每一轮独立测试方案对应一个批次目录；新的方案/版本/场景必须新建批次，不要并入旧的。

## 标准工作流

### 0. 判定新建 vs 复用

| 用户说法 | 处理 |
|---|---|
| "测试一下"、"出方案"、"部署后跑" | **新建**批次 |
| "继续跑之前的方案"、"补测"、"回归" | **复用**已有批次 |
| "整理报告"但已有方案与数据 | **复用**已有批次 |

判断不准时**先问用户**，不要臆测。

### 1. 检查并创建批次

```bash
cd <工程根目录>
python -m test_archive list                  # 先看现有批次，避免编号冲突
python -m test_archive new "<简述>"           # 例: new "登录接口回归测试"
```

编号自动从 1 开始，两位补零（01, 02…）；超过 99 自动升三位。

### 2. 部署源码（如用户要求）

**Skill 不内置部署逻辑** — 服务器信息属于用户工程知识，必须由用户提供。

- 若用户**未提供**服务器地址、账号、部署方式 → **先问**，不要臆造
- 部署过程输出保存到 `data/deploy.log`
- 部署后做一次健康检查，结果追加到 `deploy.log`

### 3. 写测试方案

```bash
python -m test_archive render <编号或简述> plan --subject "<测试主题>"
```

模板渲染到 `plan/test_plan.md`，自动填充批次名/工作目录/生成时间。随后填充：

- 测试目标与范围
- 用例列表（编号 case01, case02…，每条带预期结果）
- 测试环境说明
- 风险与回退

**写完让用户确认方案**，除非用户明确"自动执行、无需确认"。

### 4. 执行测试，落原始数据

按方案逐条执行，过程产出存到 `data/`，文件名以用例编号开头：

```
data/case01_output.log
data/case02_response.json
data/case03_screenshot.png
data/deploy.log
```

文件名规范：小写字母 + 数字 + 下划线，可含 `.log` `.json` `.png` 等扩展。**不要用中文文件名**（目录名可中文，内部文件名英文/拼音）。

### 5. 生成测试报告

```bash
python -m test_archive render <编号或简述> report --subject "<测试主题>"
```

填充报告：

- 执行总结（通过/失败/阻塞数量、通过率）
- 每条用例结论，**必须引用 `data/` 下对应的证据文件路径**
- 失败/阻塞用例的现象、可能原因、复现步骤
- 缺陷清单（bug-01, bug-02…）
- 结论与建议

### 6. 收尾说明

向用户**简要**汇报：整体结论、关键缺陷、产出物路径。不要复述报告全文。

## 编号与命名规则

| 项 | 规则 |
|---|---|
| 批次编号 | 从 01 起，两位补零；超过 99 自动升三位 |
| 简述 | 中文短语或英文短语，词间用 `_` 连接；**不含空格、斜杠** |
| data/ 文件名 | `caseNN_<描述>.<ext>`，小写字母+数字+下划线 |
| plan/ 默认文件 | `test_plan.md` |
| report/ 默认文件 | `test_report.md` |
| 多轮执行区分 | `caseNN_runM_*`；旧版报告 `test_report_v1.md` 等 |

详细规则见 `references/naming.md`。

## CLI 速查

```bash
python -m test_archive [--root DIR] [--json] <subcommand>

subcommands:
  init                                   确保 wkq/ 存在
  new <简述>                             新建批次目录（自动编号）
  list                                   列出所有批次
  resume <编号|简述|完整名>              定位/复用已有批次
  render <编号|简述|完整名> plan|report  渲染模板到批次子目录
       [--out FILE] [--subject TEXT]
```

`--root` 默认当前目录；`--json` 输出 JSON 便于 agent 解析。

## 安装

无需安装依赖，纯 Python stdlib。把 `test-archive/` 放到 skills 目录（或 PYTHONPATH 包含的路径），即可 `python -m test_archive ...`。

若 `python -m test_archive` 报 ModuleNotFoundError，把 skill 根目录加入 PYTHONPATH：

```bash
export PYTHONPATH=/path/to/test-archive:$PYTHONPATH
python -m test_archive list
```

## 注意事项

- **不内置部署**：测试服务器、账号、部署方式由用户提供，skill 只负责 wkq/ 结构。
- **不混批次**：每个新方案/版本/场景必须新建批次；用户明确"继续之前的"才复用。
- **不臆造**：方案中的环境信息（服务器地址、版本号、commit）填不上时，留 TODO 并向用户确认，不要瞎写。
- **不复述报告**：收尾时只给路径和结论，让用户去读文件。
- **不跳过确认**：方案写完必须给用户看（除非已明确"自动执行"）。

## Reference files（按需加载）

| 文件 | 何时读 |
|---|---|
| `references/workflow.md` | 完整 7 步工作流细节，含部署占位说明 |
| `references/naming.md` | 编号、目录名、文件名的完整规则与示例 |
| `references/checklist.md` | 开工前/执行中/收尾前的检查清单 |
| `templates/test_plan.md` | 测试方案模板（render plan 时复制） |
| `templates/test_report.md` | 测试报告模板（render report 时复制） |
| `examples/sample_workflow.md` | 端到端 shell 轨迹示例 |

## FAQ

**Q: 用户说"接着上一轮测"，是新建还是复用？**
A: 复用。用 `python -m test_archive resume <上一轮编号或简述>` 定位批次，新产出追加到 `data/`（用 `caseNN_run2_*` 区分），旧报告另存为 `test_report_v1.md`，新版用 `test_report.md`。

**Q: 编号已经到 99 了怎么办？**
A: 第 100 个会自动用三位 `100_<简述>`，之后都是三位。已存在的两位编号保持不变。

**Q: 我想给同一轮方案写两份方案文档（接口测试 + 性能测试）怎么办？**
A: 同一批次内允许并存多份方案，但至少保留一份 `test_plan.md` 作为索引；其余用 `interface_test_plan.md`、`perf_test_plan.md` 等命名。

**Q: 部署到测试服务器失败，日志写哪？**
A: 写到 `data/deploy.log`。报告里"环境与版本信息"表填实际部署结果，失败用例作为阻塞用例记录。

**Q: 跟 `backup-sync` skill 怎么配合？**
A: 在多人共享服务器上，跑完一轮测试后用 `backup-sync` 把整个 `wkq/` 推送到 GitHub，防止他人误删。详见 `backup-sync` skill 的 SKILL.md。

**Q: 模板里的 `{{ subject }}` 占位符没传会怎样？**
A: 渲染时会保留为 `TODO: subject`，方便人工补全，不会报错。
