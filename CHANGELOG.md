# 变更记录

## 未发布

### 新增

- Worker 结构化错误、补报对账状态和执行阻塞心跳。
- 隔离/恢复独立操作日志标识和路径祖先安全检查。
- API/Worker 运行时与开发依赖锁文件。
- 外部文件动作 Python 客户端和中文接入说明。
- 本地备份、恢复预检、稳定性证据和故障排查文档。
- `CONTEXT.md` 当前项目状态和 `TODO.md` 分级待办，作为后续维护入口。

### 修复

- 防止补报失败后继续领取任务。
- 防止恢复日志被隔离完成日志错误抵消。
- 防止旧 Worker 缺少进展字段时被显示为“就绪”。
- 启动脚本现在检查 Compose 启动结果、必需服务和 API 健康状态。
- 修正 Compose Web 构建参数层级和 Windows Worker 测试解释器选择。
- 统一外部动作、权限和审批冲突的中文错误提示，保留错误码便于排查。

### 验证边界

- 2026-09-16 本机全量验证通过：API `273 passed, 6 skipped`、Worker `62 passed, 2 skipped`、Web `53 passed`、Playwright E2E `3 passed`，Windows 文件动作合约通过。
- 最新 24 小时监控采样在 `480/2880` 个样本处因连续 3 次失败提前结束，长期稳定性不能记为通过；Windows junction/reparse、完整 PostgreSQL 恢复和远程 CI 仍未完成。
