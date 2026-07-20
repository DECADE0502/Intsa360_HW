# Insta360 硬件提效平台卸载指南

## 标准卸载入口

平台的完整卸载统一由 Inno Setup 官方卸载器 `unins000.exe` 执行。可以从以下任一入口启动，它们使用同一套卸载逻辑：

- Windows 设置 → 应用 → 已安装的应用 → Insta360硬件提效平台 → 卸载（推荐）。
- 开始菜单中的卸载快捷方式。
- 再次运行 `Insta360_HW_Setup.exe`，在维护页选择卸载。
- Geek Uninstaller 等标准软件管理工具中的平台卸载条目。

交互卸载时会询问是否保留用户数据：

- **保留数据**：删除程序、Cadence 集成和平台运行状态，业务数据仍原地保留在 `%LOCALAPPDATA%\Insta360_HW`。
- **完全清除**：删除程序、Cadence 集成以及 `%LOCALAPPDATA%\Insta360_HW` 中的历史、配置和用户插件。此操作无法撤销。

## 命令行卸载

根目录 `uninstall.ps1` 只负责定位并调用官方 `unins000.exe`，不会用另一套脚本直接删文件。

```powershell
# 保留 %LOCALAPPDATA%\Insta360_HW 中的业务数据
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode PreserveData

# 完全清除程序和用户数据
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode PurgeData

# 自定义安装目录时显式指定路径
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode PreserveData -InstallDir "D:\Apps\Insta360\HWAgent"

# 只打印将要执行的官方卸载命令，不执行
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode PreserveData -DryRun
```

旧参数 `Detach` 会明确映射为 `PreserveData`，`Full` 会明确映射为 `PurgeData`。新的自动化脚本应直接使用新名称。

直接调用标准卸载器或通过 Setup 执行静默卸载时，数据策略必须明确：`/PURGEDATA` 删除用户数据，`/PRESERVEDATA` 保留用户数据。Setup 的 `/ACTION=Uninstall` 默认传递 `/PURGEDATA`；保留数据的命令如下：

```powershell
Insta360_HW_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /ACTION=Uninstall /PRESERVEDATA
```

## 仅移除 Cadence 集成

平台中的「移除 Cadence 集成」不是卸载：它只删除平台部署的 Capture Loader 和已挂载自定义脚本，不删除平台程序和 BOM 历史。操作后需重启 Capture；要恢复入口，使用「修复 Cadence 集成」。

## 异常处理

- **提示文件被占用**：先关闭平台和 OrCAD Capture，然后从同一标准入口重试。不要批量结束所有 `python.exe`，以免误伤其他工具。
- **找不到 `unins000.exe`**：重新运行同版本 `Insta360_HW_Setup.exe` 选择修复，再从 Windows 设置卸载。
- **卸载后 Capture 菜单仍在**：先重启 Capture。若仍存在，查看 `%LOCALAPPDATA%\Insta360_HW\logs\uninstall_latest.log`，不要删除非平台所有的 Tcl 脚本。
- **Windows 卸载条目损坏**：先用 Setup 修复卸载注册；修复仍失败时，将 `%LOCALAPPDATA%\Insta360_HW\logs\install_latest.log` 与 `uninstall_latest.log` 提供给维护人员。
