# 硬件效率工具集安装说明

## 安装版（推荐）

双击 `Insta360_HW_Setup.exe`，按向导完成安装即可。安装程序会：

- 把平台部署到 `C:\Program Files\Insta360\HWAgent`（可在向导中修改）。
- 创建开始菜单快捷方式和可选的桌面快捷方式，均指向 `Insta360_HW.exe`。
- 自动检查并安装 Python 依赖（openpyxl）。
- 自动部署 Cadence（OrCAD Capture）菜单集成。

安装完成后，从开始菜单或桌面双击 **Insta360_HW** 启动平台。如已安装 Cadence，重启 OrCAD Capture 后会在 Accessories 菜单看到 insta360_HW 入口。

## 绿色版（免安装）

把整个目录拷贝到任意位置，双击 `Insta360_HW.exe` 即可。首次运行会自动完成依赖检查和 Cadence 集成部署。

## 自定义安装（脚本）

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

可指定安装目录和 Cadence 自动加载目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:LOCALAPPDATA\Insta360\HWAgent" -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```

安装完成后重启 OrCAD Capture，打开 Accessories -> 硬件效率工具集。
