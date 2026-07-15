# Insta360 硬件提效平台安装说明

## 首次安装

双击 `Insta360_HW_Setup.exe`，按向导完成安装。Setup 会：

- 默认注册到 `C:\Program Files\Insta360\HWAgent`。
- 在该目录保留一个稳定入口 `Insta360_HW.exe` 和标准 Windows 卸载器。
- 把实际程序放入带版本与提交号的 `runtime\<版本+提交>` 目录。
- 把历史、输出、本机配置、用户插件和生命周期日志放到 `%LOCALAPPDATA%\Insta360_HW`。
- 部署带所有依赖的 Python 运行时，不使用电脑上已有的 Python。
- 只部署 Insta360_HW 自己拥有的 Cadence 加载器和已启用插件。

安装完成后可以从开始菜单、桌面快捷方式或安装目录中的 `Insta360_HW.exe` 进入平台。首次部署 Cadence 集成后，请重启 OrCAD Capture。

## 再次运行 Setup

Setup 会识别已有安装并提供与当前状态匹配的操作：

- **升级**：安装更高版本并迁移用户状态。
- **修复**：重新验证并恢复当前版本、稳定入口、卸载器与 Cadence 集成。
- **重新安装**：重新写入当前版本，适合运行时损坏。
- **卸载**：调用同一个标准 Windows 卸载器。

不完整或中断的安装会先自动恢复，再继续用户选择的操作。Setup 不会在后台执行平台内 OTA。

## 标准卸载

以下入口调用同一卸载链路：

- Windows 设置 → 应用 → 已安装的应用。
- 开始菜单中的卸载快捷方式。
- 再次运行 `Insta360_HW_Setup.exe` 后选择卸载。
- Geek Uninstaller 等读取标准卸载注册表的软件。

默认完整卸载会删除平台目录、用户状态及 Insta360_HW 自有 Cadence 集成，但不会删除 PLMTools 等第三方脚本。交互式卸载时可以明确选择保留用户数据。

## SmartScreen 与 UAC

当前 Setup 若未使用企业代码签名，Windows 可能显示 SmartScreen 提示。确认文件来自正式 Release 并核对 `SHA256SUMS.txt` 后，可点击「更多信息」→「仍要运行」。安装到 Program Files、修复和卸载都需要管理员授权。

## 企业静默安装

```powershell
Insta360_HW_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR="D:\Insta360_HW" /LOG="D:\Logs\insta360-hw-setup.log"
```

静默安装使用默认安装/升级决策，不弹出维护选项。批量部署前应先在与目标电脑一致的 Cadence 16.6 或 17.4 环境中验证。
