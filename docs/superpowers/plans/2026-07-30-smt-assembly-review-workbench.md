# SMT 装配审查工作台重构计划

> 基线：`0.5.11`，提交 `c62f17d`
>
> 目标：把现有“坐标灰块板面”重构为“真实位号图底图 + 坐标热点 + BOM/NC 语义 + 审核留痕”的 SMT 装配审查工作台。
>
> 发布约束：全部任务、真实样本、前后端构建和输出回读通过前，不升版本、不构建安装包、不发布 OTA。

## 1. 已确认的产品结论

1. 默认主视图使用供应商位号图，不再用自绘灰块模拟真实 PCB。
2. 坐标文件只提供结构化位置、面别、旋转和点击热点，不负责生成板面细节。
3. 现有 `PcbCanvas` 不删除，改名并收敛为“坐标诊断视图”，用于无底图、配准失败和解析排错。
4. 用户只选择：
   - SMT 资料目录；
   - 已处理的 PLM/OA BOM；
   - 可选 Cadence 网表。
5. `decision_manifest`、`semantic_manifest` 继续由历史资产自动关联，禁止重新暴露为普通用户上传项。
6. NC 不能无条件等于 `XY - BOM`。只有坐标来源被证实为完整位号集合时才能形成“确认 NC”；来源语义未知时只能形成“候选 NC”。
7. 文件名、位号前缀和描述都是证据，不能作为单一决定条件。
8. 配准不确定时必须进入确认或校准，禁止把“看起来差不多”的热点静默叠加到位号图。
9. 第一阶段先交付可靠的人工选择页面和三点校准闭环，不以 OCR/全自动配准完成为前置条件。
10. 本工具不是 Gerber、ODB++、IPC-2581、3D PCBA 或贴片机程序编辑器。

## 2. 当前实现盘点

### 2.1 可直接复用

- `app/backend/parsers/xy.py`
  - 已支持当前 `XY.txt` 的 `!` 分隔格式；
  - 已读取单位、面别、坐标、旋转、封装和源行。
- `app/backend/parsers/board_outline.py`
  - 已支持 DXF、Gerber 包围框和器件坐标降级板框；
  - 可继续服务坐标诊断视图。
- `app/backend/tools/smt_layout.py`
  - 已关联处理后 BOM、内部决策记录和可选网表；
  - 已有 NC 证据、三向一致性、首件表和输出能力。
- `frontend/src/components/RefdesVirtualList.tsx`
  - 已有大列表虚拟滚动、选中和悬浮联动。
- `frontend/src/state/toolWorkspace.ts`
  - 已能在切换工具后保留重型结果。
- `frontend/src/components/PcbCanvas.tsx`
  - 已有缩放、平移、框选、正反面、热点选择；
  - 改为诊断模式后继续复用。

### 2.2 必须替换

- 前端只接受 `XY.txt + DXF/ART/Gerber`，会直接丢弃 PDF、PNG、JPG。
- 后端 `_find_xy_file()` 写死 `XY.txt`，不支持供应商坐标格式适配。
- 当前只生成一次性 `run_smt_layout` 结果，没有“识别、配准、审核、决策”多阶段状态。
- `SmtBoard` 只有板框，没有位号图页面、底图资源和坐标变换。
- `SmtComponent` 把原始坐标、标准坐标、图像坐标和判定状态混在一个对象中。
- NC 推导没有显式表达坐标文件的范围语义。
- 所有热点用 SVG `<rect>` 绘制，位号图、空间索引和分级显示均不存在。
- 输入区在分析后仍占据主空间，不符合高频审查工作流。

### 2.3 真实样本暴露的通用问题

`IAC4_MB_V05贴片资料` 同时包含：

- SMD 位号图 PDF；
- 原理图 PDF；
- 拼板 DXF；
- 装配 DXF；
- 多个钢网 ART；
- `XY.txt`；
- 3D STEP；
- 压缩包。

因此不能使用“PDF 就是位号图”“最大 DXF 就是板框”“文件名含 TOP/BOTTOM 就直接确认”等规则。识别对象必须细化到 PDF 页面、Excel 工作表和坐标数据集，并输出证据与置信状态。

## 3. 目标用户流程

### 阶段 A：选择资料

用户选择三项输入。系统扫描整个 SMT 目录，不要求用户先理解文件类型、单位、原点和镜像。

扫描完成后显示：

- 位号图候选和页面数量；
- 坐标文件候选及有效位号数量；
- BOM 装机位号数量；
- 正反面候选；
- 坐标来源范围语义；
- 需要确认的问题。

### 阶段 B：识别与配准

结果分三种：

- `ready`：证据充分，可直接进入工作台；
- `needs_confirmation`：给出少量页面/方向候选；
- `needs_calibration`：用户选择页面并点选至少三个分散锚点。

用户不直接填写矩阵、缩放比例、原点或镜像参数。

### 阶段 C：异常优先复核

默认只显示：

- 数据冲突；
- BOM 有、坐标无；
- 坐标有、BOM 无；
- 候选 NC；
- 工艺/机械对象待分类；
- 配准离群点。

正常装机器件保留可查，但默认降低视觉权重。

### 阶段 D：确认与交付

用户确认异常结论，不逐颗确认正常器件。导出：

- SMT 装配审查报告；
- 位号明细；
- 正反面标注图；
- 机器可读分析快照；
- 首件核对表；
- 未解决阻断项。

## 4. 领域模型

### 4.1 输入与解析

```text
SmtAnalysisRun
  run_id
  schema_version
  parser_version
  rule_version
  state
  source_fingerprint
  sources[]
  coordinate_sets[]
  drawing_pages[]
  registrations[]
  placements[]
  decisions[]
  summary
```

```text
SourceAsset
  asset_id
  relative_path
  sha256
  media_type
  file_size
  roles[]
  classification_state
  evidence[]
  pages_or_sheets[]
```

文件角色至少包括：

- `placement_coordinate`
- `assembly_drawing`
- `schematic_drawing`
- `panel_drawing`
- `stencil_data`
- `board_outline`
- `bom`
- `netlist`
- `unrelated`
- `unknown`

### 4.2 坐标数据

```text
CoordinateSet
  coordinate_set_id
  adapter_id
  source_asset_id
  sheet_or_section
  declared_unit
  normalized_unit
  unit_state
  scope_semantics
  side_mapping
  rotation_semantics
  quality_report
  occurrences[]
```

`scope_semantics` 固定为：

- `full_design_set`
- `placement_only`
- `smt_only`
- `unknown`

`CoordinateOccurrence` 必须同时保存：

- 原始位号及规范化位号；
- 原始 X/Y；
- 规范化 X/Y；
- 原始单位及确认状态；
- 原始面别及规范化面别；
- 原始旋转及旋转语义状态；
- 封装；
- 源文件、工作表/区段和源行；
- 解析警告。

### 4.3 位号图与配准

```text
DrawingPage
  page_id
  source_asset_id
  page_number
  pixel_width
  pixel_height
  page_rotation
  crop_rect
  side_candidate
  drawing_role
  preview_asset
  tile_manifest
  extracted_refdes[]
```

```text
Registration
  registration_id
  coordinate_set_id
  page_id
  side
  model
  transform
  anchors[]
  validation
  confidence_state
  decision_source
```

`model` 第一版只允许：

- `similarity`
- `similarity_with_mirror`
- `affine`

透视变换不进入第一版自动主链。高自由度模型不得用来掩盖错页、错面或错版本。

`confidence_state` 固定为：

- `verified`
- `needs_confirmation`
- `needs_calibration`
- `rejected`

配准验证保存：

- 锚点数量；
- 锚点空间覆盖情况；
- 内点比例；
- 重投影误差分布；
- 映射后落在有效区域的比例；
- 最优和次优候选差距；
- 镜像/面别歧义；
- 验证证据和阻断原因。

具体自动通过阈值必须由真实样本校准并配置化，计划阶段不硬编码未经验证的数值。

### 4.4 装机状态与证据

```text
Placement
  placement_id
  ref
  side
  coordinate_occurrence_ids[]
  bom_requirement
  netlist_evidence
  drawing_evidence
  role
  assembly_state
  blocking_reasons[]
  evidence_chain[]
  decision
```

`role` 至少包括：

- `smt_component`
- `tht_component`
- `manual_assembly`
- `fiducial`
- `tooling_hole`
- `mounting_hole`
- `test_point`
- `mechanical`
- `panel_object`
- `unknown`

`assembly_state` 固定为：

- `installed`
- `confirmed_nc`
- `candidate_nc`
- `non_smt`
- `bom_only`
- `coordinate_only`
- `conflicting`
- `unresolved`

每个结论都必须有有序证据链，不能只返回最终颜色。

### 4.5 用户决策

```text
SmtDecision
  decision_id
  placement_id
  action
  reason
  source
  input_fingerprint
  rule_version
  operator
  created_at
```

动作包括：

- 确认为装机；
- 确认为 NC；
- 标记为工艺对象；
- 标记为非 SMT/手工焊；
- 暂不确定；
- 修正角色；
- 添加说明。

历史决策只在输入指纹、规则版本和关键属性满足复用契约时自动应用，否则只显示提示。

## 5. NC 与异常判定规则

### 5.1 核心集合

```text
R_COORD       坐标中的唯一位号
R_FULL        经确认的完整设计位号集合
R_BOM_POP     BOM 中实际装机位号
R_NET         网表电气位号
R_DRAWING     位号图提取位号
R_PROCESS     工艺、孔、Mark、机械和拼板对象
R_EXPLICIT_NC 内部处理记录明确标记的 NC
```

### 5.2 判定

- 坐标范围为 `full_design_set` 且输入无阻断：
  - `R_FULL - R_BOM_POP - R_PROCESS` 可形成系统判定 NC。
- 坐标范围为 `unknown`：
  - `R_COORD - R_BOM_POP - R_PROCESS` 只能形成候选 NC。
- `R_BOM_POP - R_COORD` 不能直接叫漏贴，必须区分插件、手工焊、机械件、缺面、坐标漏项和版本不一致。
- 网表只提供增强证据，不能单独证明装机或 NC。
- 内部语义清单继续优先提供明确装机/NC/其他非 SMT 决策，但前端不展示“清单”概念。
- 主料和替代料先归并为同一个装配位置，替代料空位号不能重复计数。

### 5.3 必须阻断或降级

- 同一组件位号出现在不同坐标或不同面；
- BOM 同一位号被两个非替代物料占用；
- 数量与展开位号不一致且影响当前结论；
- 正反面或镜像候选无法区分；
- 坐标与图来自不同版本；
- 页面包含多个板但未选择分析区域；
- 坐标大量落在底图有效区域外；
- 配准依赖少量、共线或局部集中的锚点；
- 坐标范围语义未知却试图输出确认 NC；
- 缺失的一面被误当成 NC。

## 6. API v2

保留旧 `/api/tools/smt_layout/run` 作为一个版本周期的兼容入口，但新前端只使用 v2 多阶段 API。

### 6.1 创建分析

```http
POST /api/smt-analysis/runs
```

输入：

- SMT 上传目录；
- BOM 资产；
- 可选网表资产；
- 自动关联的内部处理记录。

输出：

- `run_id`
- 识别状态
- 文件/页面/坐标候选
- 阻断与确认项

### 6.2 查询状态

```http
GET /api/smt-analysis/runs/{run_id}
```

返回轻量运行状态、摘要和待处理问题，不默认返回全部器件详情。

### 6.3 选择输入候选

```http
PUT /api/smt-analysis/runs/{run_id}/selection
```

提交：

- 正反面页面；
- 坐标数据集；
- 页面裁切区域；
- 坐标范围语义的用户确认。

### 6.4 自动配准

```http
POST /api/smt-analysis/runs/{run_id}/registrations:auto
```

返回候选变换、验证指标和状态。不得在失败时伪造成功板面。

### 6.5 提交校准

```http
PUT /api/smt-analysis/runs/{run_id}/registrations/{side}
```

提交锚点、页面、裁切、方向和用户确认。

### 6.6 查询位号

```http
GET /api/smt-analysis/runs/{run_id}/placements
```

支持：

- 面别；
- 状态；
- 角色；
- 当前视口 `bbox`；
- 搜索；
- 审核状态；
- 分页游标。

首屏返回轻量热点索引，完整证据详情按位号请求。

### 6.7 决策与导出

```http
POST /api/smt-analysis/runs/{run_id}/decisions
POST /api/smt-analysis/runs/{run_id}/decisions:batch
POST /api/smt-analysis/runs/{run_id}/exports
```

导出绑定分析运行、决策快照和未解决阻断，保证刷新、切换工具和重新打开后结果一致。

### 6.8 底图资源

```http
GET /api/smt-analysis/runs/{run_id}/pages/{page_id}/preview
GET /api/smt-analysis/runs/{run_id}/pages/{page_id}/tiles/{level}/{x}/{y}
```

所有路径由服务端资产 ID 映射，禁止把任意本地路径直接暴露为下载接口。

## 7. 前端工作台

### 7.1 输入页

- 三个紧凑输入区域；
- 目录扫描后显示内容识别摘要；
- PDF、PNG、JPG、JPEG、TXT、CSV、XLS、XLSX、DXF、ART、GBR、GER 可进入后端识别；
- 不在前端按文件名提前丢弃可能有用的资料；
- 无选择时不显示占据整屏的大型空白上传框。

### 7.2 配准页

- 左侧页面候选；
- 中间叠加预览；
- 右侧候选方向、证据和阻断；
- 支持原图/叠加透明度滑块；
- 支持选择位号后在图上点锚点；
- 支持撤销、清空、重新自动配准；
- 三个以上分散锚点作为默认人工校准路径；
- 用户只确认“这个叠加正确”，不编辑矩阵。

### 7.3 审查工作台

```text
顶部：项目/版本、输入健康、配准状态、正反面、搜索、导出
左侧：状态统计、筛选、图层
中间：位号图底图与热点
右侧：异常/位号虚拟列表
底部：可收起证据详情抽屉
```

- 进入工作台后输入区折叠为文件标签；
- 中间板面获得主要宽度；
- 无异常列表时板面自动占满；
- 点击列表定位并缩放到热点；
- 点击热点选中列表；
- 支持上一异常/下一异常；
- 支持框选和批量确认；
- 重叠热点显示候选列表；
- 正反面分开显示数量和配准状态；
- 底面镜像视图必须明确标记当前方向。

### 7.4 图层与视觉

- 位号图底图；
- 状态热点；
- 当前选择；
- 搜索结果；
- 异常标记；
- 可选位号文本；
- 可选旋转方向；
- 配准锚点；
- 坐标诊断层。

热点默认使用小型符号，不再覆盖整板：

- 正常装机：低权重圆点；
- 确认 NC：带斜杠符号；
- 候选 NC：空心环；
- 待确认：菱形/问号；
- 冲突：警告三角；
- 当前选择：高亮环。

颜色必须辅以形状，不能仅靠红黄蓝区分。

### 7.5 渲染技术

- 底图使用 Canvas/瓦片层；
- 热点使用 Canvas 2D；
- 当前悬浮、选中和详情使用少量 DOM；
- 位号列表继续使用虚拟滚动；
- 热点使用 R-tree 或等价空间索引；
- 缩放级别控制标签和热点细节；
- `PcbCanvas` 改为 `CoordinateDiagnosticView`，不再作为默认主视图。

第一版不引入 WebGL。只有真实样本证明 Canvas 2D 无法达到验收基线时再评估。

## 8. 缓存与增量更新

缓存键：

```text
文件解析       文件哈希 + 解析器版本
页面预览       文件哈希 + 页码 + 旋转 + 裁切
页面瓦片       页面指纹 + 层级 + tile 坐标
配准           坐标指纹 + 页面指纹 + 配准引擎版本
装机判定       坐标集合指纹 + BOM 指纹 + 规则版本 + 决策快照
```

增量规则：

- 只换 BOM：不重新解析/栅格化位号图，不重新配准；
- 只改用户决策：只更新相关位号、统计和审计事件；
- 换坐标：重做坐标解析、面别验证、配准和装机判定；
- 换位号图：保留 BOM/坐标解析，重做页面识别和配准；
- 切换工具：运行状态和用户决策不丢失。

## 9. 实施任务

### T0：固化基线和真实样本预期

**范围**

- 记录 0.5.11 当前输入、响应、截图、性能和测试结果；
- 为 IAC4 V05 资料建立不入仓的本地 golden 描述；
- 记录 SMD PDF、原理图 PDF、拼板 DXF、装配 DXF、钢网 ART、XY 的正确角色；
- 保存当前 1037 器件、正反面数量、现有 NC 分类和首件输出作为迁移对照；
- 明确坐标文件在该样本中是否包含 NC，不能自行推断。

**文件**

- 新建 `tests/fixtures/smt/README.md`
- 新建 `tests/fixtures/smt/contracts/*.json`
- 修改 `docs/Insta360_HW_Platform_Guide.md`

**验收**

- golden 仅保存脱敏结构、哈希和人工确认预期；
- 不把公司原始资料提交仓库；
- 当前主链测试保持通过。

### T1：建立 v2 领域契约

**范围**

- 在 Pydantic 和 TypeScript 中实现第 4 节模型及枚举；
- 明确版本和有限数值校验；
- 建立 JSON round-trip fixture；
- 不修改解析和 UI 行为。

**文件**

- 新建 `app/backend/contracts/smt_analysis.py`
- 新建 `frontend/src/tools/smtAnalysis/types.ts`
- 新建 `tests/test_smt_analysis_contract.py`
- 新建 `frontend/src/test/smt-analysis-contract.test.ts`

**依赖**

- T0

**验收**

- 后端和前端共享 fixture；
- 任一字段或枚举漂移会使契约测试失败；
- 旧 `SmtLayoutResponse` 暂时保留。

### T2：资料扫描和内容分类

**范围**

- 递归扫描上传目录并建立 `SourceAsset`；
- 分类到文件、PDF 页面和 Excel 工作表级；
- 文件名仅作为加权证据；
- 区分位号图、原理图、拼板、钢网、板框和未知资料；
- 输出候选、证据和待确认状态，不做配准。

**文件**

- 新建 `app/backend/smt_analysis/ingest.py`
- 新建 `app/backend/smt_analysis/classifiers.py`
- 新建 `tests/test_smt_ingest.py`
- 新建 `tests/fixtures/smt/ingest/`

**依赖**

- T1

**验收**

- 同目录多个 PDF/DXF 时不按最大文件或扩展名静默选择；
- IAC4 V05 的 SMD PDF 与原理图 PDF 不混淆；
- 未识别资料保留，不静默丢弃；
- RAR、STEP 等不支持格式被标记而不是导致分析失败。

### T3：坐标适配器注册表

**范围**

- 把现有 `XY.txt` 解析改为第一个适配器；
- 增加通用 CSV/TXT/XLS/XLSX 探测框架；
- 支持编码、分隔符、表头行、列类型和数据区识别；
- 输出原始值、规范化值、来源和质量报告；
- 单位、面别、旋转不明确时保持未知。

**文件**

- 新建 `app/backend/smt_analysis/coordinates/base.py`
- 新建 `app/backend/smt_analysis/coordinates/cadence_xy.py`
- 新建 `app/backend/smt_analysis/coordinates/tabular.py`
- 修改 `app/backend/parsers/xy.py`
- 新建 `tests/test_smt_coordinate_adapters.py`

**依赖**

- T1

**验收**

- 现有 XY fixture 解析结果不回归；
- 不依赖固定文件名；
- 坐标列误判时返回候选/阻断，不交换 X/Y 猜测后静默继续；
- 未确认单位不能标成 mm。

### T4：位号图页面和本地底图资产

**范围**

- 先提交依赖选型 ADR，对 `pdfjs-dist`、PDFium 系方案及现有运行时兼容性进行离线构建、许可证、体积和性能验证；
- 未经公司许可证策略确认，不引入具有分发约束的 PDF/OCR 依赖；
- 支持 PDF、PNG、JPG/JPEG；
- PDF 按页面建立 `DrawingPage`；
- 生成低清预览和按需清晰资源；
- 保留页面旋转、裁切和原始尺寸；
- 建立受限资产访问 API；
- 第一阶段不依赖 OCR。

**文件**

- 新建 `docs/adr/smt-pdf-rendering.md`
- 新建 `app/backend/smt_analysis/drawings.py`
- 新建 `app/backend/smt_analysis/page_cache.py`
- 新建 `app/backend/routes/smt_analysis_assets.py`
- 新建 `tests/test_smt_drawing_pages.py`
- 修改运行时依赖和发布收集脚本

**依赖**

- T1、T2

**验收**

- 多页 PDF 每页可独立预览；
- 原理图页不会被强制当板面页；
- 超大页面不会一次生成无上限位图；
- 路径穿越测试通过；
- 安装版离线可渲染，不依赖在线 CDN。

### T5：纯配准引擎

**范围**

- 实现相似、镜像相似和仿射模型；
- 支持人工锚点求解；
- 枚举旋转/镜像候选；
- 计算验证指标、候选排序和阻断原因；
- 自动配准接口先允许没有候选，禁止伪成功；
- OCR/矢量位号自动锚点作为后续插件，不耦合核心求解。

**文件**

- 新建 `app/backend/smt_analysis/registration.py`
- 新建 `app/backend/smt_analysis/registration_validation.py`
- 新建 `tests/test_smt_registration.py`

**依赖**

- T1

**验收**

- 合成变换可 round-trip；
- 共线、重复、集中锚点被拒绝；
- 错面、错页和双候选接近返回待确认；
- 变换结果幂等且无 NaN/Infinity；
- 自动阈值从配置读取，未校准前默认保守。

### T6：装机语义与 NC 引擎

**范围**

- 从 `smt_layout.py` 拆出纯集合/证据判定；
- 引入坐标范围语义；
- 主料/替代料归并为装配位置；
- 工艺和机械对象分类；
- 接入内部 BOM 语义记录和可选网表；
- 输出状态、证据链和阻断原因。

**文件**

- 新建 `app/backend/smt_analysis/assembly.py`
- 新建 `app/backend/smt_analysis/roles.py`
- 新建 `app/backend/smt_analysis/evidence.py`
- 修改 `app/backend/tools/smt_layout.py`
- 新建 `tests/test_smt_assembly_engine.py`

**依赖**

- T1、T3

**验收**

- `unknown` 坐标范围绝不输出自动确认 NC；
- 替代料不重复增加实际位号数；
- 工艺对象不混入 NC；
- BOM 有坐标无和坐标有 BOM 无分别输出；
- 网表不能单独把位号判成装机/NC；
- 旧语义清单继续自动生效。

### T7：分析运行、缓存和决策持久化

**范围**

- 建立运行仓库、状态机和缓存；
- 输入变化精确失效；
- 保存页面选择、配准、审核决策和输出快照；
- 工具切换/刷新后恢复；
- 失败任务可重试且不污染成功快照。

**文件**

- 新建 `app/backend/repositories/smt_analysis_repository.py`
- 新建 `app/backend/services/smt_analysis_service.py`
- 新建 `app/backend/routes/smt_analysis.py`
- 新建 `tests/test_smt_analysis_repository.py`
- 新建 `tests/test_smt_analysis_api.py`

**依赖**

- T1；可与 T2-T6 并行开发，汇合时接入

**验收**

- 同输入和版本命中缓存；
- 只换 BOM 不重新生成底图和配准；
- 失败/取消后保留上一个完整版本；
- 刷新和切换工具不丢运行；
- 删除历史时只删除本运行拥有的资产。

### T8：前端 API、状态机和兼容迁移

**范围**

- 建立 `smtAnalysis` API client；
- 前端状态改为 `source -> identify -> register -> review -> deliver`；
- 旧 workspace 只迁移输入，不恢复旧灰块结果；
- 新旧后端不匹配时给明确升级提示。

**文件**

- 新建 `frontend/src/tools/smtAnalysis/api.ts`
- 新建 `frontend/src/tools/smtAnalysis/state.ts`
- 修改 `frontend/src/api/client.ts`
- 修改 `frontend/src/state/toolWorkspace.ts`
- 新建 `frontend/src/test/smt-analysis-state.test.ts`

**依赖**

- T1、T7

**验收**

- 每个阶段的允许动作明确；
- 输入变化只失效依赖它的阶段；
- 刷新后恢复当前运行；
- 旧状态不导致新规则跳过配准/审核。

### T9：资料选择和识别确认 UI

**范围**

- 改造三项输入；
- SMT 目录不再过滤 PDF/图片/表格；
- 展示扫描结果和页面/坐标候选；
- 支持修改选择；
- 内部处理记录仅显示“已自动关联处理记录”。

**文件**

- 新建 `frontend/src/tools/smtAnalysis/SourceStep.tsx`
- 新建 `frontend/src/tools/smtAnalysis/IdentificationStep.tsx`
- 修改 `frontend/src/tools/SmtLayoutPane.tsx`
- 新建对应 CSS module 和 Vitest

**依赖**

- T2、T3、T4、T8

**验收**

- 用户不再看到“决策清单/语义清单”；
- PDF 位号图会被上传；
- 多候选时不静默选择；
- 分析后输入区折叠；
- 窄屏无横向溢出。

### T10：配准确认和手动校准 UI

**范围**

- 页面候选、正反面和方向选择；
- 叠加透明度；
- 位号锚点选择；
- 撤销、清空、重算；
- 配准证据与阻断；
- 完成确认后进入工作台。

**文件**

- 新建 `frontend/src/tools/smtAnalysis/RegistrationStep.tsx`
- 新建 `frontend/src/tools/smtAnalysis/AnchorEditor.tsx`
- 新建 `frontend/src/test/smt-registration-step.test.tsx`

**依赖**

- T5、T8、T9

**验收**

- 用户不输入矩阵；
- 锚点不足/分布无效不能继续；
- 取消/重试不丢页面选择；
- 正反面分别确认；
- reduced-motion 下无依赖动画的逻辑。

### T11：板面渲染器与空间交互

**范围**

- Canvas 位号图底图；
- Canvas 热点层；
- 平移、缩放、定位、框选、重叠热点；
- 视口查询和空间索引；
- LOD 标签；
- 正反面切换；
- 坐标诊断模式。

**文件**

- 新建 `frontend/src/components/SmtBoardViewport.tsx`
- 新建 `frontend/src/components/smtBoardRenderer.ts`
- 新建 `frontend/src/components/spatialIndex.ts`
- 重命名/迁移 `PcbCanvas.tsx` 为诊断视图
- 新建渲染器和浏览器测试

**依赖**

- T1、T4、T5；可与 T9-T10 并行

**验收**

- 真实底图为默认；
- 坐标诊断视图明确标注不代表真实板面；
- 热点与位号列表双向联动；
- 1000-5000 器件基线由 T0 机器实测并满足批准预算；
- 缩放、切面和筛选不重排外围布局；
- Canvas 像素检查确认非空且底图、热点同时存在。

### T12：异常复核和批量决策 UI

**范围**

- 异常优先列表；
- 状态/角色/面别/审核筛选；
- 上一/下一异常；
- 证据详情抽屉；
- 单项和批量确认；
- 操作范围和风险提示；
- 未解决阻断汇总。

**文件**

- 新建 `frontend/src/tools/smtAnalysis/ReviewWorkbench.tsx`
- 新建 `frontend/src/tools/smtAnalysis/EvidenceDrawer.tsx`
- 新建 `frontend/src/tools/smtAnalysis/DecisionBar.tsx`
- 新建对应 Vitest/Playwright

**依赖**

- T6、T7、T8、T11

**验收**

- 正常器件默认不淹没异常；
- 任一结论可看到原因和来源；
- 批量决策明确显示作用范围；
- 用户决策刷新后仍在；
- 候选 NC 与确认 NC 计数绝不混合。

### T13：首件、三向一致性和输出迁移

**范围**

- 现有 FAI、sanity 和导出消费新 `Placement`；
- 生成标注图、明细、JSON 和报告；
- 输出重新打开并回读验证；
- 报告注明输入范围、配准状态和未解决项。

**文件**

- 修改 `app/backend/tools/smt_layout.py`
- 新建 `app/backend/smt_analysis/export.py`
- 修改 `tests/test_smt_layout_fai.py`
- 修改 `tests/test_smt_layout_sanity.py`
- 新建 `tests/test_smt_analysis_export.py`

**依赖**

- T6、T7

**验收**

- 旧首件表关键字段不丢失；
- 新输出不从位号前缀重新猜 NC；
- 标注图和明细使用同一决策快照；
- 未解决阻断不能被导出成“已通过”；
- 输出回读位号集合、状态和数量一致。

### T14：自动页面识别和半自动配准增强

**范围**

- PDF 矢量文字位置提取；
- 可选本地 OCR；
- 位号锚点候选；
- 页面与坐标面评分；
- 旋转/镜像候选；
- 供应商适配器扩展点。

**文件**

- 新建 `app/backend/smt_analysis/refdes_extraction.py`
- 新建 `app/backend/smt_analysis/auto_registration.py`
- 新建 `tests/test_smt_auto_registration.py`

**依赖**

- T2、T3、T4、T5

**验收**

- OCR 不可用时主流程仍可手动完成；
- 自动候选必须经过独立验证；
- 错页/错面样本优先拒绝，而不是追求自动覆盖率；
- 具体阈值由真实样本校准后写入版本化配置。

### T15：全链路、真实样本和发布门槛

**范围**

- 真实 IAC4 V05 正反面配准；
- 合成错页、错面、错版本、缺面、拼板和低清样本；
- 100、1000、5000 器件规模测试；
- 桌面和窄屏截图；
- 安装运行时离线测试；
- 文档更新。

**文件**

- 新建 `tests/test_smt_analysis_e2e.py`
- 新建 `frontend/e2e/smt-analysis.spec.ts`
- 修改 `docs/Insta360_HW_Platform_Guide.md`
- 修改发布验收脚本

**依赖**

- T0-T14

**验收**

- 位号图、坐标热点和列表联动正确；
- 正反面无静默误配；
- 坐标范围未知时没有确认 NC；
- 拼板/错版本得到阻断；
- 缺图时诊断视图仍可用；
- 缺一面不把另一面位号误判为 NC；
- 前后端单元、契约、API、E2E、生产构建全部通过；
- 真实输出回读通过；
- 用户人工验收后才允许发布 OTA。

## 10. 依赖与并行图

```text
T0 -> T1

T1 -> T2 -> T4
T1 -> T3
T1 -> T5
T1 -> T6
T1 -> T7

T2 + T3 + T4 + T8 -> T9
T5 + T8 + T9 -> T10
T4 + T5 -> T11
T6 + T7 + T8 + T11 -> T12
T6 + T7 -> T13
T2 + T3 + T4 + T5 -> T14

T0-T14 -> T15
```

建议并行批次：

- Wave 1：T1
- Wave 2：T2、T3、T5、T6、T7
- Wave 3：T4、T8、T14
- Wave 4：T9、T11、T13
- Wave 5：T10、T12
- Wave 6：T15

## 11. 跨任务契约

1. T1 的枚举和 JSON fixture 是所有任务唯一契约来源。
2. T2 只负责识别，不负责坐标解析、配准和 NC。
3. T3 只负责坐标语义和质量，不负责页面选择。
4. T5 是纯数学/验证模块，不读取文件、不访问数据库。
5. T6 是纯装机语义模块，不依赖前端颜色和文件名。
6. T7 只管理运行、缓存、决策和事务，不复制解析规则。
7. T11 只渲染 API 数据，不在浏览器重新猜单位、镜像或 NC。
8. T13 只消费已确认的分析快照，不重新从前缀和描述推导。
9. T14 失败必须回退到 T10 手动配准，不能阻断基础闭环。
10. 任何任务不得把具体项目名、具体位号或具体文件名写成生产特判。

## 12. 测试矩阵

### 资料

- 矢量 PDF、扫描 PDF、PNG、JPG；
- 正反面分文件、同 PDF 多页；
- 原理图和位号图共存；
- 拼板和单板图共存；
- DXF/ART/Gerber 与 PDF 共存；
- 低清、旋转、裁切、密码保护和损坏 PDF。

### 坐标

- 当前 `XY.txt`；
- CSV/TXT/XLS/XLSX；
- UTF-8、UTF-16、GBK；
- 多级表头、说明行、重复表头；
- 单位明确、单位未知；
- 面别明确、1/2 歧义；
- X/Y 交换候选；
- 重复位号、缺位号、全零和离群点；
- 单板和拼板坐标。

### BOM

- 普通主料；
- 替代料空位号；
- 显式 NC；
- 不含 NC 的处理后 BOM；
- 插件、手工焊和结构件；
- 位号范围；
- 数量不一致；
- 重复和冲突位号；
- 历史精确复用和跨版本失效。

### 配准

- 平移、缩放、旋转；
- 镜像；
- 仿射轻微变形；
- 锚点不足、共线和局部集中；
- 两个近似候选；
- 错页、错面、错版本；
- 多板页面；
- 人工锚点撤销和重算。

### 降级

- 仅坐标；
- 仅 BOM；
- 缺位号图；
- 缺正面/反面图；
- 缺正面/反面坐标；
- PDF 解析失败；
- OCR 不可用；
- 自动配准失败。

## 13. Definition of Done

- 普通用户只需选择目录、BOM 和可选网表。
- 默认看到真实位号图，不是灰块伪板面。
- 热点、列表、搜索、筛选和证据双向联动。
- 所有配准均有验证状态，未知不静默通过。
- 所有 NC 均说明位号全集来源和判定证据。
- 候选、确认、冲突和未解决状态严格分开。
- 刷新、切工具和重启后运行与决策可恢复。
- 无位号图或配准失败时仍能使用坐标诊断模式。
- 输出与分析快照一致并完成回读验证。
- 全部测试、构建、真实样本和用户验收通过后才发布。

## 14. 实施前需要用户确认的业务信息

这些信息不阻塞 T1-T5，但必须在 T6/T15 完成前确认：

1. 当前各供应商坐标文件通常是完整设计集合、仅 SMT 集合还是仅实际贴装集合。
2. 已处理 PLM/OA BOM 是否稳定代表最终装机位号，插件、手工焊和结构件是否仍在其中。
3. 第一版是否只支持单板，还是必须支持从拼板中选择单板。
4. 用户确认 NC 是否需要二次复核或审批身份。
5. 最终主要交付是 PDF、Excel、OA 附件还是供应商问题单。
6. 是否允许在本地运行 OCR，以及最低终端配置和缓存保留要求。
