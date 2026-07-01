# Insta360 硬件提效平台回滚说明

如果更新后需要回滚：

1. 保留当前目录下的 `data` 和 `config/local.json`（这些是你的用户数据）。
2. 使用你的 Git 仓库切回上一个稳定版本，或重新解压上一版工具包覆盖安装目录。
3. 重新运行 `install.ps1` 以安装 Cadence 菜单脚本。
4. 运行 `scripts\verify_all.ps1` 验证。

不要删除 `data\uploads`、`data\outputs` 或 `data\history`，这些目录保存用户上传文件、输出结果和历史记录。

## 备份位置

平台的备份和运行痕迹分散在两个位置：

- `%LOCALAPPDATA%\Insta360_HW\`：
  - `.ready`：首次启动完成标记。
  - `launcher.log`：启动日志，最多保留 5 份轮转。
  - `keep_data\<时间戳>\`：卸载时选择「保留数据」备份出的 `data`、`config/local.json`、`plugins/user`。
- `<install_root>\_hwagent_backup_<GUID>\`：更新过程中的临时回滚点。更新成功后会被清理；更新中途失败时保留，用于自动回滚。

## 手工回滚步骤

- **OTA 中途失败**：平台内的更新流程会自动回滚到 `_hwagent_backup_<GUID>`，重启平台即可恢复上一版本。
- **手工触发回滚**：

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\update.ps1 -AllowDowngrade
  ```

  然后指定旧版本包或旧版 Git 标签。

- **安装根目录半损**：重新运行 `Insta360_HW_Setup.exe`，向导会识别到已存在的安装并允许「覆盖安装 / Reinstall」；此操作不会清除 `data\` 和 `config\local.json`。
- **完全重装但保留数据**：先按 `docs/UNINSTALL.md` 的说明选择「保留数据」卸载，再运行新版安装包，最后从 `%LOCALAPPDATA%\Insta360_HW\keep_data\<时间戳>\` 手工复制数据回新的 `<install_root>\data\`。
