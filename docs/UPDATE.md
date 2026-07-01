# Insta360 硬件提效平台更新说明

## 平台内更新（推荐）

打开平台，在左侧边栏底部点击「检查更新」。检测到新版本后会展示「本次更新要点」，确认后点击「立即更新」。平台会：

1. 从发布通道拉取更新包与 `UPDATE_NOTICE.json`。
2. 校验 SHA256（详见下文）。
3. 备份当前安装目录到 `<install_root>\_hwagent_backup_<GUID>\`。
4. 覆盖安装文件、重新部署 Cadence 菜单脚本。
5. 自动重启平台服务。

## 命令行更新

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

更新脚本会保留 `data`、`uploads`、`outputs`、`history` 和 `config/local.json`，以及 `plugins/user` 下的自定义脚本。如果仓库地址为空，会用中文提示并跳过 Git 更新。

## SHA256 完整性校验

每次 OTA 下载都会自动比对发布方在 `UPDATE_NOTICE.json` 中提供的 `sha256`：

- 校验通过：更新继续执行，并在「更新公告」里展示 `integrity_verified: true` 指示。
- 校验失败：平台会**中止更新**，删除已下载的临时包，本地安装不会受到污染；UI 上给出失败原因，可以重试或稍后再试。
- 若 `UPDATE_NOTICE.json` 未提供 `sha256`，UI 会显示黄色警告：「此更新包未经 SHA256 校验」。此时可手工核对来源（例如与发布公告里的哈希对齐）后再决定是否继续。

企业分发场景下建议始终在发布通道里配好 `sha256`，避免中间层被投毒。

## 版本单调（禁止降级）

OTA 默认拒绝降级，即远端版本号 ≤ 本地版本号时会跳过更新，避免自动化流程把用户拖回旧版本：

- 若需要手动降级，可通过 `Insta360_HW_Setup.exe` 重新安装旧版本安装包，向导会弹出「确定降级」确认。
- 高级用户可以显式允许降级：

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\update.ps1 -AllowDowngrade
  ```

- 降级前请先备份 `data\` 和 `config\local.json`：新版可能写入了旧版无法识别的字段。
