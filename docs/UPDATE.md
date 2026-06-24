# 硬件效率工具集更新说明

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\update.ps1
```

更新脚本会保留 `data`、`uploads`、`outputs`、`history` 和 `config/local.json`。如果仓库地址为空，会用中文提示并跳过 git 更新。
