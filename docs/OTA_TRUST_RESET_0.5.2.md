# OTA 信任链重建说明（0.5.2）

## 原因

旧 OTA 私钥已经丢失，无法再生成能被 0.5.1 及更早客户端验证的更新清单。
Ed25519 私钥无法从仓库中的公钥或历史签名恢复，也不能通过普通 OTA 静默替换信任公钥。

## 迁移方式

1. 0.5.2 使用新的 OTA 签名密钥和公开信任锚。
2. 0.5.1 及更早版本必须手动运行 `Insta360_HW_Setup.exe` 安装 0.5.2。
3. 完成一次手动安装后，0.5.3 及后续版本可继续通过平台内 OTA 更新。
4. 用户数据、历史记录、本机配置和用户插件在安装过程中保留。

## 新信任锚

公开密钥文件：`config/update_public_key.pem`

密钥指纹：

```text
sha256:a0c7ca048ea23095ceafa81e301be56ac829483e5bf9b751db319c3a68dd1511
```

私钥仅保存在发布机：

```text
%LOCALAPPDATA%\Insta360_HW\release-keys\update_private_key.pem
```

私钥不得提交到 Git、发送到聊天或包含在 Setup/Runtime/OTA 文件中，必须另行安全备份。
