# Task 7 报告：Compose 运行拓扑、Worker 开发启动和平台自检

## 实现文件

- `compose.yaml`：postgres、api、scheduler、control-worker、web；API/Web 仅绑定 `127.0.0.1`，PostgreSQL 无宿主机 published port。
- `apps/api/Dockerfile`：加入 API healthcheck。
- `apps/api/app/api/platform.py`、`apps/api/app/services/platform_checks.py`：结构化 health/self-check，包含 status、稳定英文 code、`message_zh`、`observed_at`、有界 details；provider 仅返回名称/模型/配置状态，不返回密钥。
- `apps/api/app/services/platform_checks.py`：self-check 读取数据库 `alembic_version` 的 applied revision，并与代码 migration head 比较；缺失或不一致返回明确 unhealthy migration check。
- `apps/api/app/main.py`：挂载平台路由。
- `apps/api/app/processes/scheduler.py`：通过现有 `enqueue_task()` 幂等入队 due task，并恢复过期 durable lease；可能有副作用的任务进入 manual review，安全任务按有界退避重新排队。
- `scripts/start-local.ps1`、`scripts/stop-local.ps1`、`scripts/migrate-local.ps1`、`scripts/setup-local.ps1`、`scripts/verify-foundation.ps1`：本机固定 Compose 命令、迁移优先、健康等待、localhost/迁移/认证/heartbeat/self-check/lease 校验；前端命令使用 `npm.cmd`，不打印 token 内容。
- `README.md`、`docs/architecture.md`：中文友好的首跑命令、端口、迁移、Phase 0 无真实宿主机动作边界。
- `apps/api/tests/test_platform_checks.py`、`apps/api/tests/test_compose_contract.py`、`apps/api/tests/test_scheduler.py`：Task 7 focused tests，覆盖 stale/missing migration、服务角色、due-task 幂等入队和 lease 恢复。

## TDD 证据

先新增 focused tests 后运行：4 个新增回归断言失败，原因是 self-check 没有数据库 revision 比对、scheduler 没有 due-task 入队接口。实现后 focused tests 为 12 passed。

## 验证

- `apps/api/.venv/Scripts/python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py -q`：8 passed。
- `apps/api/.venv/Scripts/python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py tests/test_scheduler.py -q`：12 passed。
- `apps/api/.venv/Scripts/python.exe -m pytest tests -q`：129 passed, 4 skipped。
- `ruff check apps/api/app apps/api/tests`：passed。
- Task 7 定向 mypy（platform.py、platform_checks.py、scheduler.py）：passed。
- `docker compose config --quiet`：passed。
- 五个 PowerShell 脚本 AST parse：全部 `PARSE_OK`。

## Docker smoke

Docker 可用（Docker 29.7.2）。已实际执行 `start-local.ps1 -Provider mock`：PostgreSQL 成功启动，API 镜像成功构建，0001–0006 migrations 成功执行，control-worker/scheduler/Web 镜像成功构建；最终 API 容器因宿主机 `8000` 已被占用而无法绑定，精确错误为：

`Bind for 0.0.0.0:8000 failed: port is already allocated`

因此未声称 smoke sequence 成功。随后执行 `docker compose down` 成功，移除了本次 worktree 的容器和网络，保留命名 PostgreSQL volume。未执行主 checkout 的 Docker 命令。

## 限制与假设

- 完整 `mypy app`（在 `apps/api` 目录执行）已通过；Task 7 定向 mypy 也已通过。
- `verify-foundation.ps1` 按 brief 要求在没有活跃 Worker heartbeat 或存在 stale lease 时退出非零；首次 setup 只启动基础服务并打开 UI，原生 Windows Worker 需按既有协议注册后才能满足 heartbeat 验收。
- `verify-foundation.ps1` 要求 `migration_check.code == database_migration_current`；数据库 revision 缺失或 stale 会退出非零，不再只检查代码目录中的 migration head。
- 迁移脚本使用现有 `app.db.upgrade_to_head()` 显式注入 Compose URL，因为直接 CLI `alembic upgrade head` 在当前前序 `alembic.ini` 无 `sqlalchemy.url` 时会报 `KeyError: 'url'`。
