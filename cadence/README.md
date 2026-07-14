# Cadence 集成

Insta360 硬件提效平台支持 OrCAD Capture 16.6 和 17.4。Capture 顶部菜单固定使用 ASCII 名称 `insta360_HW`，核心入口为：

| 菜单项 | 行为 |
|---|---|
| `Open Platform` | 启动本地平台并打开工作台 |
| `Export and Process BOM` | 导出当前设计的完整器件属性，转换成 Excel，并自动带入 BOM 处理 |

## 导出链路

每次导出都会在 `data/jobs` 下创建独立任务目录，包含本次任务自己的 `parts.json` 和 `bom.xlsx`。两个 Capture 进程并行导出不会覆盖；转换失败时直接显示本次错误，不会回退使用 inbox 中的旧 BOM。

导出成功后，隐藏启动器把 Excel 路径和 DSN 名称传给平台，BOM 处理页自动进入来源识别步骤。

## 安装与修复

Setup 正常安装时会自动部署 Cadence 集成。需要手动恢复时，可从平台点击“修复 Cadence 集成”，或运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\redeploy_cadence_loader.ps1 -Force
```

兼容入口 `cadence\install_cadence_integration.ps1` 只转发到同一修复流程，不再自行搜索或复制脚本。

发现逻辑会检查：

- `SPB_DATA`、`CDS_DATA`、`HOME` 和常见 `SPB_Data` 用户配置根目录；
- C/D 盘的 Cadence 16.6、17.4 标准安装位置；
- `CDSROOT`、`CDS_ROOT`、`CADENCE_ROOT` 指向版本根目录或 `tools` 目录的情况。

新 Loader 只安装到用户 `cdssetup\OrCAD_Capture\tclscripts\capAutoLoad`。厂商安装目录只用于识别版本和清理本平台过去遗留的 Loader，不会写入新脚本。

## 所有权与移除

平台在 `%LOCALAPPDATA%\Insta360_HW\cadence\integration_manifest.json` 记录自己部署的文件。修复可重复执行；内容未变化时不会重写 Loader。

移除或卸载时同时满足以下条件才会删除文件：

1. 文件名为 `iac_bom_tool.tcl`；
2. 路径位于合法的用户或厂商 `capAutoLoad`；
3. 文件含 Insta360_HW 所有权标记。

`PLMTools`、系统脚本和其他未知 Tcl 始终保留。手动移除命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\remove_cadence_loader.ps1
```

Capture 已经运行时，普通菜单脚本可在 Command Window 重新 `source` Loader 热更新；快速 NC 快捷键受 Capture 注册机制限制，需要重启 Capture 后生效。
