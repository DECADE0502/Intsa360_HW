# 硬件效率工具集安装说明

推荐安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

自定义安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "$env:LOCALAPPDATA\Insta360\HWAgent" -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```

安装完成后，重启 OrCAD Capture，并打开 Accessories -> 硬件效率工具集。
