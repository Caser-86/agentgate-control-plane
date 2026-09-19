# 本地备份与恢复

备份脚本用于保存控制平面数据库、Worker journal 和管理员明确指定的隔离目录。它不会复制 `data/bootstrap-token`、Worker `credentials.bin` 或普通工作区文件；因此第一次执行如果没有提供隔离目录，manifest 会明确写 `complete=false`。

## 生成备份

在项目根目录使用一个尚不存在的新目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-local.ps1 `
  -Destination 'D:\AgentGateBackups\2026-09-12' `
  -QuarantineRoot 'C:\AgentGate\workspaces\demo\.agentgate\quarantine'
```

`-QuarantineRoot` 可以重复传入多个隔离目录。备份目录不能位于数据库、Worker 状态或隔离目录内部，且脚本不会覆盖已有备份目录。

数据库备份行为：

- 发现 `data/agentgate.db` 时，使用 SQLite 在线 backup API 生成一致性副本。
- 未发现 SQLite 文件时，使用 Compose PostgreSQL 容器内的 `pg_dump` 生成纯 SQL 文件。
- PostgreSQL 不可用时直接失败，不生成“成功”备份清单。

## 恢复预检

恢复默认只做预检，不改变现有数据：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-local.ps1 `
  -Source 'D:\AgentGateBackups\2026-09-12' `
  -ValidateOnly
```

预检会检查格式版本、文件是否缺失、路径是否越界、文件长度和 SHA-256 摘要。摘要不一致时必须停止，不要手工修改 manifest。

## 应用 SQLite 恢复

应用恢复前必须停止 API、scheduler、control-worker、Web 和 Native Worker，并明确指定 `-Offline`。脚本还要求先把当前状态备份到另一个新目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-local.ps1 `
  -Source 'D:\AgentGateBackups\2026-09-12' `
  -Apply `
  -Offline `
  -CurrentStateBackupDestination 'D:\AgentGateBackups\before-restore-2026-09-12'
```

已有隔离目标文件不会被覆盖；发生冲突时会在写入前停止。PostgreSQL 备份目前只提供一致性 dump 和完整性预检，不由脚本自动执行 `psql` 覆盖恢复，需在停机窗口采用受审计的数据库恢复流程。

## 注意事项

- 备份目录包含数据库和隔离文件，仍应只保存在本机受控磁盘，不要上传到聊天或公共仓库。
- 备份不包含跨机器可用的 Worker DPAPI 凭据；换机器后需要重新注册 Worker 并对账。
- 恢复不是删除/覆盖用户普通文件的工具；目标冲突必须人工处理。
- 只有“生成成功 + manifest 摘要通过 + 独立环境恢复演练成功”才能算完成备份恢复验收。
