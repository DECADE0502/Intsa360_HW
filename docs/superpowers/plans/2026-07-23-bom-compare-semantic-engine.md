# BOM 对比语义引擎与关联工具重构实施计划

> **给执行者**：本计划面向 `v0.5.5` 之后的 BOM 领域重构。不要在现有 `bom_compare.py` 上继续堆条件分支。必须先建立唯一的 BOM 中间模型，再让 BOM 对比、PLM、OA/ECR、风险检查、贴片封装检查、贴片布局对照和历史记录共同消费。每个 task 只修改列出的文件，先写红灯测试，再实现，再做定向验收。

## 0. 基线与目标

**仓库基线**

- 分支：`feature/v0.4.0-overhaul`
- 提交：`3cc17c17c31d297d711f961ed08211e9478a56c7`
- 版本：`0.5.5`
- 当前工作区：计划编写前为 clean
- 技术栈：Python / FastAPI / openpyxl / React / TypeScript / Ant Design / Vite

**目标**

1. 将 Excel 行、实际贴装位号、物料身份和替代关系分离建模。
2. 同时提供原始行、实际贴装、替代关系和元数据四层对比。
3. 正确处理两料、三料及一般 `N` 料替代组。
4. 区分 `替代(AB共存)` 与 `更换(A换成B)`。
5. PLM、OA BOM、OA/ECR 使用明确且不同的输出契约。
6. 所有相关工具共享同一份规范化 BOM 和决策结果。
7. 保留用户模板结构、工作表、列顺序、合并单元格和格式。
8. 不把替代料数量计入实际贴装数量。
9. 不跨父项合并相同位号。
10. 不使用料号前缀猜测原料、国产料或物料角色。

**非目标**

- 不接入公司 PLM 主数据接口。
- 不维护具体料号白名单。
- 不在本计划中改变安装、更新、卸载或 Cadence 生命周期链路。
- 不自动修改用户上传的原始文件。
- 不将真实公司 BOM、物料编码明细或完整位号表提交到公开仓库。
- 不在本计划中发布 OTA；完成全部门禁后另开发布任务。

## 1. 已确认的真实样例不变量

真实样例目录通过环境变量传入：

```text
HWAGENT_BOM_COMPARE_SAMPLES_ROOT
```

默认本机目录可由执行者设置，但生产代码、测试代码和文档不得硬编码个人绝对路径。

### 1.1 样例 01：单板 PLM + 替代组

- 143 条数据行。
- 单一父项。
- 26 个替代组。
- 25 个两料组。
- 1 个三料组。
- 完整替代关系共 27 对。
- 800 个实际物理位号。
- 替代组结构校验为 0 错误。
- 28 行无实际位号，其中 27 行为替代料，1 行为合法的无位号板级物料。
- 三料组主料优先级为 0，两个替代料依次为 1、2。

### 1.2 样例 02：小型 PLM

- 3 条数据行。
- 无替代组。
- 存在 PCB/FPC 行的纯数字位号 `72`。
- `72` 不能按 `60` 规则自动清空，也不能直接认定为真实贴装位号。
- 应产生 `numeric_reference_suspected` 源质量问题，等待用户确认。

### 1.3 样例 03 与 04：PLM/OA 格式映射

- PLM 有 122 条数据行。
- OA 有 1 条父项行和 134 条子项行。
- 两者规范化后均有 892 个实际位号。
- `父项 + 位号 -> 物料编码` 映射完全一致。
- OA 中 7 个物料编码被拆成多行。
- 部分同编码行存在型号、描述或规格冲突，不能仅按编码自动合并。
- OA “层级”列对子项从 1 连续增长到 134，不能当作真实树深度。

### 1.4 样例 05 与 06：多 PCBA 与标注版

- 原始工作表 215 行。
- 第 `145、160、164、183、187、208、212` 行为重复表头。
- 跳过重复表头后有 207 条数据行。
- 共 8 个父项。
- 共 34 个替代组：33 个两料组、1 个三料组。
- 51 个相同位号标签在不同父项间复用，必须以 `父项 + 位号` 隔离。
- 正式版与标注版所有单元格值、行数和顺序完全一致。
- 标注版只有填充色变化：365 个单元格、65 行。
- 存在多个纯数字位号。
- 同一父项中两个无标准位号物料共享纯数字 `68`；在确认数字 token 含义前，不得误报为真实贴装冲突。

### 1.5 样例 07：OA/ECR

- 24 个发生变更的替代组。
- 25 个 OA 变更项。
- 每个变更项两行，共 50 行关系明细。
- 其中一个三料组拆成 2 个变更项。
- 01 中另有 2 个未发生变化的替代组，不应写入 ECR。
- 硬件版本存在于 ECR 表单，而不在样例 01 的 PLM 数据表中。

### 1.6 样例安全规则

- 完整 `.xlsx` 不得复制到 `tests/fixtures`。
- CI 使用去标识化的合成 fixture。
- 本机真实 golden 测试默认 `skip`，仅设置环境变量时执行。
- 测试日志只打印统计、行号和错误类别，不打印完整物料编码、描述、型号或位号集合。
- 真实样例只用于验证通用规则，生产代码不得出现样例板名、具体料号或具体位号特判。

## 2. 唯一数据链

```text
Excel 工作簿
  -> WorkbookEnvelope
  -> SourceSheet / SourceCell
  -> CanonicalRow
  -> BoardBOM
  -> PhysicalPlacement + NonPlacementItem
  -> SubstituteGroup + MaterialVariant
  -> ValidationFinding
  -> BomChangeEvent
  -> CompareResult
  -> 差异报告 / PLM / OA BOM / OA-ECR / JSON
```

任何下游工具不得重新从 Excel 行、位号前缀、描述或文件名推导主料、替代料、NC 或贴装数量。

## 3. 领域模型

新建包：

```text
app/backend/bom_semantics/
  __init__.py
  contracts.py
  models.py
  field_mapping.py
  workbook_reader.py
  normalization.py
  references.py
  substitutes.py
  validation.py
  diff.py
  change_events.py
  report_export.py
  plm_export.py
  ecr_export.py
  serialization.py
```

### 3.1 WorkbookEnvelope

保存：

- 原始文件路径和 SHA-256。
- 工作表名称、顺序、可见性。
- 数据表、说明表、ECR 表单等 profile。
- 表头行、父级表头行和数据区域。
- 列顺序、合并单元格、冻结窗格、列宽和行高。
- 原始值、显示值、数据类型、数字格式和来源坐标。
- 重复表头、说明行、父项行和尾部模板说明区。

### 3.2 CanonicalRow

至少包含：

- `source_id`
- `sheet_name`
- `row_number`
- `item`
- `parent_code`
- `parent_description`
- `hardware_version`
- `material_code`
- `name`
- `model`
- `description`
- `unit`
- `quantity`
- `references`
- `is_nc`
- `remark`
- `grade`
- `grade_remark`
- `substitute_group_code`
- `substitute_strategy`
- `substitute_mode`
- `substitute_priority`
- `issue_method`
- `mrp`
- `jump_level`
- `extra_fields`
- `raw_cells`
- `quality_flags`

所有标识符保留字符串；数量使用 `Decimal`。

### 3.3 MaterialVariant

同一父项、同一物料编码下，按以下字段建立候选变体：

- 名称。
- 型号。
- 物料描述。
- 单位。
- 优选等级。
- 替代方式。
- 制造商（若存在）。
- PCB Footprint / PCB 封装（若存在）。
- 其它配置为“功能字段”的模板字段。

只有大小写、空白、标点或经确认的安全截断差异可以自动归并。数字规格、封装、制造商、等级或完整候选不同必须保留为不同变体。

### 3.4 PhysicalPlacement

主键：

```text
(parent_code, normalized_reference)
```

保存：

- 当前主料编码。
- 来源行。
- 所属替代组。
- NC 状态。
- 主料变体。
- 数据质量状态。

替代料不生成 PhysicalPlacement。

### 3.5 NonPlacementItem

用于 PCB、FPC、背胶、辅料等合法无位号物料。它们参与物料层对比，但不进入实际贴装位号计数。

纯数字位号在用户确认前不得自动转为 NonPlacementItem，只产生质量问题。

### 3.6 SubstituteGroup

包含：

- `group_code`
- `main_item`
- `alternative_items`
- `physical_references`
- `quantity`
- `priorities`
- `validation_findings`
- `group_fingerprint`

`group_fingerprint` 不能只使用组编码，因为主料互换后组编码会变化。

### 3.7 BomChangeEvent

统一事件类型：

- `unchanged`
- `metadata_only`
- `substitute_priority_only`
- `main_changed_refs_migrated`
- `alternative_added`
- `alternative_removed`
- `replacement`
- `quantity_changed`
- `reference_added`
- `reference_removed`
- `reference_migrated`
- `material_added`
- `material_removed`
- `substitute_structure_invalid`
- `placement_blocker`

每个事件包含：

- 父项。
- 旧、新对象快照。
- 影响位号。
- 影响替代组。
- 功能影响等级。
- OA/ECR 建议类型。
- 阻断原因。
- 可追溯源行。

## 4. 字段映射与工作簿 profile

支持 profile：

- `capture_raw`
- `plm_single_board`
- `plm_multi_board`
- `oa_bom`
- `oa_ecr`
- `unknown`

字段映射不依赖固定列号，按以下证据排序：

1. 完整表头别名。
2. 父级合并表头上下文。
3. 相邻字段位置。
4. 数据内容形态。
5. 用户显式映射。

重复的“描述”必须根据父项/子项分组表头或相邻编码列消歧，不能永远选择第一列。

默认别名至少覆盖：

- 项次。
- 层级。
- 父项编码。
- 父项描述。
- 子项编码。
- 名称。
- 型号。
- 物料描述。
- 单位。
- 数量。
- 位号。
- 备注。
- 优选等级。
- 优选等级备注。
- 替代组编码。
- 替代策略。
- 替代方式。
- 替代优先级。
- 发料方式。
- 是否参与 MRP。
- 是否跳层。
- 硬件版本 / 适用版本。

用户映射保存到本地配置，按模板表头指纹复用；仓库只保存 schema 和默认别名。

## 5. 数据归一化规则

### 5.1 编码

- 父项编码、物料编码始终是文本。
- 数字单元格结合 `number_format` 还原显示文本。
- 科学计数法、超过 Excel 可靠精度或前导零已丢失时产生 blocker。
- 禁止将编码转换为整数或浮点数后再比较。

### 5.2 位号

- 支持英文逗号、中文逗号、英文/中文分号、空格、制表符和换行。
- 去首尾空格、统一大小写、去重、自然排序。
- 精确 token `60` 归一化为空。
- `R60`、`C60` 等正常位号不受影响。
- 其它纯数字 token 产生 `numeric_reference_suspected`。
- 用户可对每个来源位置选择：作为空位号、保留、替换为指定值。
- 决议使用 `source_fingerprint + sheet + row + column` 绑定，不能按数字全局套用。

### 5.3 数量

- 使用 `Decimal` 比较。
- 替代组主料数量必须等于真实位号数。
- 替代料数量必须与主料数量相同。
- 替代料数量不计入实际贴装总数。
- 非贴装物料允许有数量但无位号。

### 5.4 重复表头和说明行

- 任意数据区中再次出现规范表头时跳过并记录 `repeated_header_skipped`。
- 模板说明行、颜色说明行和枚举说明区不能解析为物料。
- 跳过行为必须保留源行号和审计记录。

### 5.5 OA 父项行

- 明确层级 0 且符合父项形态的行建立父项上下文。
- 子项层级列可能是序号，不能用于树深度推理。
- 父项行不得进入物料集合。

### 5.6 NC

- NC/未贴与贴装位号分开保存。
- NC 替代关系不能进入实际贴装计数。
- 若同一父项、同一位号同时出现在贴装和 NC，产生 blocker。

## 6. 替代组构建与校验

### 6.1 构建

- 仅在同一父项内按替代组编码聚合。
- 优先级 0 为主料。
- 优先级大于 0 为替代料。
- 替代料位号为空或 `60`。
- 普通无替代物料不创建伪替代组。

### 6.2 必须阻断

- 没有优先级 0。
- 存在多个优先级 0。
- 优先级不连续。
- 替代组编码不等于主料编码。
- 组内数量不一致。
- 主料数量与位号数不一致。
- 替代料占用真实位号。
- 同一位号映射到两个主料。
- 同一物料同时处于多个互斥替代组。
- 物料编码或父项编码失真。

### 6.3 需要审查但不自动阻断

- 纯数字位号。
- 同编码多属性变体。
- 无位号普通物料。
- 模板字段无法唯一映射。
- 描述与编码疑似不一致。
- 规则无法判断的主料迁移。

### 6.4 重复物料行

- 同父项、同编码、同替代组、属性等价：合并位号并校验数量。
- 同父项、同编码、不同替代组：默认 blocker。
- 同父项、同编码、属性冲突：保留 MaterialVariant，禁止自动合并。
- 不同父项相同编码：独立处理。

## 7. 新旧 BOM 匹配和差异判定

### 7.1 父项匹配

顺序：

1. 父项编码完全一致。
2. 用户显式指定旧父项到新父项的映射。
3. 无唯一映射时按新增/删除父项处理，不按描述猜测。

### 7.2 实际贴装匹配

按 `(父项, 位号)` 比较：

- 主料相同：检查属性和替代关系。
- 主料不同：检查是否属于同一替代成员集合。
- 旧有新无：位号删除。
- 旧无新有：位号新增。
- 同位号多主料：blocker。

### 7.3 替代组稳定匹配

顺序：

1. 父项相同且物理位号集合完全一致。
2. 位号集合高度重叠且成员集合一致。
3. 成员集合一致且主料发生互换。
4. 用户显式组映射。
5. 仍有多个候选时停止自动匹配。

组编码只能作为证据，不能作为唯一键。

### 7.4 差异优先级

```text
结构 blocker
  > 替代组变化
  > 实际贴装变化
  > 物料增删/数量变化
  > 元数据变化
```

同一业务变化只能产生一个主事件，不能同时重复生成“删除 + 新增 + 换料”。

### 7.5 关键语义

- 主替优先级互换且成员仍共存：`main_changed_refs_migrated`，不是 replacement。
- 只新增替代料：`alternative_added`，实际贴装无变化。
- 只删除替代料：`alternative_removed`，实际贴装无变化。
- A 完全退出，B 承接全部位号：`replacement`。
- 编码、数量、位号和替代关系不变，仅描述变化：`metadata_only`。
- 描述相同但编码不同：功能变化，不能按描述判为相同。

## 8. API 契约

`bom_compare` 使用三阶段无状态协议：

### 8.1 inspect

请求：

```json
{
  "action": "inspect",
  "bom1": "...",
  "bom2": "...",
  "field_mapping_overrides": {}
}
```

响应：

```json
{
  "schema_version": 2,
  "action": "inspect",
  "sources": [],
  "quality_findings": [],
  "mapping_candidates": [],
  "source_fingerprints": [],
  "can_compare": false
}
```

### 8.2 compare

请求增加：

- 字段映射决议。
- 纯数字位号决议。
- 父项映射。
- 可选策略配置。

响应：

- `analysis_fingerprint`
- `summary`
- `raw_row_diff`
- `placement_diff`
- `substitute_diff`
- `metadata_diff`
- `blockers`
- `warnings`
- `normalized_sources`
- `can_export`

### 8.3 export

请求：

- `analysis_fingerprint`
- 输入文件。
- 所有决议。
- PLM 模板。
- OA/ECR 模板。
- ECR 表单元数据。
- 输出选择。

后端必须重新计算并验证 fingerprint，禁止使用前端上传的差异结论直接写文件。

## 9. 输出契约

### 9.1 对比报告

工作表：

1. 对比摘要。
2. 实际贴装差异。
3. 替代关系差异。
4. 物料与数量差异。
5. 元数据差异。
6. 原始行差异。
7. 风险与阻断。

### 9.2 机器 JSON

包含：

- schema version。
- source fingerprint。
- 字段映射。
- 父项。
- 规范物料。
- 实际贴装。
- 替代组。
- 校验结果。
- 变更事件。
- 用户决议。

### 9.3 PLM

- 使用用户模板或内置模板。
- 保留所有工作表和顺序。
- 保留说明表、合并单元格、列宽、行高和格式。
- 按识别出的数据区域清理旧数据，不删除尾部说明区。
- 按模板列顺序写入。
- 编码列强制文本格式。
- 正式版与标注版数据哈希必须一致。

### 9.4 OA BOM

OA BOM 是成品 BOM 格式转换，不是 ECR。

- 保留父项层级行。
- 允许同编码拆行输入，但规范化模型保持一致。
- 重新导入后必须得到与 PLM 一致的物理位号映射。

### 9.5 OA/ECR

只根据 `BomChangeEvent` 生成：

- `新增`
- `删除`
- `更换(A换成B)`
- `替代(AB共存)`
- `数量(位号)修改`

`N` 料共存组生成 `N-1` 个变更项。每个变更项两行：

- 变更前：主料，位号完整，优先级 0。
- 变更后：一个替代料，位号为空，保留真实替代优先级。

未变化的替代组不进入 ECR。

## 10. UI 交互

全界面中文。

顶部流程：

```text
来源体检 -> 父项与字段确认 -> 差异审查 -> 输出设置 -> 交付
```

### 10.1 来源体检

- 左右并列显示旧版和新版。
- 展示识别 profile、父项数、数据行、重复表头、数字位号、字段映射和阻断数。
- 数字位号逐项选择“作为空值 / 保留 / 替换”。
- 字段映射不唯一时提供下拉选择。
- 来源未通过体检时不能进入差异页。

### 10.2 差异审查

主页面使用标签页：

- 实际贴装。
- 替代关系。
- 物料变化。
- 元数据。
- 原始行。
- 风险阻断。

布局：

- 左侧：可筛选差异列表。
- 中间：旧版/新版并排字段。
- 右侧：固定证据和替代组成员面板。
- 窄屏：右侧转抽屉。
- 正常项默认折叠。
- blocker 始终置顶。
- 不使用长页面堆叠所有结果。

### 10.3 替代组展示

- 主料单独标识。
- 替代料按优先级排列。
- 实际位号只显示在主料区域。
- 主料互换使用明确的“旧主料 -> 新主料”语义。
- 新增/删除替代料单独标识。
- 不使用料号前缀展示“原料/国产料”角色，除非来自用户策略或主数据。

### 10.4 输出

- 分开提供“下载差异报告”“生成 PLM”“生成 OA BOM”“生成 OA/ECR”。
- 有 blocker 时禁用正式输出，并说明阻断原因。
- OA/ECR 生成前要求确认项目、阶段、部门、硬件版本等表单字段。
- 输出完成后保留结果预览和重新开始按钮。

### 10.5 动效与可访问性

- 页面切换和行状态变化约 180ms。
- 支持 `prefers-reduced-motion`。
- 表格、筛选、详情可键盘操作。
- 动画不承担唯一状态表达。

## 11. 关联工具行为

### 11.1 BOM 处理

- 成功处理时额外生成规范化 `BoardBOM JSON`。
- 原始 Capture BOM 没有替代关系时生成普通物料模型。
- 输入为已处理 PLM/OA 时保留替代组，禁止丢失替代料数量。

### 11.2 BOM 风险检查

增加：

- 替代组唯一主料。
- 优先级连续。
- 组内数量一致。
- 主料数量与位号一致。
- 替代料位号为空。
- 同位号多主料。
- 同编码多属性。
- 纯数字位号。

风险检查消费规范模型，不重新解析一套规则。

### 11.3 贴片封装检查

- 主料按实际位号检查。
- 替代料不增加贴装数量。
- 替代料单独检查封装兼容性。
- 替代料与主料封装不同必须提示，不自动认定可混用。

### 11.4 贴片布局对照

- 只使用 PhysicalPlacement。
- 替代料仅作为候选信息展示。
- NC 和非贴装物料不进入应贴集合。
- 不再从处理后 BOM 的空位号推断 NC。

### 11.5 历史记录

- 保存规范化 JSON 和 source fingerprint。
- 历史选择器显示父项、版本、实际位号和替代组数。
- 可直接选择历史 BOM 参与对比。
- schema 变化时旧记录只做来源文件复用，重新规范化。

## 12. 实施任务

### 12.0 任务总览与文件所有权

| Wave | Task | 主要产物 | 独占文件范围 | 依赖 |
|---|---|---|---|---|
| 0 | T0 | 隐私安全 fixture、private golden harness | `.gitignore`、`tests/fixtures/bom_semantics` | 无 |
| 1 | T1 | 领域模型和 API 契约 | `bom_semantics/models.py`、`contracts.py` | T0 |
| 2 | T2 | 工作簿 profile 和字段映射 | `field_mapping.py`、`workbook_reader.py` | T1 |
| 3 | T3 | 规范化、位号和质量报告 | `normalization.py`、`references.py` | T2 |
| 4 | T4 | 替代组、物理贴装和结构校验 | `substitutes.py`、`validation.py` | T3 |
| 5 | T5 | 四层 diff 和变更事件 | `diff.py`、`change_events.py` | T4 |
| 6A | T6 | JSON 和差异报告 | `serialization.py`、`report_export.py` | T5 |
| 6B | T7 | PLM 模板导出 | `plm_export.py` | T2、T4 |
| 6C | T8 | OA BOM 和 OA/ECR 导出 | `ecr_export.py` | T2、T5 |
| 7A | T9 | 后端 API、资产和历史 | `bom_compare.py`、assets repository | T6、T7、T8 |
| 7B | T10 | 前端工作台 | `BomComparePane.tsx`、`tools/bomCompare` | T1 mock；T9 联调 |
| 7C | T11 | BOM 处理和风险检查接入 | `bom_process*`、`bom_risk.py` | T4、T6 |
| 7D | T12 | SMT 工具接入 | `smt_package.py`、`smt_layout.py` | T4、T6 |
| 8 | T13 | 真实 golden、性能、E2E、用户文档 | golden/E2E tests、用户指南 | T6-T12 |
| 9 | T14 | 只验收、不打补丁 | 无生产文件 | T13 |

同一 Wave 只有在“独占文件范围”不交叉时才可并行。任何执行者发现需要修改其他 task 的独占文件，必须停止并把依赖上报给主任务，不得跨边界顺手修改。

### T0 基线、隐私和测试框架

**目标**

- 固化 `v0.5.5` 基线。
- 建立合成 fixture 和本机 opt-in golden 机制。
- 防止真实 BOM 被提交。

**Files**

- Modify: `.gitignore`
- Create: `tests/fixtures/bom_semantics/README.md`
- Create: `tests/fixtures/bom_semantics/build_fixtures.py`
- Create: `tests/test_bom_semantics_private_golden.py`
- Create: `tests/test_bom_semantics_fixture_builder.py`

**实现**

- 合成普通 BOM、两料组、三料组、多父项、重复表头、数字位号和 OA/ECR。
- 私有测试仅环境变量存在时运行。
- `.gitignore` 排除 `tests/private/`、真实样例缓存和生成报告。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_fixture_builder.py -q
python -m pytest tests/test_bom_semantics_private_golden.py -q
git status --short
```

未设置环境变量时 private golden 应 `skip`，不得失败。

**DoD**

- 公开 fixture 不含真实板名、料号和位号。
- 真实样例无法被普通 `git add .` 误加入。

**依赖**：无。

**commit**：`test(bom): T0 add privacy-safe semantic fixtures and private golden harness`

### T1 领域模型与契约

**目标**

- 建立稳定的 Python 领域类型和 API schema。

**Files**

- Create: `app/backend/bom_semantics/__init__.py`
- Create: `app/backend/bom_semantics/models.py`
- Create: `app/backend/bom_semantics/contracts.py`
- Create: `tests/test_bom_semantics_contract.py`

**实现**

- 定义本计划第 3 节全部 dataclass / enum。
- 建立 `schema_version` 和稳定序列化字段。
- 模型中不引用 openpyxl、FastAPI、前端或具体工具。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_contract.py -q
```

**DoD**

- 枚举和 schema 有穷尽测试。
- 领域包无 Excel/UI/API 依赖。

**依赖**：T0。

**commit**：`feat(bom): T1 define semantic BOM domain and API contracts`

### T2 工作簿 profile 与字段映射

**目标**

- 识别 PLM 单板、PLM 多板、OA BOM、OA/ECR 和未知模板。

**Files**

- Create: `app/backend/bom_semantics/field_mapping.py`
- Create: `app/backend/bom_semantics/workbook_reader.py`
- Create: `tests/test_bom_semantics_workbook_reader.py`
- Create: `tests/test_bom_semantics_field_mapping.py`

**实现**

- 扫描所有工作表。
- 识别父级合并表头、数据表头、父项行、重复表头和尾部说明区。
- 输出 WorkbookEnvelope，不做替代关系判断。
- 字段映射冲突返回候选，不静默选错。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_workbook_reader.py tests/test_bom_semantics_field_mapping.py -q
```

**DoD**

- 合成 4 类 profile 全部识别。
- 列重排后字段映射不变。
- 重复“描述”正确区分父项和子项。

**依赖**：T1。

**并行性**：可与 T10 的静态 UI 骨架并行。

**commit**：`feat(bom): T2 detect workbook profiles and map BOM fields`

### T3 规范化、位号和源质量报告

**目标**

- 从 WorkbookEnvelope 生成 CanonicalRow 和 SourceQualityReport。

**Files**

- Create: `app/backend/bom_semantics/references.py`
- Create: `app/backend/bom_semantics/normalization.py`
- Create: `tests/test_bom_semantics_normalization.py`
- Create: `tests/test_bom_semantics_references.py`

**实现**

- 编码文本化。
- Decimal 数量。
- 位号分割、去重和自然排序。
- 精确 `60` 空值。
- 其它纯数字 token 进入审查。
- 跳过重复表头和说明行。
- OA 父项行建立上下文。
- 所有问题保留源坐标。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_normalization.py tests/test_bom_semantics_references.py -q
```

**DoD**

- `60`、`R60`、`72` 三种情况行为不同且有测试。
- 多父项相同位号不会合并。
- 无静默跳行。

**依赖**：T2。

**commit**：`feat(bom): T3 normalize identifiers references and source quality`

### T4 替代组构建与结构校验

**目标**

- 正确构建 SubstituteGroup、PhysicalPlacement、NonPlacementItem 和 MaterialVariant。

**Files**

- Create: `app/backend/bom_semantics/substitutes.py`
- Create: `app/backend/bom_semantics/validation.py`
- Create: `tests/test_bom_semantics_substitutes.py`
- Create: `tests/test_bom_semantics_validation.py`

**实现**

- 两料、三料、N 料组。
- 唯一主料。
- 连续优先级。
- 组编码、数量、位号和重复物料校验。
- 同编码多属性保留变体。
- 不把非贴装物料当替代料。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_substitutes.py tests/test_bom_semantics_validation.py -q
```

**DoD**

- 14 个验收用例中的替代组和阻断类全部有单元测试。
- 替代料数量不进入 PhysicalPlacement 总数。

**依赖**：T3。

**commit**：`feat(bom): T4 build and validate substitute groups`

### T5 差异引擎与变更事件

**目标**

- 输出四层差异和唯一 BomChangeEvent。

**Files**

- Create: `app/backend/bom_semantics/diff.py`
- Create: `app/backend/bom_semantics/change_events.py`
- Create: `tests/test_bom_semantics_diff.py`
- Create: `tests/test_bom_semantics_change_events.py`

**实现**

- 父项匹配。
- 位号级实际贴装对比。
- 替代组稳定匹配。
- 主替互换、替代新增/删除、replacement、数量/位号变化。
- 元数据变化降级。
- blocker 优先。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_diff.py tests/test_bom_semantics_change_events.py -q
```

**DoD**

- 主替互换只生成一个业务事件。
- 新增替代料不改变实际贴装总数。
- A 完全退出才生成 replacement。
- 描述相同编码不同仍是功能变化。

**依赖**：T4。

**commit**：`feat(bom): T5 compare placement and substitute semantics`

### T6 JSON 与差异报告导出

**目标**

- 生成机器 JSON 和多工作表差异报告。

**Files**

- Create: `app/backend/bom_semantics/serialization.py`
- Create: `app/backend/bom_semantics/report_export.py`
- Create: `tests/test_bom_semantics_serialization.py`
- Create: `tests/test_bom_semantics_report_export.py`

**实现**

- 稳定 JSON schema。
- 七张差异工作表。
- 编码文本格式。
- 输出后回读校验。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_serialization.py tests/test_bom_semantics_report_export.py -q
```

**DoD**

- 导出后重新导入 JSON 不丢字段。
- 报告统计与 CompareResult 一致。

**依赖**：T5。

**并行性**：可与 T7、T8 并行。

**commit**：`feat(bom): T6 export semantic JSON and layered compare report`

### T7 PLM 模板保真导出

**目标**

- 不依赖固定列号写入 PLM 模板。

**Files**

- Create: `app/backend/bom_semantics/plm_export.py`
- Create: `tests/test_bom_semantics_plm_export.py`

**实现**

- 保留工作表、顺序、说明区、合并单元格和格式。
- 根据字段映射写入。
- 数据区扩缩时复制数据行样式。
- 正式版与标注版使用同一数据矩阵。
- 所有编码写为文本。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_plm_export.py -q
```

**DoD**

- 列重排模板 round-trip 通过。
- 辅助工作表和尾部说明未丢失。
- 正式/标注版值哈希完全一致。

**依赖**：T4、T2。

**并行性**：可与 T6、T8 并行。

**commit**：`feat(bom): T7 preserve PLM templates during semantic export`

### T8 OA BOM 与 OA/ECR 导出

**目标**

- 明确分离 OA BOM 格式转换和 OA/ECR 变更输出。

**Files**

- Create: `app/backend/bom_semantics/ecr_export.py`
- Create: `tests/test_bom_semantics_oa_export.py`
- Create: `tests/test_bom_semantics_ecr_export.py`

**实现**

- OA BOM 父项行和子项行输出。
- ECR 根据 BomChangeEvent 选择变更类型。
- `N-1` 成对生成。
- 未变化组不进入 ECR。
- 保留表单和合并单元格。

**验收**

```powershell
python -m pytest tests/test_bom_semantics_oa_export.py tests/test_bom_semantics_ecr_export.py -q
```

**DoD**

- 三料组生成 2 个 OA 项、4 行。
- AB 共存和 A 换 B 不混淆。
- 输出回读后事件数量和关系一致。

**依赖**：T5、T2。

**并行性**：可与 T6、T7 并行。

**commit**：`feat(bom): T8 generate OA BOM and semantic ECR changes`

### T9 BOM 对比后端适配与历史资产

**目标**

- 将现有工具切换到新语义引擎，同时保持旧调用兼容。

**Files**

- Modify: `app/backend/tools/bom_compare.py`
- Modify: `app/backend/tools/analysis_tools.py`
- Modify: `app/backend/assets.py`
- Modify: `app/backend/repositories/assets_repository.py`
- Modify: `app/backend/api/routers/tools.py`（仅契约需要时）
- Create: `tests/test_bom_compare_api_v2.py`
- Modify: `tests/test_bom_compare_workbench.py`
- Modify: `tests/test_asset_store.py`

**实现**

- `inspect / compare / export` 三阶段。
- 保存规范化 JSON 和分析 fingerprint。
- 历史资产暴露父项、版本、实际位号和替代组数。
- 旧 `{bom1,bom2}` 请求映射为 compare 默认流程，但返回 schema v2。

**验收**

```powershell
python -m pytest tests/test_bom_compare_api_v2.py tests/test_bom_compare_workbench.py tests/test_asset_store.py -q
```

**DoD**

- 原 API 不 500。
- 新 API 全部字段有契约测试。
- 历史 BOM 无需刷新即可在选择器出现。

**依赖**：T6、T7、T8。

**commit**：`refactor(bom): T9 route BOM compare through semantic engine`

### T10 前端 BOM 对比工作台

**目标**

- 重写来源体检、四层差异和输出工作流。

**Files**

- Rewrite: `frontend/src/tools/BomComparePane.tsx`
- Create: `frontend/src/tools/bomCompare/types.ts`
- Create: `frontend/src/tools/bomCompare/SourceInspection.tsx`
- Create: `frontend/src/tools/bomCompare/PlacementDiff.tsx`
- Create: `frontend/src/tools/bomCompare/SubstituteDiff.tsx`
- Create: `frontend/src/tools/bomCompare/MetadataDiff.tsx`
- Create: `frontend/src/tools/bomCompare/ExportPanel.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/tools/__tests__/BomComparePane.test.tsx`

**实现**

- 中文五步流程。
- 来源质量决议。
- 父项隔离筛选。
- 左列表、中间差异、右证据。
- blocker gate。
- OA/ECR 表单。
- 工作区持久化。
- 响应式和 reduced motion。

**验收**

```powershell
Set-Location frontend
npm test -- --run BomComparePane
npm run typecheck
npm run build
```

再使用 Playwright 验证：

- 1440x900。
- 1920x1080。
- 390x844。
- 无横向页面溢出。
- 表格内部允许受控横向滚动。
- 右侧无大面积空白。

**DoD**

- 所有操作可键盘完成。
- blocker 不能被前端绕过。
- 切工具再返回状态仍在。

**依赖**：T1 契约后可先使用 mock；最终联调依赖 T9。

**文件锁**：本 task 独占 `BomComparePane.tsx` 和相关 CSS 区域。

**commit**：`feat(frontend): T10 build semantic BOM comparison workbench`

### T11 BOM 处理与风险检查接入

**目标**

- BOM 处理输出规范模型，风险检查复用结构校验。

**Files**

- Modify: `app/backend/tools/bom_process.py`
- Modify: `app/backend/tools/bom_process_adapter.py`
- Modify: `app/backend/tools/bom_risk.py`
- Modify: `app/backend/tools/bom_rules.py`
- Modify: `tests/test_bom_e2e_flow.py`
- Modify: `tests/test_bom_risk_checks.py`
- Create: `tests/test_bom_process_semantic_manifest.py`

**实现**

- 处理结果增加 BoardBOM JSON。
- 现有决策清单继续保留。
- 风险检查调用 semantic validation。
- 替代料不因空位号报“主料缺位号”。
- 同编码多属性仍进入冲突审查。

**验收**

```powershell
python -m pytest tests/test_bom_e2e_flow.py tests/test_bom_risk_checks.py tests/test_bom_process_semantic_manifest.py -q
```

**DoD**

- 现有装机判定测试全部保持通过。
- 新输出不改变既有 PLM/OA 数据，除非输入本身含替代组且旧逻辑会丢失数据。

**依赖**：T4、T6。

**并行性**：可与 T12 并行。

**文件锁**：独占 BOM process/risk 文件。

**commit**：`refactor(bom): T11 reuse semantic model in processing and risk checks`

### T12 SMT 关联工具接入

**目标**

- 封装检查和布局对照正确理解主料与替代料。

**Files**

- Modify: `app/backend/tools/smt_package.py`
- Modify: `app/backend/tools/smt_layout.py`
- Modify: `tests/test_smt_package_export.py`
- Modify: `tests/test_smt_layout.py`
- Modify: `tests/test_smt_layout_e2e.py`

**实现**

- PhysicalPlacement 是唯一应贴位号来源。
- 替代料不计入贴装数量。
- 替代料封装兼容性单独输出。
- 使用 semantic JSON 时禁止回退到空位号猜测。

**验收**

```powershell
python -m pytest tests/test_smt_package_export.py tests/test_smt_layout.py tests/test_smt_layout_e2e.py -q
```

**DoD**

- 三料组仍只产生主料的实际贴装位号。
- 替代料封装差异可见。
- 现有 SMT 画布和 FAI 测试保持通过。

**依赖**：T4、T6。

**并行性**：可与 T11 并行。

**commit**：`refactor(smt): T12 consume semantic placement and alternatives`

### T13 真实 golden、性能和全链路

**目标**

- 用合成 fixture 和本机真实样例完成最终验收。

**Files**

- Modify: `tests/test_bom_semantics_private_golden.py`
- Create: `tests/test_bom_compare_e2e_v2.py`
- Create: `tests/test_bom_semantics_performance.py`
- Modify: `docs/Insta360_HW_Platform_Guide.md`

**验收矩阵**

- 普通无替代 BOM。
- 两料组。
- 三料组。
- 主替互换。
- 只增加替代料。
- A 完全换 B。
- 替代料位号 `60`。
- 数字位号审查。
- 主料位号缺失/重复。
- 优先级断层/双 0。
- 编码不变描述变化。
- 描述相同编码变化。
- 多父项相同位号。
- 列重排模板。
- 重复表头。
- OA 父项行。
- 同编码多属性。
- 导出再导入 round-trip。
- 正式/标注版值一致。

**真实样例断言**

- 01：143 行、26 组、800 实际位号、27 完整关系对、0 结构错误。
- 02：纯数字位号进入源质量审查。
- 03/04：892 位号映射一致；OA 同码多行保留变体审查。
- 05：7 个重复表头被跳过；207 行；8 父项；34 组；跨父项位号不冲突。
- 05/06：数据差异 0；仅样式变化。
- 07：24 变更组；25 OA 项；50 行；未变化组不输出。

**性能门槛**

- 两份各 1500 行 BOM 的 inspect + compare 在基准开发机上小于 3 秒。
- 峰值附加内存小于 300 MB。
- 不使用 O(n²) 全行笛卡尔比较。

**命令**

```powershell
python -m pytest tests/test_bom_semantics_*.py tests/test_bom_compare_e2e_v2.py -q
$env:HWAGENT_BOM_COMPARE_SAMPLES_ROOT = "<private-samples>"
python -m pytest tests/test_bom_semantics_private_golden.py -q
```

**DoD**

- 全部真实聚合断言通过。
- 文档只说明用户流程，不泄露具体料号。

**依赖**：T6-T12。

**commit**：`test(bom): T13 certify semantic comparison with golden and e2e gates`

### T14 发布前总验收

**目标**

- 证明功能、代码、UI 和输出均可发布，但不执行版本发布。

**Files**

- 不修改生产代码。
- 如发现问题，返回对应 task 修复，不在 T14 打补丁。

**门禁**

```powershell
python -m pytest tests -q
Set-Location frontend
npm test -- --run
npm run typecheck
npm run build
Set-Location ..
git diff --check
git status --short
```

人工验收：

- 桌面和窄屏截图。
- 来源体检。
- 主替互换。
- 三料 ECR。
- blocker 禁止导出。
- PLM 模板保真。
- OA/ECR 表单保真。
- 历史 BOM 即时可选。
- 切换工具后状态恢复。

**DoD**

- 所有测试和构建通过。
- 工作区无意外生成文件。
- 不修改 VERSION / REVISION / UPDATE_NOTICE。
- 不构建安装包。
- 不发布 OTA。

**依赖**：T13。

## 13. 依赖图与并行建议

```text
T0
 -> T1
    -> T2
       -> T3
          -> T4
             -> T5
                -> T6 ----\
                -> T8 -----+-> T9 -> T10
             -> T7 --------/
             -> T11 -------\
             -> T12 --------+-> T13 -> T14
```

可并行：

- T6 / T7 / T8。
- T11 / T12。
- T10 在 T1 后可按 mock 契约开发，但最终联调必须等待 T9。

不可并行：

- T2 与 T3。
- T4 与 T5。
- T9 与任何同时修改 `bom_compare.py` 的任务。
- T10 与任何同时修改 `BomComparePane.tsx` 或同一 CSS 区域的任务。

## 14. 全局执行约束

1. 每 task 单独 commit。
2. 先红后绿；新增行为必须有回归测试。
3. 不修改 task 文件清单之外的代码。
4. 不顺手重构生命周期、安装器、插件或 Cadence。
5. 不修改真实样例。
6. 不把真实样例复制进仓库。
7. 不在规则中出现具体板名、料号、位号特判。
8. 不通过描述覆盖编码结论。
9. 不按料号前缀推断原料或国产料。
10. 不让替代料数量进入实际贴装总数。
11. 不跨父项匹配位号。
12. 不把 UI 传来的事件结果当可信输出依据，export 必须后端重算。
13. 不直接编辑 `app/frontend` 构建产物；只修改 `frontend/src`，最后统一构建。
14. 不修改 `VERSION`、`REVISION`、`UPDATE_NOTICE.json`。
15. 不运行本地安装或本地 OTA。
16. 本机远端发布禁止 `git push`，只能显式 `git send-pack`；本计划阶段不发布。

## 15. Definition of Done

只有同时满足以下条件，BOM 对比重构才算完成：

- 四层差异均来自同一 BoardBOM 模型。
- 两料、三料、N 料替代组正确。
- 主替互换、AB 共存和 A 换 B 语义不混淆。
- 替代料不计入实际贴装数量。
- 多父项严格隔离。
- 数字位号不会被静默误判。
- 同编码多属性不会被错误合并。
- PLM、OA BOM、OA/ECR 三种输出边界清晰。
- PLM/OA 模板保真和 round-trip 通过。
- 正式版与标注版数据完全一致。
- 风险、SMT 封装和布局工具消费同一语义模型。
- 历史记录保存并可复用规范化 BOM。
- 所有 Python、前端、TypeScript、生产构建、桌面和窄屏验收通过。
- 未发布版本、安装包或 OTA。
