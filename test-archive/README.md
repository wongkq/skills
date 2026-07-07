# test-archive

> Claude Code Skill — 测试方案/数据/报告三件套归档

为工程测试建立统一的归档结构 `wkq/NN_<简述>/{plan,data,report}/`，自动编号、模板渲染、确保每轮测试产出可追溯。

**入口文档：[SKILL.md](./SKILL.md)** — 这是 Claude 读取的入口（含 frontmatter 触发描述）。

## 文档导览

| 文档 | 内容 |
|---|---|
| [**SKILL.md**](./SKILL.md) | **Skill 入口** — 触发条件、目录规则、CLI 速查、FAQ |
| [references/workflow.md](./references/workflow.md) | 完整 7 步工作流，含部署占位说明 |
| [references/naming.md](./references/naming.md) | 编号、目录名、文件名命名规范 |
| [references/checklist.md](./references/checklist.md) | 开工/执行中/收尾检查清单 |
| [templates/test_plan.md](./templates/test_plan.md) | 测试方案模板 |
| [templates/test_report.md](./templates/test_report.md) | 测试报告模板 |
| [examples/sample_workflow.md](./examples/sample_workflow.md) | 端到端 shell 轨迹示例 |

## 一句话接入

```bash
cd <工程根目录>
python -m test_archive new "登录接口回归测试"
python -m test_archive render 1 plan  --subject "登录接口回归测试"
# ... 填充方案、执行测试、落 data/ ...
python -m test_archive render 1 report --subject "登录接口回归测试"
```

## 文件结构

```
test-archive/                         # Skill 根目录
├── SKILL.md                           # ← Claude 入口（必须）
├── README.md                          # ← 本文件
├── test_archive/                      # Python 实现包（纯 stdlib）
│   ├── __init__.py / __main__.py
│   ├── cli.py                         # argparse 子命令
│   ├── batch.py                       # 编号生成、批次目录管理
│   ├── workspace.py                   # 高层工作区接口
│   └── templates.py                   # 模板渲染
├── templates/                         # Markdown 模板
│   ├── test_plan.md
│   └── test_report.md
├── references/                        # 详细参考文档（按需加载）
│   ├── workflow.md
│   ├── naming.md
│   └── checklist.md
└── examples/                          # 使用示例
    └── sample_workflow.md
```

## 30 秒上手

```bash
# 1. 列出现有批次（首次为空）
python -m test_archive list

# 2. 新建批次
python -m test_archive new "登录接口回归测试"

# 3. 渲染方案模板，填充后让用户确认
python -m test_archive render 1 plan --subject "登录接口回归测试"

# 4. 执行测试，过程产出存到 data/
#    （命名规范：caseNN_<描述>.<ext>，小写英文）

# 5. 渲染并填充报告
python -m test_archive render 1 report --subject "登录接口回归测试"
```

## 设计要点

- **纯 Python stdlib**：无第三方依赖，部署到任何测试服务器即可用。
- **强制三件套**：方案/数据/报告分目录存放，子目录职责不可混。
- **自动编号**：从 01 起，两位补零；超过 99 自动升三位。
- **模板渲染**：`{{ batch_name }}` `{{ generated_at }}` 等占位符自动填充，未提供的留 `TODO:`。
- **不覆盖已有文件**：渲染时若目标文件已存在会报错，避免误删人工填充的内容。
- **不内置部署**：服务器信息属于用户工程知识，由用户提供；skill 只管 wkq/ 结构。

## License

MIT
