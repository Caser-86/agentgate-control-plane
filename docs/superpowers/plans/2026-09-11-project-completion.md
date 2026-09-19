# AgentGate 正式本地版本完成计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前项目收敛为可安装、可接入、可恢复、可验证的 Windows 本地单用户文件操作权限网关。

**Architecture:** 保留 FastAPI 控制平面、PostgreSQL、React 控制台和 Windows Native Worker，不整体重写。结构化动作经过权限与审批后交给 Worker，执行结果持久化并对账；监控辅助判断系统状态，不替代权限控制。

**Tech Stack:** Python、FastAPI、SQLModel、PostgreSQL、SQLite Worker journal、React、Vite、PowerShell、Docker Compose、pytest、Playwright、GitHub Actions。

**Spec:** [2026-09-10 工程审核与路线](../../project-review-and-roadmap-2026-09-10.md)。本计划将该审核转成实施任务；以下新增接口、文件及状态都是待实现设计，不是现有能力声明。

## 全局约束

- 只有经过网关的动作受控；不承诺全机防误删、系统级沙箱或任意 Agent 自动接管。
- 当前目标为 Windows 本地单用户版本；服务默认只绑定回环地址，免密只适合本地自用，不放宽现有非开发环境认证限制。
- 文件操作只保留检查、隔离、恢复；不增加永久删除、任意 Shell 或服务写操作。
- 产品页面使用正式中文，不出现“面试演示”“安全演示”等产品定位文案。测试样例可以标为样例，但不能伪装成真实能力。
- 保留用户现有修改、配置、数据库、隔离文件和凭据。测试使用专用临时工作区、测试数据库及独立 Worker 状态目录。
- 不把所有 403 当作可忽略错误；不把客户端未获确认的结果直接标成成功；不自动重放可能已经产生副作用的操作。
- 每项按“失败回归 → 最小实现 → 针对性测试 → 相关回归 → 文档”完成。历史通过记录不能代替本次验证。
- 每项独立记录变更和证据；提交只包含本项文件，不混入已有修改。实际提交、远程推送、发布、许可证选型另按用户授权处理。
- 先关闭可靠性缺陷，再增加体验；不得用“已知限制”豁免数据丢失、重复执行或错误恢复。

## 一、什么算完成

交付的是正常产品，而不是额外制作一个展示页面。完成后使用者应能：

1. 按中文文档在支持环境安装并启动，看到真实组件状态和正在运行的版本。
2. 登记一个工作区，为外部程序创建范围明确的访问凭据。
3. 由外部程序提交真实文件操作；受保护文件被拒绝，需审批的动作在批准前无副作用。
4. 批准后隔离普通文件，随后恢复；冲突时不覆盖已有文件。
5. 在断网、重启、重复请求、上报失败后查看明确结果，必要时人工对账，不静默丢证据。
6. 从备份恢复本地系统；按文档定位启动、认证、Worker、审批和文件冲突问题。

不要求：新模型集成、多租户、远程执行、全盘扫描、Windows 驱动、独立 SaaS、Kubernetes、视觉重设计。

## 二、任务总表与依赖

| ID | 交付物 | 依赖 | 有效工程日 |
| --- | --- | --- | --- |
| T0 | 基线、隔离验收环境和证据模板 | 无 | 0.5 |
| T1 | 结构化错误分类与可靠补报对账 | T0 | 2–3 |
| T2 | 隔离/恢复独立日志配对与中断复核 | T0 | 1.5–2.5 |
| T3 | Windows 路径边界与并发变化验证 | T2 | 1.5–3 |
| T4 | 可解释的 Worker 进展与阻塞状态 | T1、T2 | 1–1.5 |
| T5 | Windows/PostgreSQL CI 与统一验证入口 | T0，最终集成 T1–T4 | 1.5–2 |
| T6 | 可重复依赖、可靠启动、版本核对 | T5 | 1–2 |
| T7 | 一致性备份与安全恢复流程 | T1、T2、T6 | 1.5–2.5 |
| T8 | 认证回归、真实外部调用与权限验收 | T1–T4 | 1.5–2.5 |
| T9 | 中文使用流程、错误状态与文档收口 | T4、T8 | 1–2 |
| T10 | 可信稳定性统计与故障注入验收 | T5–T9 | 1.5–2 |
| T11 | 干净环境验收与发布资料 | 全部 | 0.5–1 |

合计约 **15–24.5 个有效工程日**，另加至少 24 小时稳定性观察；预留约 20% 风险缓冲。与前次 15–26 日粗估同一量级，不是保证工期。Windows 并发路径方案若涉及系统级权限隔离，必须单独评估，不能无限塞入本次范围。

按四个交付阶段执行：A=T0–T4，B=T5–T7，C=T8–T9，D=T10–T11。T1/T2 可由不同执行者并行，但不要同时修改共享 client 文件；T5 可提前建立 CI，最终验收必须基于集成结果。

## 三、实施任务

### T0：锁定基线与测试环境

**文件：** 新建 `docs/superpowers/reports/2026-09-11-completion-progress.md`；读取 `scripts/verify.ps1`、现有测试配置和工作树差异，不修改业务逻辑。

**输入/输出：** 输入当前 Git 工作树；输出可追踪基线、环境版本、失败/跳过清单和后续任务状态。

- [ ] 记录提交号与 `git status --short`，逐项注明已有修改；禁止 reset、清空 data 或覆盖 `.env`。
- [ ] 记录 Python、Node、Docker、PowerShell 和 Windows 版本；不输出环境变量全量内容。
- [ ] 分别执行 API、Worker、Web 基线命令，记录退出码、耗时与跳过原因。
- [ ] 为故障测试约定独立测试数据库、临时目录和 Worker 状态；记录绝对路径，确认不是用户工作区。
- [ ] 创建证据记录，每项包含 `task_id / commit / command / exit_code / result / skipped_reason / artifact_path`。

```powershell
git rev-parse HEAD
git status --short
& .\apps\api\.venv\Scripts\python.exe --version
& .\apps\worker\.venv\Scripts\python.exe --version
node --version
docker version --format '{{.Client.Version}}'
```

**验收：** 所有后续测试能追溯基线；环境无法运行的测试明确列为未验证，不算通过。预计 0.5 日。

### T1：结构化错误与补报对账

**修改：** `apps/worker/agentgate_worker/client.py`、`journal.py`、`main.py`；`apps/api/app/services/worker_protocol.py`、`apps/api/app/api/worker.py`。**测试：** `apps/worker/tests/test_client.py`、`test_journal.py`、`test_main.py`；`apps/api/tests/test_worker_protocol.py`、`test_worker_file_protocol.py`。

**协议设计：** 保留现有 WorkerProtocolError 的旧调用方式，增加可选 `status_code: int | None`、`error_code: str | None`，不得把响应全文写入异常。新增本地 `reconciliation_required` 状态，与 `reported` 分离。`WorkerJournal.mark_reconciliation_required(task_id: str, reason_code: str) -> None` 只改变对账状态，保留摘要与结果；新查询 `reconciliation_items()` 返回待复核任务。旧数据库以幂等方式增加必要字段，不删除表。

**错误决策：**

| 条件 | 处理 | 是否允许新任务 |
| --- | --- | --- |
| 网络超时、429、5xx | 退避，保留待补报 | 本轮停止；恢复后再判断 |
| 401、Worker 凭据撤销/失效 | 显示认证阻塞，不清除凭据 | 不允许 |
| 已证明为当前 Worker 自己任务的终态冲突 | 保留证据并进入对账 | 不相关任务可继续；同工作区文件写操作暂停 |
| digest/归属不一致、未知 403、无法解析错误 | 安全阻塞并告警 | 不允许自动越过 |
| 重复报告且结果一致 | 服务端幂等确认 | 允许 |

该表是目标语义，实施时必须逐个核对服务端已有错误码。不能仅凭 HTTP 403 区分所有权和终态。若现有端点无法安全证明终态，先扩展服务端明确的结果语义及测试，不在客户端猜测。

- [ ] 在 `test_main.py` 固化“补报异常导致 claim 未调用”的现状测试，作为错误分类设计依据。
- [ ] 在 `test_client.py` 添加不同错误码、未知格式、网络超时回归；确认当前实现不能完成分类。
- [ ] 写 journal 状态迁移测试：待复核不是成功，重启后保留，原始证据未被改写。
- [ ] 实现错误解析、对账状态和受限制的继续策略；单次补报最多处理 50 项，避免无界循环。
- [ ] 服务端测试同任务同结果重复报告、不同结果重放、其他 Worker 报告、撤销凭据和过期授权。
- [ ] 用两个任务验证：一个进入复核后，不相关只读任务可运行，同工作区写任务不能绕过复核。
- [ ] 更新 Worker 协议文档，记录人工对账条件；人工确认不重新执行文件操作。

核心测试设计示例（新增语义）：

```python
def test_report_failure_does_not_claim_before_classification():
    from unittest.mock import Mock
    import pytest
    from agentgate_worker.client import WorkerProtocolError
    from agentgate_worker.main import _process_worker_tasks
    client = Mock()
    client.recover_pending_reports.side_effect = WorkerProtocolError("unknown rejection")
    with pytest.raises(WorkerProtocolError):
        _process_worker_tasks(client)
    client.claim.assert_not_called()
```

**验收：** 不是“忽略错误后继续”，而是已验证的错误分类、持久对账和无重复副作用。运行 Worker `test_client.py test_journal.py test_main.py` 与 API 两个协议测试。预计 2–3 日。

### T2：隔离与恢复日志独立配对

**修改：** `apps/worker/agentgate_worker/quarantine.py`、`client.py`；必要时联动 `apps/api/app/services/file_actions.py`。**测试：** `apps/worker/tests/test_quarantine.py`、`test_file_action_stability.py`；`apps/api/tests/test_file_action_recovery.py`。

**接口：** 保持 `recover_incomplete_journal(journal_path: Path) -> list[RecoveryNotice]` 对调用方兼容；新日志增加 `operation_id` 和 `operation_kind`（`quarantine` / `restore`），同一次操作的 prepared/completed 使用同一标识。历史格式按动作、操作种类及顺序识别，不用全局集合抵消。无法可靠配对的历史记录返回人工复核，不推定成功。

- [ ] 加入下面的失败用例并实际观察失败。
- [ ] 增加两次恢复尝试、重复完成、截断行、旧日志和混合格式用例。
- [ ] 写入独立操作标识；prepared 必须先持久化，移动后才能 completed。
- [ ] 在 prepared 后、移动后、completed 前分别模拟退出；重启后核对源/目标摘要和存在状态。
- [ ] 源目标同时存在、都不存在或摘要不符进入复核；不自动覆盖或再次移动。
- [ ] 对外显示恢复待复核，不把它等同于隔离失败或恢复成功。

```python
def test_restore_prepare_is_not_hidden_by_quarantine_complete(monkeypatch):
    from pathlib import Path
    from agentgate_worker import quarantine
    records = [
        {"action_id": "a", "phase": "prepared"},
        {"action_id": "a", "phase": "completed"},
        {"action_id": "a", "phase": "restore_prepared"},
    ]
    monkeypatch.setattr(quarantine, "_read_journal", lambda _: records)
    notices = quarantine.recover_incomplete_journal(Path("unused"))
    assert len(notices) == 1
    assert notices[0].decision == "manual_review_required"
```

**验收：** 中断不漏报、历史日志可读、重复执行不增加副作用。预计 1.5–2.5 日。

### T3：文件安全边界与故障验证

**修改：** `apps/worker/agentgate_worker/filesystem.py`、`quarantine.py`。**测试：** `test_filesystem.py`、`test_file_actions_windows.py`、`test_quarantine.py`；文档 `docs/file-action-governance.md`。

**输入/输出：** 输入已批准的 WorkspaceContext 和相对路径；输出安全普通文件或明确 FileActionError。不扩大允许路径格式，不依赖前端校验保证安全。

- [ ] 为根目录本身、隔离根、恢复源各祖先的 junction/reparse point 写拒绝测试。
- [ ] 将共有根与祖先检查收敛为内部校验函数；不存在的恢复叶子允许，祖先不存在或不安全必须拒绝。
- [ ] 检查后替换目录的 Windows 专用测试先复现，再验证实现；不把二次字符串检查当作绝对无竞态保证。
- [ ] 在受支持威胁模型下采用目录权限保护或句柄约束；如果不能保证同用户恶意进程隔离，明确不支持此威胁，仍必须修复静态越界与可意外触发的竞态。
- [ ] 覆盖 UNC、盘符、`..`、NUL、大小写、跨卷、已有目标、路径过长、文件被占用、只读属性和大文件中止。
- [ ] 使用临时目录和哨兵文件，测试后确认工作区外哨兵内容不变。

```python
# 每个恶意路径案例都需要类似断言；异常码按当前 FileActionError 约定核对。
assert sentinel.read_bytes() == original_sentinel_bytes
assert not unexpected_destination.exists()
```

**验收：** Windows 原生用例实际执行；跳过 junction 用例时不得宣称该边界验证通过。若需要驱动或独立账户强隔离，记录为另一个项目，不扩展本任务。预计 1.5–3 日。

### T4：Worker 状态与对账入口

**修改：** `apps/api/app/services/platform_checks.py`、`apps/api/app/api/platform.py`、相关 Worker schema；`apps/web/src/pages/SystemPage.tsx`、`FileGovernancePage.tsx`。**测试：** `apps/api/tests/test_platform_checks.py`、`apps/web/src/pages/FileGovernancePage.test.tsx`；新增 `apps/web/src/pages/SystemPage.test.tsx`。

**新增显示合同：** 心跳在线与执行状态分别显示；执行状态为 `ready / blocked / reconciliation_required / unknown`，含脱敏原因码、待补报数量和最后成功时间。旧 Worker 未上报进展时显示 unknown，不能默认为 ready。详细接口沿用现有平台响应的扩展字段，前后端同项提交。

- [ ] 写“心跳正常但补报阻塞”测试，要求页面不显示全部正常。
- [ ] 将 T1/T2 状态接入平台查询，保证服务端校验 Worker 身份。
- [ ] 增加详情入口：任务、审批、错误、相对路径和时间；不显示令牌、绝对凭据路径。
- [ ] 人工对账必须二次确认并留下操作者/原因；免密模式仍只能使用已有本地操作边界，不增加公开写端点。
- [ ] 测试加载失败、空状态、旧字段缺失、权限拒绝和恢复后刷新。

```typescript
// 使用页面现有 render/mock 模式构造 blocked 响应后：
expect(await screen.findByText('执行受阻')).toBeInTheDocument();
expect(screen.queryByText('全部正常')).not.toBeInTheDocument();
```

**验收：** 可区分“进程存在、心跳在线、任务可执行、结果已确认”。预计 1–1.5 日。

### T5：CI 与验证入口

**修改：** `.github/workflows/ci.yml`、`scripts/verify.ps1`。**测试：** `apps/api/tests/test_migrations.py`、`test_failure_injection.py`、Worker 全套及 `scripts/file-action.contract.test.ps1`。

- [ ] 分成 Ubuntu API/Web、PostgreSQL 集成、Windows Worker 三个独立 job。
- [ ] PostgreSQL job 设置 `AGENTGATE_TEST_DATABASE_URL`，数据库名使用 `agentgate_test` 前缀和回环地址，遵守现有测试保护规则。
- [ ] Windows job 安装 Worker 与测试依赖，执行文件、凭据和 PowerShell 合约；不能用 Linux 跳过结果代替。
- [ ] 修正统一脚本的解释器选择：Worker 测试使用 Worker 虚拟环境，不混用 API Python。
- [ ] 所有原生命令检查退出码；上传脱敏测试报告，禁止上传 `.env`、凭据或工作区内容。
- [ ] 在独立测试数据上验证迁移、事务回滚、并发领取和审批幂等。

```powershell
$workerPython = Join-Path $repoRoot 'apps\worker\.venv\Scripts\python.exe'
& $workerPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Worker tests failed.' }
```

**验收：** 三个 job 均有实际结果；PostgreSQL 核心测试未因缺少变量跳过。分支保护规则的远程设置另行授权，不能把 YAML 成功等同于已设置保护。预计 1.5–2 日。

### T6：依赖、启动与版本一致性

**修改：** API/Worker `pyproject.toml`、`apps/api/Dockerfile`、`scripts/setup-local.ps1`、`scripts/start-local.ps1`、`compose.yaml`。**新建：** 两个 Python 应用各自的 `requirements.lock`，`scripts/start-local.contract.test.ps1`。**测试：** `apps/api/tests/test_compose_contract.py`。

- [ ] 选择同一种锁定生成方式，固定运行依赖与传递版本；平台差异使用环境 marker 或分平台锁，不能把 Windows 解析结果直接当 Linux 镜像锁。
- [ ] 干净环境按锁安装，扫描实际依赖；扫描发现须分类处理，不自动无界升级所有包。
- [ ] 每个 Compose 原生命令后立即检查退出码。
- [ ] 启动后逐项确认 API、Web、scheduler、control-worker 就绪；API 版本包含构建提交号，禁止旧服务响应掩盖新构建失败。
- [ ] 模拟构建失败但旧 API 健康、Web 失败、端口占用，均要求非零退出。
- [ ] 比对启动前后配置摘要，确保用户端口、provider、认证设置未被覆盖；摘要不含密钥。
- [ ] 明确停止、重启和自动恢复策略，不让文件动作因容器重启被无条件重复执行。

```powershell
docker compose up -d --build api scheduler control-worker web
if ($LASTEXITCODE -ne 0) { throw '服务构建或启动失败，未完成启动。' }
```

**验收：** 同一锁文件可重建受支持平台依赖；失败不报成功，成功可核对版本。预计 1–2 日。

### T7：备份恢复与升级安全

**新建：** `scripts/backup-local.ps1`、`scripts/restore-local.ps1`、`scripts/backup-restore.contract.test.ps1`、`docs/backup-and-recovery.md`。

**接口：** 备份输入 `-Destination`，恢复输入 `-Source -ValidateOnly` 或显式 `-Apply`；默认仅校验。备份 manifest 包含格式版本、应用版本、数据库备份、隔离文件、journal 的摘要和一致性时间点，不包含明文密钥。

- [ ] 先停止领取新写任务并确认没有执行中文件操作，再生成数据库、隔离文件和 journal 的一致性备份；无法停稳则失败，不生成“成功”清单。
- [ ] 导出数据库并计算数据文件摘要；目标目录不得位于被备份目录内。
- [ ] 恢复预检版本、摘要、剩余空间和路径；缺少隔离文件或 journal 时阻止自动恢复。
- [ ] `-Apply` 前备份现状；不得覆盖用户文件冲突。所有删除/移动目标必须解析到明确目录并检查范围。
- [ ] 同机恢复验证凭据可用；异机 DPAPI 凭据不假定可用，要求重新注册和任务对账。
- [ ] 在独立目录/数据库做一次完整演练，再重复提交旧请求证明不产生第二次副作用。

```powershell
# 待脚本实现后执行；Source 使用演练备份，不指向线上状态。
.\scripts\restore-local.ps1 -Source $testBackupPath -ValidateOnly
if ($LASTEXITCODE -ne 0) { throw '备份预检未通过，不允许应用。' }
```

**验收：** 不是“备份文件存在”，而是恢复后任务、审计、隔离与恢复链路一致。预计 1.5–2.5 日。

### T8：真实接入与权限回归

**新建：** `examples/file-client/README.md`、`examples/file-client/client.py`；修改 `docs/file-action-governance.md`。**测试：** `apps/api/tests/test_external_actions.py`、`test_v1_api.py`、`test_auth_dependencies.py`、`test_security_regressions.py`。

**输入/输出：** 客户端从环境读取 API 地址和受限 token，提交现有 `/api/v1/actions` 的实际 schema；不硬编码秘密、不直接读取数据库、不调用内部测试接口。请求携带幂等键，结果关联动作 ID 与审批 ID。

- [ ] 按已有请求模型实现普通 Python HTTP 调用，不新增大型 SDK 框架。
- [ ] 使用已登记临时工作区内生成文件完成检查、申请隔离、等待审批、查询结果、申请恢复。
- [ ] 验证 `.env` 拒绝、跨工作区拒绝、未批准不执行、审批拒绝无副作用、重复提交同结果。
- [ ] 验证客户端 token 不能创建管理员会话或自行批准动作，撤销后不能继续调用。
- [ ] 在免密和启用认证两种模式检查浏览器来源、CSRF 和公开写端点边界；不要把 CORS 当授权措施。
- [ ] 客户端错误只输出中文摘要和错误码；对超时保留原幂等键，先查询状态，不盲目生成新请求。

**验收：** 外部进程确实经过正式 API 完成链路；明确不保证该进程无法绕过网关直接操作文件。预计 1.5–2.5 日。

### T9：正常产品使用流程与中文资料

**修改：** `apps/web/src/pages/WorkspacesPage.tsx`、`FileGovernancePage.tsx`、`SystemPage.tsx`、对应测试；`README.md`、`docs/README.md`、`docs/architecture.md`。**新建：** `docs/troubleshooting.md`；扩展 `apps/web/e2e/file-governance.spec.ts`。

- [ ] 首次使用展示启动状态、工作区登记和下一步操作；高级凭据/恢复信息放入详情，不强迫首次用户理解 journal。
- [ ] 文件操作失败保留用户输入；危险动作批准前展示相对路径、动作和影响，不用泛化“确定”。
- [ ] 明确区分策略拒绝、待审批、排队、执行中、待上报、待复核、完成，禁止把 API 请求成功当操作成功。
- [ ] README 收口为用途、边界、安装、一次真实操作、故障入口；模型 Mock 与真实 provider、示例工具与真实操作分开说明。
- [ ] 排障覆盖打不开网页、初始化失败、Worker 离线/阻塞、审批过期、目标冲突、备份损坏和迁移失败。
- [ ] 浏览器验收窄窗口、键盘操作、加载/空/失败态及中文错误；不在本任务重做视觉风格。

**验收：** 未参与开发者能按文档完成首次操作；若没有外部试用者，只能记录维护者走查，不能编造用户测试。预计 1–2 日。

### T10：稳定性与故障验收

**修改：** `scripts/soak-worker.ps1`、`scripts/soak-file-actions.ps1`。**新建：** `scripts/soak-worker.contract.test.ps1`。**测试：** `apps/worker/tests/test_file_action_stability.py`、`apps/api/tests/test_failure_injection.py`。

- [ ] 注入可控时间，使用单调时钟记录间隔；按有效时间槽计算覆盖率，同一槽多次采样不得抵消空洞。
- [ ] 核对最后探测时间，超过事先约定新鲜度阈值视为未知/失败，不认可历史 healthy。
- [ ] 定义正常验收：24 小时、30 秒周期、覆盖率至少 95%、最大间隔不超过 90 秒、未解释失败为 0；正常场景有失败不能仅因不连续而通过。
- [ ] 定义退出码：0 通过，2 业务失败，3 环境中断/证据不足；手工终止必须记录 interrupted，不能在 finally 中写 PASSED。
- [ ] 先用时间模拟测试睡眠、时间跳变、空样本、最后样本失败和陈旧探测，再运行短时实际测试。
- [ ] 独立故障套件注入断网、API/Worker 重启、重复上报、文件占用、恢复冲突；预期故障单独报告，不混入正常24小时全绿统计。
- [ ] 只在专用文件执行区循环隔离/恢复；留存每轮动作 ID、摘要、状态和耗时，不碰用户现有文件。
- [ ] 记录内存、日志/journal 大小和待补报数量的开始/结束值，检查是否持续增长；异常增长须分析，不单凭程序没退出判稳定。

**验收：** 正常连续运行通过且故障恢复符合预期；缺少唤醒条件时结论为证据不足。长时间执行时用产品提供的持续任务机制，避免占用会话阻塞等待。预计 1.5–2 日＋至少24小时观察。

### T11：发布前闭环

**新建：** `docs/release-checklist.md`、`CHANGELOG.md`；修改版本声明和文档导航。许可证需用户选择后才创建 `LICENSE`，公开仓库不自动等于已授权开源使用。

- [ ] 在未配置过本项目的支持环境，从仓库安装到真实外部调用走通；记录机器和软件版本。
- [ ] 在测试数据上验证上一版本升级、失败退出和备份恢复。
- [ ] 运行下方全量矩阵；所有跳过项说明原因，关键 Windows/数据库用例不能豁免。
- [ ] 审查待发布 diff 和文件清单；确认无 token、数据库、私人路径或日志内容泄漏。
- [ ] 发布说明列新增能力、修复项、兼容性、升级步骤、已知限制及证据位置。
- [ ] 核对下方门槛全部满足后才建议打版本标签；未经授权不推送或发布。

**验收：** 能明确回答“这个版本支持什么、怎么装、失败怎么办、哪些测试证明可用”。预计 0.5–1 日。

## 四、验证命令与执行规则

以下使用已存在的本地虚拟环境；环境缺失时按锁定后的安装流程准备，不能默默切换解释器。每条命令后立即检查 `$LASTEXITCODE`，失败停止该组；测试路径相对于各应用目录。

```powershell
# 在 apps/api 下
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.evals.runner

# 在 apps/worker 下；lint/typecheck 使用该环境已安装的开发工具
.\.venv\Scripts\python.exe -m pytest -q

# 在 apps/web 下
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
npm.cmd run test:e2e

# 在仓库根目录；T5 完成后统一入口应覆盖正确解释器
pwsh -NoProfile -File .\scripts\verify.ps1 -IncludeWindowsFileContract
docker compose config --quiet
git diff --check
```

测试环境端口与常用运行端口分离，E2E 使用现有脚本约定；PostgreSQL 测试连接仅指向专用测试库。Windows 合约依赖满足前先读脚本，禁止将真实用户路径传作测试目标。

## 五、发布验收矩阵

| 场景 | 必须观察的结果 | 归属 |
| --- | --- | --- |
| 错误/撤销凭据 | 拒绝且无副作用，不显示密钥 | T1、T8 |
| 受保护/越界路径 | 策略或 Worker 拒绝，外部哨兵不变 | T3、T8 |
| 未批准/拒绝/过期审批 | 不执行文件动作 | T8 |
| 同幂等键重复请求 | 同一动作结果，不重复移动 | T1、T8 |
| 同键不同内容 | 明确冲突，不覆盖原请求 | T1、T8 |
| 移动后进程退出 | 重启可识别状态，结果可对账 | T2 |
| 永久补报拒绝 | 明确阻塞或复核，无静默丢弃 | T1、T4 |
| 根或祖先 junction | 拒绝不安全路径，边界说明准确 | T3 |
| 目标已有文件 | 恢复冲突，不覆盖 | T2、T3 |
| 构建失败但旧 API 存活 | 启动命令失败，不声称新版本就绪 | T6 |
| 备份不完整/摘要错误 | 预检失败，不改现有数据 | T7 |
| 电脑长暂停/探测陈旧 | 证据不足或异常，不通过 | T10 |
| 干净安装与完整业务 | 无手工修库、无内部测试捷径 | T11 |

## 六、推进与停止条件

- 每项报告四种状态：未开始、进行中、已验证、受阻；代码写完但测试未跑仍是进行中。
- A 阶段出口：两个已复现缺陷关闭，路径边界有 Windows 证据，状态页不会将阻塞显示为正常。
- B 阶段出口：平台 CI、可靠启动、完整恢复演练均有结果。
- C 阶段出口：外部调用使用受限凭据完成真实业务，普通使用者说明可读。
- D 阶段出口：本次版本所有门槛通过；未经解释失败不能归档为环境原因。
- 出现工作区外改动、数据摘要不一致、重复副作用，立即停止涉及文件写入的测试，保留现场和日志，先解决一致性问题。
- 发现必须提高 Windows 权限、修改其他项目、删除现有数据或采用新许可证时，单独请求用户决策，不因“完成项目”自行扩大授权。

## 七、自查与交接

审核 R1→T1/T4，R2→T2，R3→T3，R4→T5，R5→T6，R6→T10，R7→T6/T11；备份恢复→T7，真实接入与认证→T8，中文与易用性→T9。没有把任何已知审核项默认为已完成。

建议按 T0、T1、T2 顺序开始，完成 A 后复核工程量。执行可选择同一任务逐项推进，或在工具可用时拆分无共享写入的子任务并逐项评审；无论方式如何，发布门槛不变。
