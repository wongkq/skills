# 端到端示例 — 一轮测试的完整轨迹

> 本文件演示从用户提需求到出报告的完整 shell 轨迹，供 agent 模仿。

## 场景

用户说："帮我测一下登录接口，部署到测试服务器上跑，然后出报告。"

## 0. 先看现有批次

```bash
$ cd /srv/projects/auth-service
$ python -m test_archive list
暂无批次。wkq 根目录: /srv/projects/auth-service/wkq
```

## 1. 问用户服务器信息

> Skill 不内置部署逻辑。Claude 必须先向用户确认：
>
> - 测试服务器地址、登录方式？
> - 部署方式：git pull / rsync / 已有脚本？
> - 是否清理旧部署？

用户回答后，把回答写进方案的环境表。

## 2. 新建批次

```bash
$ python -m test_archive new "登录接口回归测试"
已创建批次: 01_登录接口回归测试
  路径: /srv/projects/auth-service/wkq/01_登录接口回归测试
  子目录:
    plan/   → .../plan
    data/   → .../data
    report/ → .../report
```

## 3. 渲染方案模板

```bash
$ python -m test_archive render "1" plan --subject "登录接口回归测试"
已渲染: test_plan.md → .../plan/test_plan.md
  批次: 01_登录接口回归测试
```

打开 `plan/test_plan.md`，按 TODO 标记填充：

- 测试目标：验证登录接口在 v1.2.3 上的成功/失败路径
- 用例：
  - case01 正确账号密码 → 200 + token
  - case02 错误密码 → 401
  - case03 锁定账号 → 423
- 环境：测试服务器 10.0.0.5，部署方式 git pull origin v1.2.3
- 产出物清单

**写完后请用户确认方案**，再继续。

## 4. 部署 + 执行测试，落原始数据

```bash
# 部署（按用户给的方式）
$ ssh deploy@10.0.0.5 'cd /opt/auth-service && git fetch && git checkout v1.2.3 && systemctl restart auth-service' \
    > wkq/01_登录接口回归测试/data/deploy.log 2>&1

# 执行 case01
$ curl -sS -X POST http://10.0.0.5:8080/login -d '...' \
    > wkq/01_登录接口回归测试/data/case01_response.json 2> \
      wkq/01_登录接口回归测试/data/case01_stderr.log

# 执行 case02、case03 同理
```

文件命名都符合规范：小写 + caseNN_ 前缀 + 英文描述。

## 5. 渲染报告模板

```bash
$ python -m test_archive render "1" report --subject "登录接口回归测试"
已渲染: test_report.md → .../report/test_report.md
```

填充报告：

- 执行总结：3 用例，2 通过 1 失败
- 用例明细表，每行结论后引用 `data/caseNN_*.log`
- 失败用例分析（case03）：
  - 现象：返回 500 而非预期的 423
  - 证据：`wkq/01_登录接口回归测试/data/case03_response.json`
  - 可能原因：账号锁定状态未在 v1.2.3 中持久化
- 缺陷清单：bug-01 关联 case03
- 结论：v1.2.3 不可发布，需修复后回归

## 6. 收尾汇报

向用户汇报：

> 本轮测试 3 用例，2 通过 1 失败。case03（锁定账号）返回 500 而非 423，已记入 bug-01，建议修复后回归。
>
> 产出物：
> - 方案: `wkq/01_登录接口回归测试/plan/test_plan.md`
> - 数据: `wkq/01_登录接口回归测试/data/`
> - 报告: `wkq/01_登录接口回归测试/report/test_report.md`

## 7. （可选）备份

若在多人共享服务器上：

```bash
$ python -m backup_sync -c ~/.backup_sync.yaml sync --label "auth_service_regression_v1.2.3"
```

把整个 `wkq/` 增量推送到 GitHub，防止他人误删。

## 8. 回归时复用批次

用户后续说："v1.2.4 修好了，回归一下。"

```bash
$ python -m test_archive resume "1"   # 复用 01_登录接口回归测试
已定位批次: 01_登录接口回归测试
  路径: ...
```

把这次执行的产出追加到 `data/`（用 `caseNN_run2_*` 区分），报告旧版另存为 `test_report_v1.md`，新版仍是 `test_report.md`。
