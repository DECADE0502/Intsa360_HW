# BOM 装机审查 — 完整重写方案

状态：待执行（交给 codex）
日期：2026-08-04
基线：0.5.15（`230bf38`）
适用分支：feature/v0.4.0-overhaul

---

## 0. 为什么要重写（已定位到具体提交）

用户报告：处理 BOM 时最后剩一项 SH 屏蔽类，不管移到哪个区域都点不了"下一步"。

**这是 0.5.4 引进的倒退，不是一直如此。**

`git log -S` 定位到单一提交：`7708647 feat(bom): implement evidence-first placement decisions`（2026-07-22，83 文件 / +5959 −1213），首个发布版本 0.5.4。

### 0.5.3 的完成判定（8 行，能用）

```js
if (!resolution.action) return false;
if (resolution.action === "exclude") return true;   // 选"不装"即完成
// 只有选"纳入"才要求编码 + 名称/型号/描述之一
```

一个组只回答一件事：**装 / 不装**。

### 0.5.4 起变成四个必答字段

| 字段 | 谁必须填 |
|---|---|
| `destination` 区域 | 所有组 |
| `exclusion_kind` 排除类型 | 选非贴片的组 |
| `role` 角色 | 所有组 |
| **`subtype` 屏蔽类型** | **只有 SH** |

同一提交还带进两处，三者叠加成死锁：

1. 后端 SH 分支恒返回 `recommended_action=None` / `suggested_destination=None`
   （界面显示"无自动建议"）
2. 确认勾按钮渲染条件是 `!resolution.destination` —— **区域一旦被赋值，勾消失**
   （`PlacementReview.tsx:571` 附近）
3. `subtype` 选择器位于详情面板上方，实际使用中被滚动条隐藏

结果：SH1 处于「没有勾 + 没有建议 + 提示指错方向（报"必须填编码"，而编码已填）」。
并且 `moveGroup` 在切换区域时会清空 `subtype`（`if subtype === "cover" && destination === "smt"` → `""`），
所以左右移动永远补不上，即用户所说"不管移到哪里都不能点下一步"。

**其他位号不受影响**：它们只需回答"区域"，且都有自动建议可一键采纳。
SH 是唯一被位号前缀强制进入审查、且唯一多一个必答字段的位号。

### 根本病因

判定链把三件正交的事绞在一起：**这是不是一颗料 / 装不装 / 是什么类型**。
位号前缀（`DEFAULT_FORCED_REVIEW_ROLES = (("SH","shield"),)`）和描述文本
能在身份已成立之后撤回结论，于是产生「有编码、却拿不到任何建议」的审查项。

---

## 1. 领域规则（已与用户确认，作为唯一依据）

固定三段顺序求解，**后一段不得回头改写前一段**：

| 顺序 | 判据 | 禁止使用 |
|---|---|---|
| ① 身份 | `part_number` 非空 → 是一颗料；为空 → 缺编码，问人补 | 编码形态、位号前缀、描述 |
| ② 装不装 | 只看 NC 证据 | 位号前缀、类型 |
| ③ 类型 | 描述 / 封装 / 库名定类型；**位号前缀只作候选提示** | 不得改写 ①② |

补充规则（用户明确给定）：

- **编码规范一直在变，不做形态校验**。"有编码就能确定是一颗料"。
  编码形态表**只用于**"编码列为空时建议一个编码"，**不参与身份判定**。
- **SH 默认屏蔽罩**，屏蔽罩是采购物料但从不进贴片 BOM → 非贴片 / 范围排除。
  人可改为屏蔽支架（进贴片区）。
- **查验清单（用户选定方案 C）**：已按物料纳入、但描述命中工艺词的行，
  **列出来给人查验**，不由系统替人裁决，且**不阻塞流程**。

### 不变量（回归必须锁死）

1. 任何 `part_number` 非空的行，必定得到一个装机建议（`recommended_action` 非 None）。
2. 位号前缀不得否定身份，也不得推翻 NC 结论。
3. 自动**排除**（破坏性动作）必须有位号前缀 + 封装/库 双重佐证；
   单一文本来源只能命名类型，不能触发排除。
4. 一个审查组只需回答"装 / 不装"一件事即可完成；类型等附加字段必须有默认值。
5. 查验清单只呈现，不设门禁。

---

## 2. 后端改造（`app/backend/tools/bom_classify.py`）

### T1 身份判定去掉一切格式与占位表

- `identify_material()`：`part_number` 非空且不是「明显填错」→ `identity_confirmed`。
  保留的拒绝理由仅限「这一格根本不是编码」：占位残渣 / 乱码 / 路径 / 含 NC 词 /
  整段中文描述误填。
- **删除** `DEFAULT_WEAK_PART_NUMBER_VALUES`（`TP`/`GND`/`RES_NP`/`CAP_NP` 等 12 值精确表）
  及其配置读取。理由：Capture 库名（`Test`、`TP2`、`Z_TP4`、`Z_Mark1`）由设计者随手命名，
  不可穷举，列表天生补不完。
- **不得**引入任何「编码形态匹配才算料」的判据（已实测会误伤 `P-ALPHA-01`、`X1-Y2`）。

验收：`Test` / `TP` / `P-ALPHA-01` / `302010300327` / `C.C1105M21` 全部 `identity_confirmed`。

### T2 NC 判定提到类型之前，只保留一处

- `classify()` 中把 NC 分支移到屏蔽/工艺分支**之前**。
- **删除**屏蔽分支内重复实现的 NC 处理（禁止双路径）。

验收：任意前缀（含 SH）+ `value="NC"` → `confirmed_nc`；+ `value="10K"` → 非 NC。

### T3 类型由文本定，前缀只作候选；排除需双重佐证

- `infer_role()`：`library_roles`（封装/库/描述）与 `reference_roles`（前缀）任一命中即定类型；
  **两者一致时 `confidence="strong"`，单一来源 `"medium"`**。
- 把描述字段纳入类型词表比对（现有 `library_blob` 只看封装/库，需加入 `desc`/`name`/`model`）。
- `corroborated_process_role` 仍要求 `confidence == "strong"`，
  以保证**只有双重佐证才能自动排除**（不变量 3）。

验收：`ANY17` + 描述 `JUMPER test link` + 无编码 → **不得**自动排除（应为待补编码）。
`TP10` + 前缀 TP + 描述含测试点 + 封装 TP0P4 → 可自动排除。

### T4 屏蔽罩改为有默认值的可采纳项

- `ClassificationResult` 增加 `shield_subtype: str = ""`，经 `_result()` 透传，
  并在 `ReviewGroup.payload()` 中下发。
- 屏蔽分支：返回 `recommended_action="exclude"`、`suggested_destination="non_smt"`、
  `exclusion_kind="scope_excluded"`、`shield_subtype="cover"`。
  **不得**再返回 `None` 建议。
- 触发条件改为 `role.role == "shield"`（类型），不再依赖 `role.forced_review`。

验收：SH + 真编码 + 描述是测试点（库套错）→ 仍为物料，且带完整建议。

### T5 删除有编码行的"降级为待裁决"分支

- **删除** `R4D`（有编码 + 强工艺词但无佐证 → conflicting 无建议）
- **删除** `R4A`（有编码 + 歧义机构件词 → suspected_material 无建议）
- 有编码且双重佐证为工艺件 → `confirmed_material` + `exclude/non_smt/process_only`
- 有编码其余情况 → `confirmed_material` + `keep/smt`

### T6 新增查验清单

- `PlacementAnalysis` 增加 `code_verification: tuple[dict, ...]`，payload 键 `code_verification`，
  `summary` 增加计数。
- 生成规则：`identity_confirmed` 且 `part_number` 非空 且证据含 `process_keyword`
  → 按 (编码, 工艺词) 归并，输出 `part_number` / `keyword` / `reason` / `description` /
  `refs` / `row_numbers`。
- **不得**让它影响 `requires_review` 或任何门禁。

---

## 3. 前端改造（`frontend/src/tools/PlacementReview.tsx`）

### T7 完成判定回到"一个组只答一件事"

- `placementResolutionComplete()`：
  - 未选区域 → 未完成
  - 选"非贴片" → **完成**（不再追加 `exclusion_kind` / `subtype` 必填）
  - 选"贴片" → 要求编码 + 名称/型号/描述之一（这条 0.5.3 就有，保留）
- `role` / `exclusion_kind` / `subtype` 全部改为**有默认值的可选修正项**，不作必答。
- 新增导出 `placementResolutionIssue(group, resolution): string` 返回**具体**未完成原因，
  替换当前硬编码那句「进入贴片区时必须填写内部子项编码…」（它在字段已填的情况下会误报）。
  在详情面板**顶部**渲染该原因（不可被滚动条隐藏），且不限定 `destination === "smt"`。

### T8 修复确认勾消失与 subtype 被清空

- 确认勾按钮渲染条件由 `!resolution.destination` 改为 `!complete`
  —— 只要没完成就一直有可点的确认入口。
- `blankResolution()`：屏蔽类组的 `subtype` 从后端 `group.shield_subtype` 播种。
- `normalizeResolution()`：`subtype` 缺失时回落到默认值，不清空。
- `moveGroup()`：屏蔽类切换区域时按区域推导类型（贴片→支架、非贴片→屏蔽罩），
  显式选择的"其他"保留；**禁止**再把 `subtype` 置空。

### T9 展示查验清单

- 在审查页新增一个只读区块（与"自动判定项""明确 NC"同级折叠面板），
  标题含条数，列：编码 / 工艺词 / 位号数 / 描述 / 原因。
- 明确文案说明：这些已按物料纳入，若编码实为库占位名请返回改为不装。
- 该区块**不得**成为"继续"的前置条件。

---

## 4. 既有测试处置（16 个断言旧规则，需按新规则改写）

以下测试断言的是被本方案推翻的旧规则，逐个改写为新规则；**不得**为了让它们通过而在
实现里加条件分支。

`tests/test_bom_placement_matrix.py`
- `test_valid_code_with_description_only_process_text_is_a_conflict[镀金测试点/PCB安装孔]`
  → 改为：有编码 + 单一文本工艺词 → 仍是物料，且出现在查验清单
- `test_valid_code_with_ambiguous_mechanical_text_is_material_review[焊接铜柱/M3螺母柱结构件]`
  → 改为：有编码 → `confirmed_material`
- `test_shield_ref_with_pure_nc_value_still_requires_review` → 改为：SH + 纯 NC → `confirmed_nc`
- `test_blank_code_shield_is_reviewed_once_in_shield_category` → 改为：屏蔽组带 `exclude` 建议
- `test_coded_sh_material_outweighs_lower_priority_process_metadata` → 改为：仍是物料且带建议

`tests/test_bom_rule_v2.py`
- `test_formal_identity_outranks_description_only_process_text` → 同上
- `test_reference_and_package_together_can_recommend_process_zone` → 状态改为 `confirmed_material`，
  去向仍 `non_smt/process_only`
- `test_shield_is_forced_review_and_conflicting_metadata_has_no_recommendation`
  → 改名并反转：屏蔽项**必须**带建议
- `test_shield_with_pure_nc_still_requires_type_and_destination` → 改为 NC 先于类型
- `test_ambiguous_mechanical_text_never_auto_excludes_coded_material` → 保留"不排除"意图，
  期望值改 `confirmed_material`
- `test_weak_process_symbol_part_number_cannot_take_r1_shortcut` → 删除或反转
  （该规则已被"有编码即为料"取代）
- `test_coded_h_reference_with_smt_mechanical_package_is_material_review` → 改为带建议

`tests/test_bom_process_conflicts.py`
- `test_adapter_returns_shield_and_process_materials_in_one_review`
- `test_run_bom_process_requires_confirmation_for_sh_even_when_value_is_nc`
  → 按新的 SH 语义改写

---

## 5. 新增测试（预算：跨模块 ≤12 个用例，表驱动）

已有草稿 `tests/test_bom_general_rules.py`（12 用例，当前全绿），保留并作为类不变量守卫：

1. 上报案例：SH + 真编码 + 库元数据错误 → 物料 + `exclude/non_smt`
2. 同类案例：TP10 + 编码 `Test` + 封装不一致（与上报案例在前缀/编码/描述/封装四项均不同）
3. 边界邻居：普通有编码电阻 → `keep/smt`，行为不变
4. 边界：编码为空 → 仍然问人补编码
5. 身份只看编码列（`302010300327` / `P-ALPHA-01` / `Test`）
6. 前缀不能否定身份、不能推翻 NC（`SH` / `U`）
7. 屏蔽默认屏蔽罩且可回答
8. 编码与描述矛盾 → 进查验清单，且不产生审查组
9. 类不变量：有编码的审查组必带建议

前端补 vitest：完成判定只需"装/不装"、确认勾在未完成时始终存在、
移动屏蔽项不会清空类型、查验清单渲染且不阻塞。

---

## 6. 验收标准

1. 用户上报场景可通：SH1 有勾可点、有建议可采纳，"继续"可点。
2. 三份真实 BOM（`D:\desktop\工具集\` 下 IAC4_MB_V05 / IAC3A_MB_V08 / 功耗版V2）
   **装机去向逐行不变**，仅"需人工裁决"数量下降。
   参考实测：待审查行 60→5、81→11、242→187。
3. 不变量 1~5 全部有测试覆盖。
4. `pytest` + `vitest` + `npm run build` 全绿。
5. 代码中不存在：`DEFAULT_WEAK_PART_NUMBER_VALUES`、`R4D`、`R4A`、
   屏蔽分支内的 NC 重复实现、以及任何「编码形态决定身份」的判据。

---

## 7. 禁止事项

- 禁止新增「检测某种输入形状 → 特殊处理 → 否则维持旧行为」的分支（双路径）。
- 禁止用位号前缀或描述推翻已成立的身份与 NC 结论。
- 禁止把测试改成能通过而不修设计。
- 禁止扩充「占位编码值」列表（Capture 库名不可穷举）。
- 不动 `VERSION` / `REVISION` / `UPDATE_NOTICE.json` / 签名；不动 `data/`；
  不执行安装器与 OTA；不碰 `docs/fix_plan_bom_and_subprocess_2026-07-17.md`。
- 推送只用 `git send-pack`。

---

## 8. 当前工作树状态（交接说明）

已有未提交改动，实现了 T1~T6 的大部分与 T8 的一半，可作为起点或直接丢弃重做：

- `app/backend/tools/bom_classify.py`：T1、T2、T3、T4、T5、T6 已实现
- `frontend/src/tools/PlacementReview.tsx`：仅 T8 的播种与 `moveGroup` 已改
- `tests/test_bom_general_rules.py`：12 用例，全绿（未提交）
- **未完成**：T7、T9、第 4 节 16 个既有测试、全量回归、构建

尚未确认的一项判断（执行前请与用户确认）：
**有编码且双重佐证为工艺件的行（如 TP + 测试点描述 + TP0P4 封装）现在自动排除、不再询问。**
这是待审查数从 60 降到 5 的主因，代价是"排除"这一破坏性动作失去人工确认，仅靠查验清单兜底。
若需恢复询问，改 T5 中该分支的 `state` 为 `suspected_process` 即可（去向不变）。
