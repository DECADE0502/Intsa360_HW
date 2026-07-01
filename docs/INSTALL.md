# Insta360 硬件提效平台安装说明

## 安装版（推荐）

双击 `Insta360_HW_Setup.exe`，按向导完成安装即可。安装程序会：

- 把平台部署到 `C:\Program Files\Insta360\HWAgent`（可在向导中修改）。
- 创建开始菜单快捷方式和可选的桌面快捷方式，均指向 `Insta360_HW.exe`。
- 部署平台自带的 Python 3.11 运行时，路径为 `runtime/python/`。
- 部署运行所需依赖，包括 `openpyxl`。
- 自动部署 Cadence（OrCAD Capture）菜单集成。

安装完成后，从开始菜单或桌面双击 **Insta360_HW** 启动平台。如果已安装 Cadence，重启 OrCAD Capture 后会在 Accessories 菜单看到 `insta360_HW` 入口。

## SmartScreen 警告

Windows 10/11 首次运行未签名的 `Insta360_HW_Setup.exe` 时，可能弹出「Windows 已保护你的电脑」提示：

- 点击「更多信息」→「仍要运行」即可继续。
- 长期规避：企业 IT 可以把 `Insta360_HW_Setup.exe` 加入 SmartScreen / EDR 白名单，或使用内部代码签名重新签发。
- 已经保存到磁盘的安装包，可以在文件属性里勾选「解除锁定」再运行，避免每次都触发提醒。

## UAC 提示

- 默认安装目录为 `C:\Program Files\Insta360\HWAgent`，安装过程需要管理员权限。
- 弹出 UAC「是否允许此应用对你的设备进行更改」时点击「是」。
- 非管理员账户无法通过 Windows 设置卸载平台；如需完全卸载，请让 IT 或本机管理员操作。
- 若希望免 UAC，可把安装目录换成 `%LOCALAPPDATA%\Insta360\HWAgent`（见下方脚本安装），但会失去为所有用户共享安装的能力。

## 静默安装（企业分发）

安装向导底层是 Inno Setup，支持标准静默参数，可用于批量部署：

```
Insta360_HW_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR="D:\Insta360_HW"
```

- `/VERYSILENT`：不显示任何 UI，包括进度条。
- `/SUPPRESSMSGBOXES`：抑制普通消息框（配合 `/VERYSILENT` 使用）。
- `/DIR=<目录>`：覆盖默认安装目录。
- `/LOG=<file>`：把安装日志写到指定文件，便于事后排查。
- Cadence 集成会在安装脚本内异步部署；如遇失败请参见下文「Cadence 集成失败恢复」。

## 首次启动 30–60 秒

首次启动时平台会做一次性初始化：

- 内嵌 Python 运行时预热，加载 `openpyxl` 等依赖。
- Cadence 集成脚本部署到 `%USERPROFILE%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\`。
- 默认浏览器会打开 `waiting.html`，看到「正在启动本地服务」文案属正常现象。

初始化完成后浏览器会自动跳转到平台工作台；此后启动通常在 5 秒内完成。

## Cadence 集成失败恢复

- 平台启动后进入「系统状态」页，如果显示 `OrCAD Capture 未检测到` 或 `Cadence 菜单未挂载`，说明集成部署失败。
- 检查 OrCAD 是否已经安装：确认 `%USERPROFILE%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\` 目录存在。
- 手动重新部署：平台 → 系统状态 → 「重新部署 Cadence 集成」按钮，或运行：

  ```powershell
  powershell -ExecutionPolicy Bypass -File cadence\install_cadence_integration.ps1
  ```

- 若仍失败，可以按 `docs/UNINSTALL.md` 中「移除 Cadence 集成」的说明清理，再重新运行部署。

## 绿色版（免安装）

把完整目录复制到任意位置，双击 `Insta360_HW.exe` 即可。绿色版也应包含 `runtime/python/`，不依赖用户电脑已有的 Python。

## 自定义安装（脚本）

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

可指定安装目录和 Cadence 自动加载目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:LOCALAPPDATA\Insta360\HWAgent" -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```

安装完成后重启 OrCAD Capture，打开 Accessories -> insta360_HW。
