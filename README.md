# Insta360 硬件提效平台

面向硬件工程师的本地提效工具，覆盖从 OrCAD Capture 导出、BOM 整理与审查，到网表、封装和贴片资料复核的常用流程。

## 主要工具

- **BOM 处理**：把 Capture 原始 BOM 转成 PLM/OA 成品 BOM，并处理 NC、屏蔽支架和编码冲突。
- **BOM 差异比较**：按位号、物料编码和用量识别换料、新增、删除及其他版本差异。
- **BOM 风险检查**：检查裸板、屏蔽支架、NC、机构件、优选等级、数量和位号类型等风险。
- **网表差异比较**：比较两版 `pstxnet.dat` / `pstxprt.dat` 的网络、节点、Pin 和封装变化。
- **贴片封装检查**：核对处理后 BOM 与网表封装、型号和描述是否一致。
- **贴片布局对照**：结合 `XY.txt`、板框、处理后 BOM 和可选网表，完成 NC 布局、首件核对和三向一致性检查。
- **单网络检查**：提取 NC 网络和只有单一位号的网络，辅助出图前检查。
- **插件管理**：统一查看和挂载 Capture Tcl 工具。

## 使用入口

安装后运行 `Insta360_HW.exe` 进入平台；也可以在 OrCAD Capture 的 `insta360_HW` 菜单中打开平台或导出并处理当前设计 BOM。

完整安装、操作、更新和故障处理说明见 [平台使用说明](docs/Insta360_HW_Platform_Guide.md)。

## 发布前检查

维护人员在构建发布包后运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\pre_release_check.ps1
```

检查会覆盖 Python 测试、前端单元测试、前端生产构建、PowerShell 语法和已签名发布包验证。
