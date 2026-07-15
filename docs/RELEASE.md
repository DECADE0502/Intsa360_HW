# Insta360 硬件提效平台本地发布流程

正式发布只在开发机编译一次。GitHub 不再重建前端、启动器、Python 运行时或 Setup。

## 签名密钥

`config/update_public_key.pem` 是已经随客户端发布的 OTA 信任锚，不能为每台开发机重新生成。日常构建或更换开发机时，从安全备份恢复与该公钥配对的私钥到：

```text
%LOCALAPPDATA%\Insta360_HW\release-keys\update_private_key.pem
```

运行正式构建时会先执行 `verify-key`，私钥与仓库公钥不匹配就立即停止，不会产出发布包。

只有在项目尚未建立信任锚、仓库中也不存在 `config/update_public_key.pem` 时，才允许执行一次初始化：

```powershell
.\scripts\build_release_bundle.ps1 -InitializeSigningKey
```

初始化命令把私钥保存到上述本地路径，把公钥写入 `config\update_public_key.pem`。私钥不得提交，必须单独安全备份；公钥必须经过审查并随代码提交。公钥已存在时，该命令会拒绝运行。丢失私钥后不能通过普通 OTA 更换信任锚。

## 构建

1. 更新 `VERSION` 与 `UPDATE_NOTICE.json`，提交全部代码。
2. 确认工作树干净，且仓库中不存在同版本标签。
3. 运行：

```powershell
.\scripts\build_release_bundle.ps1
```

命令会先执行完整测试，再构建前端、启动器、嵌入式 Python、`runtime-v3`、Setup、V3 根目录 ZIP、同字节的 0.3.3 文件名别名、V3 签名清单、0.3.3 过渡清单和 `SHA256SUMS.txt`，共六个发布文件。默认输出到仓库同级的 `Insta360_HW_release_<版本>`，同时把完全相同的 Setup 放到 `D:\desktop\工具集\Insta360_HW_Setup.exe`。

构建不会安装、更新、卸载或启动本机平台。

## 发布

```powershell
$env:GH_TOKEN = '<具有 contents/actions 权限的令牌>'
.\scripts\publish_release.ps1
```

先把同一提交推送或合并为 GitHub 默认分支的最新提交。发布脚本会再次本地验收，创建草稿 Release 并上传六个既有文件，然后触发 GitHub 验收。GitHub 只下载这些文件并复核提交、签名、哈希、兼容清单和运行包内容；通过后才把草稿公开。任何失败都会保留未公开草稿，不会退回远端编译。
