# Insta360硬件提效平台交接文档

## 当前目标

用户要把 `D:\desktop\工具集\insta360_HWagent` 做成面向硬件研发的本地提效平台，平台名为 **Insta360硬件提效平台**。它需要覆盖：

- OrCAD Capture / Cadence 菜单集成。
- Capture BOM 导出并进入平台处理。
- PLM / OA BOM 处理、BOM 差异比较、BOM 风险检查、网表差异比较、贴片封装检查、单网络检查。
- 后续自研 Tcl 脚本和已有 OrCAD Tcl 脚本的统一管理、启用、更新。
- 一键安装、一键更新 / OTA，后续给大量同事同步使用。
- 前端要中文、流程自然、高效、美观，用户希望不要停留在手搓 UI 的粗糙状态。

## 仓库和当前状态

- 本地目录：`D:\desktop\工具集\insta360_HWagent`
- GitHub 仓库：`git@github.com:DECADE0502/Intsa360_HW.git`
- 当前远端 `main` 最新提交：
  - `4152a33 Fix Cadence default menu labels`
  - 初始首包提交：`665a94f Initial Insta360 hardware platform release`
- 本地 Git 状态最后检查为干净：`## main`

注意：推送使用本机 SSH key：

```text
C:\Users\Administrator\.ssh\id_ed25519_insta360_hw
```

## 最近完成的事情

### 1. GitHub 首包和 OTA 基础链路

已经把当前平台作为首包推到 `DECADE0502/Intsa360_HW`。

新增 / 修过：

- `.gitignore`
  - 排除 `data/`、`uploads/`、`outputs/`、`history/`、`config/local.json`、`frontend/node_modules/`、`frontend/dist/`、`.omc/`、`__pycache__` 等。
- `update.ps1`
  - 默认仓库改为 `https://github.com/DECADE0502/Intsa360_HW.git`，适合普通用户只读 OTA。
- `scripts/lib/Update.ps1`
  - 原先只支持安装目录本身是 Git 仓库时 `git pull`。
  - 现在补了普通文件夹更新路径：临时 clone 远端仓库，用 robocopy 镜像到安装目录，同时保护用户数据。
  - 保护项：`data`、`uploads`、`outputs`、`history`、`config/local.json`。
- `tests/test_distribution_install.py`
  - 增加普通文件夹从 Git 仓库更新的测试。

验证过：

- GitHub push 成功。
- HTTPS 只读 `ls-remote` 能看到远端 `main`。
- 临时旧安装目录 OTA 测试通过：旧文件被清理，`data` 和 `config/local.json` 保留。

### 2. Cadence 菜单乱码修复

用户截图显示 `insta360_HW` 下两个菜单项乱码。根因是 Capture 环境里中文菜单项在 GBK / Tcl / UI 链路中仍显示异常。

已改为英文默认菜单项：

- `Open Platform`
- `Export and Process BOM`

修改文件：

- `cadence/iac_bom_tool.tcl`
- `scripts/lib/Cadence.ps1`
- `scripts/diagnose_platform.ps1`
- `tests/test_cadence_loader.py`
- `tests/test_cadence_integration.py`

已经重新部署到：

- `D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl`
- `C:\Users\Administrator\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad\iac_bom_tool.tcl`

用户需要重启 OrCAD Capture 才能看到菜单刷新。

### 3. 之前已经完成并验证过的基础能力

这些来自前序工作，注意仍需复查真实体验：

- Cadence loader 已能注册 `insta360_HW` 顶部菜单。
- 默认菜单只保留两个入口，不再挂一堆未确认脚本。
- 旧增强脚本从 vendor autoload 中移走，避免 Capture 启动时 RegisterAction 冲突。
- `scripts/verify_capture_runtime.ps1` 可以启动真实 Capture 并等待 loader probe。
- `scripts/diagnose_platform.ps1` 可以检查：
  - autoload 中是否有禁用备份目录残留。
  - loader 是否包含默认菜单。
  - 是否加载旧增强脚本。
  - 是否改写 `RegisterAction`。
  - 平台 API 是否正常。
- BOM 处理曾用真实 IAC4 文件做过一次后端样本测试：
  - 源文件：`D:\desktop\IAC4功耗版\功耗版V2\IAC4_MB_POWER_V02_20260618A.xlsx`
  - 正确 BOM 参考：`D:\desktop\IAC4功耗版\最终交付_20260622\BOM导入资料\IAC4_MB_POWER_V02_PCBA_BOM.xlsx`
  - 后端能发现同编码描述冲突，支持确认合并 / 不合并。
  - PLM 输出确认有 19 列模板字段。

## 最近验证命令和结果

最后一次已跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\diagnose_platform.ps1
```

结果：通过，检查到英文菜单：

- `Open Platform`
- `Export and Process BOM`

最后一次已跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

结果：

- 88 个 unittest 通过。
- Python 编译通过。
- Vite build 通过。
- 只有 Vite chunk size warning。

## 明显还没有完整实现 / 需要 Claude 重点复查

### 1. “真正的大平台”还没做完整

当前平台更像一个能跑起来的工具集合 + 初版工作台，不是成熟平台。

需要补：

- 首页信息架构重新设计。
- 工具入口和任务流重新梳理。
- 脚本管理的状态、风险、启用、禁用、部署、回滚闭环。
- 更新日志、版本号、发布通道、失败回滚。
- 用户可理解的错误提示和修复建议。
- 多人安装使用文档和首装流程。

### 2. 前端 UI 仍不够优雅

当前前端已经是 React / Vite / Ant Design，但 UI 只是初版工作台。用户明确要求“流程自然高效美观”，这还没有达到。

需要做：

- 重新设计平台首页，而不是简单状态卡片。
- BOM 处理向导要更像硬件工程工作流：
  - Capture 导出状态。
  - 文件来源。
  - 字段识别。
  - 冲突合并。
  - 风险检查。
  - 最终打包。
- 冲突选择 UI 要更清楚，特别是“同物料编码但描述/型号/名称/等级不一致”时，应逐字段让用户选择保留哪一版。
- 所有 Web UI 仍要求中文。
- Cadence 菜单默认两项已改英文，是为了避免 Capture 乱码，不代表平台 UI 改英文。

### 3. “其他脚本”管理只是早期拆分状态

用户要求从 `D:\desktop\插件\orCAD_Enhanced_Tools_V1.8.tcl` 拆功能并集成。当前做了一部分拆分和注册，但不要认为完整。

现状：

- `config/capabilities.json` 中有 19 个 Cadence Tcl 能力。
- 默认 `show_in_cadence` 为 false。
- 平台可以看到脚本状态，并能启用部分脚本后重新生成 loader。
- 仍有“待拆分”概念。

风险 / 未完成：

- 每个拆出的 Tcl 功能是否真的在 Capture 里可用，没有逐个真实验证。
- 有些功能是从大脚本里拆的，可能存在隐藏依赖。
- 启用脚本后的菜单中文仍可能乱码。默认两个菜单已英文，但后续启用的 Tcl 脚本名大概率仍是中文，需要决定：
  - Cadence 菜单里全部用英文 / ASCII；
  - 或找到可靠编码方案。
- 高风险脚本例如删除图形、混淆、重命名等需要强提醒、权限控制和回滚设计。

### 4. BOM 字段映射仍需真实样本完善

用户强调 Capture 图里有很多字段，要尽可能补全。

当前有：

- `app/backend/capture_fields.py`
- `tools/bom/convert_cadence_bom.py`
- `app/backend/tools/bom_process.py`
- 相关测试 `tests/test_capture_bom_fields.py`

但需要继续做：

- 用真实 Capture 导出的 `_bom_data.json` 对照 Capture 属性窗口，确认 Tcl 真读到了哪些属性。
- 确认字段是否进入原始 xlsx。
- 确认字段是否正确映射到 PLM 19 列：
  - 父项编码
  - 描述
  - 子项编码
  - 名称
  - 型号
  - 描述
  - 单位
  - 数量
  - 位号
  - 备注
  - 物料优选等级
  - 物料优选等级备注
  - 替代组编码
  - 替代策略
  - 替代方式
  - 替代优先级
  - 发料方式
  - 是否参与MRP运算
  - 是否跳层
- 注意一个模板里有两个“描述”列，必须分清父项描述和子项描述。

### 5. Cadence 导出链路需要真实端到端复测

之前曾经出现“点击导出 BOM 不会自动导出到系统里面对接好”的问题。后来改过 loader 和启动逻辑，但必须重新真实验证。

建议 Claude 按这个顺序测：

1. 重启 OrCAD Capture。
2. 打开真实 DSN。
3. 点击 `insta360_HW -> Export and Process BOM`。
4. 看 Command Window：
   - 是否输出 `IAC: ExportAndProcess design name = ...`
   - 是否输出 `IAC: ReadParts count = ...`
5. 检查：
   - `D:\desktop\工具集\insta360_HWagent\data\inbox\_bom_data.json`
   - `D:\desktop\工具集\insta360_HWagent\data\inbox\<设计名>.xlsx`
6. 浏览器是否进入平台 BOM 处理页，并自动带入 source/name。
7. 完整跑 PLM/OA 输出和 zip 下载。

### 6. OTA 仍是基础版

当前 OTA 能从 GitHub 拉代码并保护数据，但不是完整商业级更新系统。

需要补：

- 版本对比：当前版本 vs 远端版本。
- 更新前备份当前代码。
- 更新失败回滚。
- 更新日志展示。
- 是否强制重启服务。
- 更新过程中前端显示实时日志，而不是只提示“已开始更新”。
- 远端仓库地址配置化，现在 `update.ps1` 默认 HTTPS，API 调用不传参数。

### 7. 测试覆盖偏“代码结构检查”，真实 UI / Capture 场景不足

现在很多测试是文本断言和后端单测，能防止明显回归，但不能替代真实验收。

需要补：

- Playwright 端到端测试：
  - 平台首页加载。
  - BOM 向导。
  - 冲突合并弹窗。
  - 文件上传与结果下载。
- 真实 Capture 自动化测试尽量保留：
  - `scripts/verify_capture_runtime.ps1`
  - 菜单 probe。
- 对每个 Tcl 脚本启用后的 Capture 行为做手工验收清单。

## 关键文件地图

后端：

- `app/backend/suite_app.py`：标准库 HTTP 服务入口。
- `app/backend/tool_registry.py`：6 个 Web 工具注册。
- `app/backend/capabilities.py`：平台能力 / Tcl 脚本能力注册表读取。
- `app/backend/tools/bom_process.py`：BOM 处理主逻辑。
- `app/backend/tools/analysis_tools.py`：BOM 比较、风险、网表、封装、单网络等分析。
- `app/backend/update_api.py`：版本和更新 API。

前端：

- `frontend/src/App.tsx`
- `frontend/src/platform/PlatformHome.tsx`
- `frontend/src/platform/ScriptManager.tsx`
- `frontend/src/tools/BomProcessWizard.tsx`
- `frontend/src/components/UpdateStatus.tsx`
- 构建后复制到 `app/frontend/`。

Cadence：

- `cadence/iac_bom_tool.tcl`：loader 模板。
- `scripts/lib/Cadence.ps1`：生成和安装 GBK loader。
- `scripts/redeploy_cadence_loader.ps1`：重部署 loader。
- `scripts/verify_capture_runtime.ps1`：真实 Capture loader probe 检查。
- `cadence/modules/*.tcl`：拆出的 Tcl 能力模块。
- `cadence/archive/orcad_enhanced_tools_reference.tcl`：旧增强脚本参考，不应直接加载。

安装 / 更新：

- `install.ps1`
- `update.ps1`
- `scripts/lib/Update.ps1`
- `scripts/lib/Paths.ps1`
- `scripts/lib/TclScripts.ps1`

测试：

- `scripts/verify_all.ps1`
- `scripts/diagnose_platform.ps1`
- `tests/test_distribution_install.py`
- `tests/test_cadence_loader.py`
- `tests/test_cadence_integration.py`
- `tests/test_capture_bom_fields.py`
- `tests/test_bom_process_conflicts.py`

## 建议 Claude 下一步优先级

1. 先做真实 Capture 端到端验收，确认 `Export and Process BOM` 能从 DSN 直接进平台并带入 xlsx。
2. 检查用户说“功能没有完整实现”的具体点，逐条列成验收清单，不要先大改 UI。
3. 把 Cadence 中后续可启用脚本的菜单名策略定下来。建议 Cadence 侧全部 ASCII 英文，平台 Web 侧全部中文。
4. 重做 BOM 冲突合并 UI：同编码不同描述/型号/名称/等级时逐字段选择保留值。
5. 完善 OTA：
   - 版本检查。
   - 更新日志。
   - 失败回滚。
   - 前端实时状态。
6. 重新设计前端信息架构和视觉，但不要破坏现有 6 个工具。
7. 每完成一块，都跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\diagnose_platform.ps1
```

如果动了 Cadence loader，再跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_capture_runtime.ps1 -CloseStartedCapture
```

## 给 Claude 的提醒

- 不要把 `data/`、`config/local.json`、`frontend/node_modules/`、`.omc/` 推到仓库。
- 不要直接把旧 `orCAD_Enhanced_Tools_V1.8.tcl` 放回 autoload；只能拆成模块，由平台注册表控制。
- Cadence 默认菜单已经改成英文是为了解决乱码，不要改回中文。
- Web 平台 UI 仍应保持中文。
- 用户很在意真实功能闭环，不要只做代码结构和测试文本断言。
- 每次说“完成”前必须给出实际验证命令和结果。
