# 遗留开发脚本，不支持 v3 安装布局，日常请勿使用。
Write-Host "Please uninstall Insta360_HW from Windows Settings or run Insta360_HW_Setup.exe."
Start-Process "ms-settings:appsfeatures" | Out-Null
