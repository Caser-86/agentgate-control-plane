# 发布前检查清单

本清单用于创建版本前的维护者复核。所有未执行项目必须保留“未验证”状态，不能用历史日志或静态代码代替运行证据。

## 代码和敏感信息

- [ ] `git diff --check` 通过。
- [ ] diff 不包含 token、密码、API key、Cookie、数据库文件、私人工作区内容或完整日志。
- [ ] 迁移文件、schema、API、Worker 和前端合同一致。
- [ ] 未执行 reset、删除用户 data 或覆盖现有隔离文件。
- [ ] 许可证已经由仓库所有者明确选择；未授权时不创建 `LICENSE`。

## 安装和运行

- [ ] 从干净环境按 README 完成 Python/Node 安装。
- [ ] API 和 Worker 依赖从 lock 文件安装，Docker 镜像使用运行时 lock。
- [ ] `docker compose config --quiet` 通过。
- [ ] `setup-local.ps1`、`start-local.ps1`、`migrate-local.ps1` 失败时返回非零。
- [ ] 启动后 API、scheduler、control-worker、Web 和 Native Worker 的状态均有实际证据。
- [ ] 默认回环绑定、模型 provider、端口和认证配置没有被启动脚本覆盖。

## 业务和安全

- [ ] 保护文件、越界路径、未批准动作和撤销 token 均拒绝且没有副作用。
- [ ] 普通文件隔离、恢复、重复请求和恢复冲突完成真实 Windows 验收。
- [ ] Worker 中断、补报拒绝和状态不确定时保留 journal，不自动重复副作用。
- [ ] 审批、动作、审计和平台健康页能区分请求接收、排队、执行、待复核和完成。
- [ ] 外部客户端只使用正式 API 和受限 scope，不能创建管理员会话或自行审批。

## 数据和稳定性

- [ ] 生成备份并完成 manifest 摘要预检。
- [ ] 在独立测试数据/数据库完成恢复演练，确认冲突不覆盖文件。
- [ ] 故障注入覆盖 API/Worker 重启、断网、重复上报、文件占用和恢复冲突。
- [ ] 稳定性测试达到约定时长、覆盖率和最大间隔；正常场景无未解释失败。
- [ ] 记录内存、日志/journal 大小和待补报数量前后差异。

## 发布证据

- [ ] API、Worker、Web、E2E、PostgreSQL 和 Windows 结果分别记录命令、退出码、跳过原因和产物路径。
- [ ] 所有跳过项都有环境或范围解释，关键 Windows/数据库场景不能默认为通过。
- [ ] 更新 `CHANGELOG.md` 和 README 的兼容性、升级、已知限制。
- [ ] 未经明确授权，不创建标签、不推送远程、不修改仓库可见性或分支保护。
