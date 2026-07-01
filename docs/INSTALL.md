# Insta360硬件提效平台安装说明

## 安装版（推荐）

双击 `Insta360_HW_Setup.exe`，按向导完成安装即可。安装程序会：

- 把平台部署到 `C:\Program Files\Insta360\HWAgent`（可在向导中修改）。
- 创建开始菜单快捷方式和可选的桌面快捷方式，均指向 `Insta360_HW.exe`。
- 部署平台自带的 Python 3.11 运行时，路径为 `runtime/python/`。
- 部署运行所需依赖，包括 `openpyxl`。
- 自动部署 Cadence（OrCAD Capture）菜单集成。

安装完成后，从开始菜单或桌面双击 **Insta360_HW** 启动平台。如果已安装 Cadence，重启 OrCAD Capture 后会在 Accessories 菜单看到 `insta360_HW` 入口。

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
