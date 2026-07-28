# BOM 风险检查 v2 — 单份 PCBA/PLM BOM 导入前体检（重构 + 补全）

状态：设计 + 待执行任务清单（交给 codex 执行）
日期：2026-07-28
作者：Claude（Opus 4.8）
适用版本：在 0.5.8 之后（feature/v0.4.0-overhaul）

---

## 0. 背景与问题（基于三份真实 BOM 实测）

参考 BOM（只读，勿改）：
- `203010100836_IAC4_MB_POWER_V03_PCBA_BOM.xlsx`（PVT_VER7，122 行）
- `203010100819_IAC4_MB_POWER_V02_PCBA_BOM.xlsx`（PVT_VER6，122 行）
- `203010100900_IAC4_MB_V10_PCBA_系统导出旧BOM_20260728.xlsx`（BOM导入模版，143 行）

这批是 **PLM/ERP 导入格式**（两段式：父项物料 / 子项物料属性 / BOM 属性），固定 19 列，第 2 行才是真实表头，数据从第 3 行起，首个数据行是父项 PCB 自身；另有 `Sheet2` 单位说明（噪音）。与旧的 Capture 导出格式完全不同。

**实测暴露的现状缺陷（均已复现）：**

1. **解析层残缺**：`bom_risk.py` 走 `parsers/bom_table.py`，只认 10 个字段。PLM 的 `发料方式 / 替代组编码 / 替代策略 / 替代方式 / 替代优先级 / 备注 / 是否参与MRP / 是否跳层 / 父项编码` **全部读不到**。
2. **`型号` 列被三重误用**：真实 `desc` 列在型号之后，别名撞车，导致 `desc/package/value` 都 fallback 到型号文本。
3. **三大检查退化**：屏蔽支架 / 机构件 / 测试点检查依赖外部 `placement_decisions`（语义/决策清单）。独立入口不传清单 → 全部退化成 `info：未提供决策清单无法判断`。V10 里明明有 `SH1 主板屏蔽支架`，却报“无法确认”。
4. **替代组不可见**：V10 有 26 组替代、27 个替代件行。替代件**本身没有位号**（位号挂在主料行）。当前规则看不到替代组，会把替代件误当“空编号行 / 数量不符”。
5. **父项 PCB 行**：首行父项（数量 1、无位号）当前被 `PCB 裸板` 检查捡到算 ok，但没有作为“父项自身，不参与贴装统计”被显式排除，位号/数量统计口径不清。
6. **独立入口无渲染**：图中独立“BOM 风险检查”页走 `LegacyToolPane → ResultPanel`，**只显示“运行完成 + 下载报告”**，结构化 findings / grade / type 一律不渲染。只有 BOM 处理向导内的 `RiskView` 才渲染。
7. **NC 全为 0**：三份都是清洗后的成品/系统 BOM。工具无法区分“本就无 NC（正面结论）”与“该有却漏检”。

**关键机会**：项目已有 `app/backend/bom_semantics/`（`normalize_workbook` → `CanonicalRow`），实测能完整解析 PLM 19 列，并已带 `is_nc / is_substitute_main / is_substitute_alternative / substitute_group_code / issue_method / hardware_version / quality_flags / references / parent_code` 等全部语义字段，且能识别 `WorkbookProfile`（PLM_SINGLE_BOARD 等）。风险检查应**复用该引擎**，而不是给旧解析器打补丁。

**已确认的三项方向（用户拍板）：**
- 解析层：改用 `bom_semantics` 语义引擎。
- 判定自足性：仅凭 BOM 自身属性（名称/描述/位号/发料方式/替代组等）直接判定并分级告警，**不依赖外部决策清单**。
- 工具形态：独立“BOM 风险检查”做成完整自足工具——分级 findings + 分类表格 + 多 sheet Excel 报告全部内联渲染，并复用同一引擎供向导调用。

---

## 1. 目标

把“BOM 风险检查”做成**通用、属性驱动、与具体板号/料号无关**的单份 BOM 导入前体检：

- 任意 PLM / OA / Capture 格式单份 BOM 上传即出体检结论。
- 检查项覆盖 PCBA 导入前所有已知风险维度（见 §3）。
- 每项 finding 有：级别（blocker/warn/info/ok）、名称、结论、命中明细、可导出。
- 结论**分级**：致命（会导致导入失败/错料）> 警告（需人核对）> 提示（信息性）> 通过。
- 前端独立页与向导内一致地渲染结构化结果。
- 全部规则可配置化、可回归，不对任何单一 BOM/料号特判。

---

## 2. 架构决策

### 2.1 解析层统一到语义引擎

- 新建 `app/backend/tools/bom_risk_model.py`（或在 `bom_risk.py` 内）：调用 `normalize_workbook(path)` 得到 `NormalizedSource`，再构造风险检查用的**行视图** `RiskRow`（对 `CanonicalRow` 的轻封装，补齐派生标记）。
- 保留对 `WorkbookProfile` 的感知：PLM_SINGLE_BOARD / PLM_MULTI_BOARD / OA_BOM / OA_ECR / CAPTURE_RAW / UNKNOWN。不同 profile 下部分检查项按适用性显示（不适用 → 明确标注“本格式不适用”，不是静默 ok）。
- `normalize_workbook` 返回的 `findings`（BLOCKER/WARNING）要并入风险结论（如 profile 未识别、必填字段缺失、编码科学计数法丢精度）。

### 2.2 判定自足（不依赖决策清单）

所有判定只用 BOM 自身可得信号，规则通用、配置化：

- 屏蔽支架：`references` 前缀 `SH` **或** name/desc 命中屏蔽支架词（屏蔽支架 / 屏蔽罩 / shield bracket）。
- 机构件：name/desc 命中机构件词表（螺丝/螺母/螺柱/铜柱/垫片/华司/散热片/导热垫/结构件/支柱…，可配置）。
- 测试点/工艺：位号前缀（TP/JP/FID/MK/MH/Z_TP，可配置）**或** desc 命中工艺词（测试点/跳线/短接/Mark/基准/工艺边/FIDUCIAL…）。位号前缀只作为**辅助信号**，与描述冲突时以描述为准（沿用平台“前缀不独裁”原则）。
- NC：复用 `CanonicalRow.is_nc` + `bom_classify` 的纯 NC / 嵌套 NC 判定。
- 决策清单变为**可选增强**：若调用方（向导）传入语义/决策清单，用它校正并做 BOM↔清单一致性核对；不传则完全用属性自足判定。保留既有 `semantic_manifest / decision_manifest` 入参兼容。

### 2.3 分级模型

finding 增加 `level` 字段（`blocker | warn | info | ok`），保留 `status` 兼容旧前端。
- blocker：父项缺失 / 必填字段缺失 / 编码丢精度 / 重复位号 / 数量与位号数不符 / 空编码且有位号。
- warn：非优选等级、位号↔类型冲突、疑似机构件或测试点混入贴装区、NC 混入、替代组结构异常。
- info：版本敏感料提醒、发料方式分布、替代组概览、屏蔽支架清单。
- ok：该项检查通过（含“本就无 NC”这类正面结论）。

### 2.4 前端渲染统一

- 新建 `frontend/src/tools/BomRiskPane.tsx`（独立工具专用），替代 `LegacyToolPane` 对 `bom_risk_check` 的兜底渲染。
- 抽出共享渲染组件 `RiskFindings`（概览计分 + 分级页签 + 分类明细表 + 导出下载），供独立页与向导内 `RiskView` 共用，消除“只有向导才渲染”的分裂。
- `App.tsx` 路由：`bom_risk_check` → `BomRiskPane`（不再落 LegacyToolPane 兜底）。

---

## 3. 检查项全集（通用、属性驱动）

> 每项标注：级别、判定信号、三份 BOM 实测预期。均不针对具体料号。

| # | 检查项 | 级别 | 判定信号 | 实测预期 |
|---|---|---|---|---|
| 1 | 工作表格式识别 | blocker/ok | WorkbookProfile；识别失败=blocker | 三份=PLM_SINGLE_BOARD |
| 2 | 必填字段/表头完整 | blocker/ok | 语义引擎 findings | 三份 ok |
| 3 | 编码精度（科学计数法丢失） | blocker/ok | 数字编码被转 3.02E+11 等 | 三份 ok（需保留检测） |
| 4 | 父项 PCB 裸板 | ok/warn | 父项行（无位号+层数/HDI/PCB 描述）；缺失=warn | 三份均有父项 |
| 5 | 位号/数量口径 | info | 排除父项与替代件后统计有效贴装位号数、料号数 | — |
| 6 | 重复位号 | blocker | 跨行展开后重复 | 三份预期无 |
| 7 | 空编码行 | blocker | 有位号但子项编码为空（替代件无位号不算） | 三份预期无 |
| 8 | 数量=位号数 | blocker | qty≠展开位号数（替代件/父项豁免） | 三份预期一致 |
| 9 | NC/未贴混入 | warn/ok | is_nc / 纯NC / 嵌套NC | 三份=无（正面结论“已清洗干净”） |
| 10 | 屏蔽支架 | info/warn | SH 前缀或屏蔽支架词 | V10 有 SH1；功耗版无 |
| 11 | 机构件混入 | warn/info | 机构件词表 | 按描述 |
| 12 | 测试点/工艺项 | warn/info | 前缀+工艺词 | 系统 BOM 多已剔除 |
| 13 | 位号↔器件类型冲突 | warn | 前缀期望(C/R/L)≠描述实际类型 | 三份各 12 处**真实**（如 C223 实为射频电感）——保留 |
| 14 | 物料优选等级 | warn/ok | 非“优选/正常”计数分类 | V03=32项，V10=61项非优选正常（验证中/限选/临时…） |
| 15 | 替代组结构 | warn/info | substitute_group_code 分组：每组须恰好 1 主料、≥1 替代；主料带位号、替代件无位号；优先级/策略齐全 | V10 有 26 组；功耗版 0 组 |
| 16 | 发料方式分布 | info/warn | issue_method（直接领料/直接发料）；异常值告警 | V10=138直接发料+5直接领料；功耗版=全直接领料 |
| 17 | MRP/跳层 | info | 是否参与MRP / 是否跳层 分布，异常提示 | — |
| 18 | 版本敏感料 | info | eMMC/DDR/LPDDR/UFS/NAND/SOC/WIFI/加密 命中 | 三份均命中数颗 |
| 19 | 备注/工程编号 | info | 备注非空（YXJGX/PLM 编号等） | V10 大量备注 |
| 20 | 单位一致性 | info/warn | unit 非 ea 或空 | 三份=全 ea |
| 21 | （可选）BOM↔决策清单一致性 | warn/ok | 传入清单时才跑 | 独立入口跳过 |

---

## 4. 规则通用化与配置

在 `config/default.json → bom` 下扩展（沿用现有 `material_code_shapes / nc_keywords` 风格）：

```jsonc
"bom": {
  "risk": {
    "mechanical_keywords": ["螺丝","螺钉","螺母","垫片","华司","铜柱","支柱","散热片","导热垫","结构件","定位柱"],
    "shield_keywords": ["屏蔽支架","屏蔽罩","shield bracket","shield"],
    "process_keywords": ["测试点","跳线","短接","基准","工艺边","MARK点","FIDUCIAL","MOUNTINGHOLE"],
    "process_ref_prefixes": ["TP","JP","FID","MK","MH","Z_TP"],
    "grade_ok": ["优选","正常"],
    "version_sensitive": ["eMMC","EMMC","DDR","LPDDR","UFS","NAND","SOC","WIFI","加密"],
    "expected_prefix_type": {"C":"电容","R":"电阻","L":"电感"},
    "code_prefix_type": {"C":"电容","R":"电阻","L":"电感"}
  }
}
```

规则代码只读配置，不硬编码词。缺配置时回落到内置默认。

---

## 5. 输出

### 5.1 内联结果（前端渲染）

`risk_report`：
- `profile`、`stats`（数据行/有效贴装位号/料号/替代组数/父项）
- `findings[]`：`{level, status, name, message, code, detail_ref}`
- 分类明细：`grade_flags`、`type_flags`、`substitute_groups`、`shield_items`、`mechanical_items`、`process_items`、`nc_items`、`issue_method_dist`、`version_sensitive`
- `counts_by_level`

### 5.2 Excel 报告（多 sheet）

`BOM风险检查_<时间>.xlsx`：
- `风险概览`（检查项/级别/结论）
- `等级明细`、`位号类型冲突`、`替代组`、`屏蔽支架/机构件/工艺项`、`版本敏感料`、`NC明细`（有才写）

---

## 6. 任务清单（交给 codex；每个任务须一步到位、可回归，不打补丁）

> 约束：不改 VERSION/REVISION/UPDATE_NOTICE.json/签名；不动 `data/`；不执行安装器/OTA；`docs/fix_plan_bom_and_subprocess_2026-07-17.md` 保持不动；只用 `git send-pack` 不用 `git push`。参考 BOM 只读。

**T1 — 语义引擎驱动的风险行模型**
- 新增 `app/backend/tools/bom_risk_model.py`：`build_risk_rows(path) -> RiskModel`，内部调 `normalize_workbook`；产出 `RiskRow`（含 refs、code、name、model、desc、grade、qty、unit、issue_method、substitute_* 、is_nc、is_parent、hardware_version、quality_flags、profile）。
- 识别并标记父项行（`parent_code == material_code` 或无位号且描述含层数/HDI/PCB）。
- 验收：三份 BOM 全部 profile=PLM_SINGLE_BOARD，行数 122/122/143，替代组 V10=26；单测锁定。

**T2 — 通用风险规则引擎（属性自足）**
- 重写 `bom_rules.evaluate_bom_risks` 为消费 `RiskModel`；实现 §3 全部 21 项；引入 `level`；屏蔽支架/机构件/测试点/NC 改为属性自足判定，决策清单降为可选增强。
- 替代件（无位号）豁免空编码/数量检查；父项豁免贴装统计。
- 全部词表/前缀/等级读 `config/default.json → bom.risk`。
- 验收：对三份 BOM 输出符合 §3 实测预期（附断言表）；无决策清单时屏蔽支架/机构件/工艺项**不再**显示“未提供清单”。

**T3 — 替代组结构校验**
- 每组：恰 1 主料（is_substitute_main，带位号）、≥1 替代（无位号）、优先级唯一且连续、策略/方式非空；违反→warn 并列出组。
- 验收：V10 的 26 组通过；构造异常组的单测报 warn。

**T4 — bom_risk.py 重构**
- `_run_bom_risk_check_impl` 改用 T1/T2；`risk_report` 增加 §5.1 全部分类明细与 `counts_by_level`；Excel 改多 sheet（§5.2）。
- 保留 `semantic_manifest / decision_manifest` 兼容入参。
- 验收：独立 `bom_risk_check` 与向导 `bom_process` 风险步共用同一结论。

**T5 — 前端独立工具页 + 共享渲染**
- 新增 `frontend/src/tools/BomRiskPane.tsx`；抽 `RiskFindings` 共享组件（概览计分/分级页签/分类明细表/导出）。
- `App.tsx`：`bom_risk_check` 路由到 `BomRiskPane`；向导内 `RiskView` 复用 `RiskFindings`。
- 分级用颜色：blocker=红、warn=橙、info=蓝、ok=绿。
- 验收：上传三份 BOM 任一，独立页完整渲染 findings/等级/替代组/发料方式，不再只有“下载报告”。

**T6 — 配置与词表**
- 在 `config/default.json` 落 `bom.risk`；`bom_classify.classification_config` 旁新增 risk 配置读取（缺失回落默认）。
- 验收：删掉配置节点仍按默认工作；改词表即时生效的单测。

**T7 — 回归测试（golden，属性组合为主）**
- 后端：`tests/test_bom_risk_v2.py` 用三份 BOM 作 golden（路径经 env 变量 opt-in，缺失则跳过，遵循现有 `HW_BOM_GOLDEN_PATH` 模式），断言每项 finding 级别与计数；另加纯属性组合单测（不绑板名）。
- 前端：`bom-risk-pane.test.tsx` 断言分级渲染与空态。
- 验收：`pytest` + `vitest` 全绿。

**T8 — 文档**
- 更新 `docs/Insta360_HW_Platform_Guide.md` 的 BOM 风险检查段落，说明 21 项、分级、配置项、profile 适用性。

---

## 7. 验收总标准

1. 三份参考 BOM 均无解析告警、profile 正确、字段完整（含替代组/发料方式）。
2. 屏蔽支架/机构件/测试点/NC 在**无决策清单**下给出属性自足结论。
3. 替代件不再误报空编码/数量不符；父项不污染贴装统计。
4. 独立“BOM 风险检查”页完整渲染分级 findings 与分类明细。
5. 全部规则读配置、无单料特判；`pytest` + `vitest` 全绿。
6. 未触碰版本/签名/OTA/data/ 与禁改文件。

---

## 8. 不做（本期范围外）

- 多板 PLM（PLM_MULTI_BOARD）跨板汇总——本期只保证单板 profile 正确识别并给适用性提示。
- OA ECR 变更语义比对——已有独立引擎，不并入风险检查。
- 决策清单/语义清单的生成——仅消费，不新增生成流程。
