# Cadence 集成 · 设计与安装

把「Insta360 硬件提效平台」的入口集成进 OrCAD Capture，做到 **在 Cadence 里点一下 → 自动导出 BOM → 自动打开本地工具并带入该 BOM**。

围绕三件事设计：**入口集成 / 联动 / 安装便利**。

---

## 1. 入口集成（Capture 菜单 + 脚本）

Capture 支持 Tcl/Tk 脚本，可注册命令并加到菜单。本目录 `iac_bom_tool.tcl` 注册一个菜单组 **insta360_HW**，含两个命令：

| 菜单项 | 行为 | 可靠性 |
|---|---|---|
| **导出并处理** | 调用 `cadence_export.ps1`（COM 驱动 Capture 导出 BOM 到 inbox）→ 启动工具并带入该文件 | 依赖 Capture COM/版本，见 §2 |
| **打开 BOM 工具** | 仅启动工具的网页界面（不导出） | 任何版本都可用，兜底 |

> 说明：Capture 的 BOM 导出本身是 GUI 操作；不同版本的 Tcl/COM 接口略有差异。`cadence_export.ps1` 里**触发导出那一行**是唯一的版本相关配置点，已用注释标出，并给了两套可选实现 + 手动兜底。

## 2. 联动（Cadence → 本地工具，文件直传）

链路（全部已在工具侧实现并联通）：

```
Capture 菜单「导出并处理」
   └─ cadence_export.ps1 把 BOM 导出到  <tool>\data\inbox\cadence_bom.xlsx
        └─ exec  launch_tool_suite.ps1 -Source "<inbox>\cadence_bom.xlsx"
             └─ 启动器确保服务在跑，打开浏览器：
                  http://127.0.0.1:<port>/?tool=bom_process&source=<encoded path>
                   └─ 前端读取 ?source=，自动进入「BOM 处理」第 2 步，
                      预置该文件（无需再上传），点“开始处理”即可
```

关键点：
- 工具的 `source_bom` 接受**服务端绝对路径**，文件已在本机磁盘，**无需重新上传**。
- 启动器 `-Source` 参数把路径 URL 编码后拼到 `?source=`，前端 `loadTools()` 解析后预置。
- 之后流程照旧：处理 → **必走 BOM 检查** → 一键下载打包 zip。

## 3. 安装便利

`install_cadence_integration.ps1` 一键安装：
- 自动把本工具的**绝对路径**写进 `iac_bom_tool.tcl`（模板替换 `{{TOOL_ROOT}}`）。
- 复制到 Capture **真正自动加载**的目录：`%HOME%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\`
  （与 PartSolution 的 `PLMMenu.tcl` 同目录；SPB 17.4/24.x 通用）。会自动跟随已存在的 `PLMMenu.tcl` 定位。
- 创建 `data\inbox` 目录。
- 打印手动兜底步骤（若自动定位失败）。

> 菜单注册写法对齐了可用的 `PLMMenu.tcl`（`InsertXMLMenu` + `RegisterAction`，ASCII 菜单名）。

### 用法
```powershell
# 在本工具根目录执行
powershell -ExecutionPolicy Bypass -File cadence\install_cadence_integration.ps1
# 或指定自动加载目录：
powershell -ExecutionPolicy Bypass -File cadence\install_cadence_integration.ps1 -CaptureAutoLoadDir "D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"
```
装好后**重启 Capture**：菜单 **insta360_HW** 出现；也可在 Command Window 输入 `iac` / `iacx`。

---

## 手动兜底（不依赖 COM 自动导出）

若 COM 自动导出在你的 Capture 版本上不通：
1. 在 Capture 用 **Tools ▸ Bill of Materials**，把 Header/Combined property string 设为工具「BOM 处理 · 步骤1」给出的字符串，输出文件设到 `<tool>\data\inbox\cadence_bom.xlsx`。
2. 菜单点 **打开 BOM 工具**（或直接双击 `Insta360_HW.exe`），上传该文件即可。

即：联动失败也只是“多一步手动上传”，主流程不受影响。

