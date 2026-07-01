# Insta360 硬件提效平台卸载指南

## 卸载入口

平台**不提供** Web 界面卸载按钮（避免 Web 服务自删的踩坑）。三种卸载方式：

### 1. Windows 设置 → 应用 → Insta360_HW → 卸载（推荐）

弹出「保留 / 完全清除」对话框：

- **是（保留数据）** = 保留 `data\`、`config\local.json`、`plugins\user\`，并把它们备份到 `%LOCALAPPDATA%\Insta360_HW\keep_data\<时间戳>\`。
- **否（完全清除）** = 完全清除 `<install_root>` 与 `%LOCALAPPDATA%\Insta360_HW\` 下的所有内容，包括之前保留的 `keep_data`。

### 2. 平台前端 → 「移除 Cadence 集成」

**仅移除** OrCAD Capture 菜单集成，不停止平台服务，不删除数据：

- 会删除 `%USERPROFILE%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\` 下由平台部署的 Tcl 脚本。
- 之前为了避让冲突而被禁用的 vendor 脚本（`_disabled_custom_scripts_*`）会被还原到 auto-load 目录。
- 重启 OrCAD Capture 后，`insta360_HW` 菜单消失，原有第三方菜单恢复。

### 3. 命令行

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode Detach -InstallDir "C:\Program Files\Insta360\HWAgent"          # 保留数据
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Mode Full   -InstallDir "C:\Program Files\Insta360\HWAgent" -Force   # 完全清除
```

- `-Mode Detach`：等价于「保留数据」，会生成 `keep_data\<时间戳>\` 备份。
- `-Mode Full -Force`：等价于「完全清除」，跳过所有交互，谨慎使用。
- `-InstallDir`：如果自定义过安装目录，需要显式传入实际路径。

## 常见问题

**Q: 卸载时提示「文件被占用」怎么办？**
A: 平台服务正在运行。Inno Setup 的 `PrepareToInstall` 阶段会尝试自动停止服务；若失败，请手动执行 `taskkill /IM python.exe /F` 或从任务管理器结束 `Insta360_HW.exe`，再重试卸载。

**Q: 卸载后 OrCAD Capture 里的菜单还在？**
A: 需要重启 Capture 才能让菜单变更生效。若重启后仍在，请检查 `%USERPROFILE%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\` 是否残留 `iac_bom_tool.tcl` 或 `insta360_hw_*.tcl`，可以手工删除。

**Q: 保留的数据在哪里、怎么恢复？**
A: 位于 `%LOCALAPPDATA%\Insta360_HW\keep_data\<时间戳>\`，含 `data\`、`config\local.json`、`plugins\user\`。重新安装后，把这些内容手工复制回新的 `<install_root>\` 即可继续使用旧的历史记录和自定义脚本。

**Q: 完全清除的数据可以恢复吗？**
A: 不能。`Mode Full` 会彻底删除 `%LOCALAPPDATA%\Insta360_HW\`，包括 `keep_data`。请在卸载前手工备份重要的 BOM、网表历史和自定义脚本。

**Q: 卸载后 Windows 设置里的条目还在？**
A: Inno Setup 在成功卸载后会自动移除注册表项。如果异常中断，可以再次运行 `Insta360_HW_Setup.exe` 选择「修复」，然后再走一次卸载流程。
