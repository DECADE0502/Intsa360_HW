# 硬件效率工具集回滚说明

如果更新后需要回滚：

1. 保留当前目录下的 `data` 和 `config/local.json`。
2. 使用你的 git 仓库切回上一个稳定版本，或重新解压上一版工具包。
3. 重新运行 `install.ps1` 安装 Cadence 菜单脚本。
4. 运行 `scripts\verify_all.ps1` 验证。

不要删除 `data\uploads`、`data\outputs` 或 `data\history`，这些目录保存用户上传文件、输出结果和历史记录。
