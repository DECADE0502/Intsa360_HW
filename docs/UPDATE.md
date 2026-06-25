# 硬件效率工具集更新说明

## 平台内更新（推荐）

打开平台，在左侧边栏底部点击「一键更新」。平台会从 Git 仓库拉取最新版本，重新构建前端、重新部署 Cadence 菜单脚本，完成后自动重启服务。

## 命令行更新

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

更新脚本会保留 `data`、`uploads`、`outputs`、`history` 和 `config/local.json`，以及 `plugins/user` 下的自定义脚本。如果仓库地址为空，会用中文提示并跳过 Git 更新。
