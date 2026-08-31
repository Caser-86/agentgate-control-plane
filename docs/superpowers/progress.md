# Final integration fixes progress

基线目标提交：`70df1d7`（隔离工作树 `codex/reliable-foundation-20260831`）。

已完成：

- 原生 Worker grant 增加 `lease_version`，恢复过期租约时按任务、旧 owner、旧 lease version 原子删除 stale grant；旧 owner/grant 无法启动或完成，新 owner 可重新启动并完成。
- proposed check 保存 submitter，幂等键按 submitter 隔离；状态查询按 submitter 限定，跨客户端返回统一 404。
- 成功 check proposal 在同一事务中写入 accepted audit、`task.queued` Outbox 和任务；观测失败回滚任务及事件。
- `platform.self_check` 仅接受 `target=local` 且禁止 parameters；文档改为 durable queue/control-worker，并明确 `platform.self_check` capability。
- 验收脚本先检查迁移就绪，再启动 native Worker self-check。

未完成/限制：

- Compose 第一次运行发现迁移 revision 名超过既有 `alembic_version.version_num VARCHAR(32)`；已将 revision 缩短为 `0007_bound_grants_check_owner`。第二次镜像构建因依赖下载超过 30 秒有界窗口而终止，故本轮没有宣称修正后的容器迁移/E2E 已通过。
- 工作树未提供可用的 `AGENTGATE_TEST_DATABASE_URL`，PostgreSQL pytest 用例保持跳过。

本轮最终集成修复证据：`apps/api/tests/test_compose_contract.py` 为 `10 passed`；Worker `8 passed`；后端 `165 passed, 5 skipped`；前端 `7 files/13 tests passed`，lint/typecheck/build 退出码 0；Compose config、PowerShell 解析和 diff check 均通过。未启动服务，因此 bounded E2E 与 live foundation verification 未执行。详见 `reports/task-8-report.md`。
