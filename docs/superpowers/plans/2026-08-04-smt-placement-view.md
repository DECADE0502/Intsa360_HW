# 贴片位号视图 — 重做方案

状态：待执行（交给 codex）
日期：2026-08-04
基线：0.5.17
参考资料目录：`D:\desktop\IAC4工作\IAC4_MB_V05\IAC4_MB_V05贴片资料\IAC4_MB_V05贴片资料`

---

## 0. 为什么重做

现有「位号图查看」（`refdes_viewer`，0.5.15 引入）的全部能力是：从 PDF 文字层提位号 + 点击定位。
**这两件事用任何 PDF 阅读器按 Ctrl+F 都能做，而且做得更好。** 它没有提供任何 PDF 阅读器做不到的东西。

真正的价值在于**把 BOM 判定结果叠回板面**：哪些位号贴装、哪些 NC、哪些是非贴片工艺项。
这个信息只存在于 BOM 处理结果里，PDF 阅读器不可能知道。

---

## 1. 关键设计决策（全部由实测数据定，勿推翻）

### 1.1 坐标源用 XY.txt，不用 PDF 文字层

实测 `IAC4_MB_V05`：

| 来源 | 位号数 | 覆盖率 |
|---|---|---|
| `XY.txt` | **1037**（正面 450 / 反面 587） | **100%** |
| PDF 文字层 | 803（正面 444 / 反面 359） | **77%** |

PDF 缺失 239 个（R×99、C×98 等密集小器件的标号被 CAM 省略），
另有 5 个只在 PDF 里（`A1` `AU10` `C224A` `C3421` `R254A`，图框文字误提）。

**结论：只渲染 XY.txt 中存在的位号。** PDF 方案覆盖率只有 77%，用于首件核对会漏掉近四分之一，
比没有更危险；且需要 798 点仿射配准、每页要下 6MB 位图，又慢又不准。

XY 提供 `ref / x_mm / y_mm / rotation / side / footprint`，`mirror` 字段直接给面别，
**零配准误差，面别不用猜**。

### 1.2 板框用位号包络，不用 DXF

实测：`XY` 单板范围 **37.6 × 37.5 mm**；`iac4_mpcb_asm_260417.dxf` 解析出
**187.2 × 83.1**、原点在 (419, −194)、51 个环 —— 那是装配/拼板图纸空间，
含图框与多块板，无法可靠对齐到 XY 空间（要猜哪个环是单板、再猜平移量）。

**结论：板框 = 全部位号的包络矩形 + 边距，圆角绘制。** 已与用户确认可接受
（误差为边缘器件到板边的几毫米，对"找位号"无影响）。

### 1.3 自己绘制，不用 PDF 底图

用户要求"不需太精美但必须精确、功能必须全但必须流畅"。按 XY 直接绘制在这两点上都占优：

| | 自绘（本方案） | PDF 底图 |
|---|---|---|
| 坐标误差 | 0（XY 即真值） | 仿射配准残差 |
| 覆盖率 | 100% | 77% |
| 每页加载 | 数百 KB JSON | 6MB 位图 |
| 面别切换 | 字段直接给 | 需逐页判定 |

### 1.4 已确认的其他决定

- **拼板**：用户明确"只是看看没啥用" → **本期不做**，不留半成品开关。
- **PDF**：保留一个「打开原始位号图」按钮（新窗口打开），需要看丝印细节时用，**不参与渲染**。
- **版本一致性**：不校验、不告警。用户上传完整贴片资料目录即代表内部匹配。

---

## 2. 输入

用户上传**整个贴片资料目录**，工具自动识别，不要求用户逐个指认文件。

| 文件 | 识别依据 | 用途 | 必需 |
|---|---|---|---|
| `XY.txt` | 首行 `VERSION` + `UUNITS`，数据行 `refdes!x!y!rotation!mirror!symbol_name` | 坐标 / 面别 / 旋转 / 封装 | ✅ |
| `*SMD*.pdf` / `*REF*.pdf` | 文件名含 SMD/REF 且**不在**原理图子目录 | 「打开原始位号图」链接 | ⬜ |
| 其余（`*.art`、`*.rar`、`*.stp`、`*.dxf`、`原理图/*.pdf`） | — | **忽略** | — |

另需 BOM 状态来源，二选一：
- 从「历史记录」选之前处理过的批次（可拿到完整判定：判定类型、理由、审查决议）
- 直接上传成品 BOM + NC 汇总两个 xlsx

按**位号**join。NC 汇总已有 `位号 / 子项编码 / 描述 / 过滤原因 / 判定类型` 列，
判定类型取值 `system_nc` / `process_default` / `user_excluded` / `scope_excluded` / `insufficient_default`。

复用现成模块，勿重写：
- `app/backend/parsers/xy.py::parse_xy_file` —— 实测直接可用，返回 `(UnitInfo, list[Component])`
- `frontend/src/components/spatialIndex.ts` —— 视口裁剪
- `frontend/src/components/drawingViewport.ts` —— 缩放平移数学

---

## 3. 状态模型

每个位号最终落在一个状态上（由 XY 与 BOM join 得出）：

| 状态 | 判定 | 颜色 |
|---|---|---|
| `placed` 贴装 | 在成品 BOM 中 | 🟢 绿 |
| `nc` 未贴 | 在 NC 汇总，判定类型 `system_nc` / `user_excluded` | 🔴 红 |
| `non_smt` 非贴片 | 判定类型 `process_default` / `scope_excluded` | ⬜ 空心灰 |
| `bom_only` BOM 有、坐标无 | 在 BOM 中但 XY 里没有 | 画不出点 → **单独列清单** |
| `xy_only` 坐标有、BOM 无 | 在 XY 中但两份 BOM 都没有 | ⚫ 深灰 |

`bom_only` 与 `xy_only` 必须在界面上给出明确计数和清单，**不得静默忽略**——
这是唯一会让操作员误判"已全覆盖"的地方。

---

## 4. 视图

左上角切换，同一份数据只改配色，不重新加载：

1. **贴装状态**（默认）—— 绿/红/空心灰/深灰，全量显示
2. **NC 专项** —— 只亮红点，其余淡化到 15%（首件核对主场景）
3. **备料风险** —— 等级非「优选/正常」的标黄（验证中/限选/临时/禁选）
4. **版本差异**（选了第二份 BOM 才出现）—— 🟠换料 / 🔵新增 / ✖删除

## 5. 交互

- **正面 / 反面** 切换：按 `side` 过滤；反面视图 **X 轴镜像**（符合翻板从背面看的直觉），并明确标注"已镜像"
- **左栏**：搜索框（支持逗号分隔多位号一次性高亮）+ 按状态分组及计数 + 点击定位
- **点击位号** → 平滑缩放居中 + 高亮 + 显示编码/描述/判定理由
- **点图上标记** → 左栏同步选中并滚动可见
- **缩放** 到一定倍数后显示位号文字，密集时自动隐藏
- 「打开原始位号图」按钮（新窗口）

## 6. 流畅性要求（硬指标）

- 数据一次性加载，约 1037 条，**≤500KB JSON**
- 只渲染视口内标记（`spatialIndex`），单面 450~590 点
- 缩放平移用 CSS transform，**不触发重排**
- 视图切换只改颜色，**不重新请求数据**
- 验收：1037 个位号下，缩放/平移操作 **无可感卡顿**

---

## 7. 任务

**T1 资料目录识别**
新建 `app/backend/smt_view/discovery.py`：扫描目录 → 定位 `XY.txt`（按内容特征，不只看文件名）
与参考 PDF；其余忽略。找不到 XY 时明确报错，不静默降级。
验收：对参考目录（15 文件 / 41MB）正确认出 `XY.txt` 与 `IAC4_MB_V05-260507SMD.pdf`，
且**不**把 `原理图/IAC4_MB_V05_20260507.pdf` 当位号图。

**T2 板面模型**
新建 `app/backend/smt_view/board.py`：`parse_xy_file` → 位号列表；
板框 = 包络 + 边距；输出 `{ref, x_mm, y_mm, rotation, side, footprint}` 与板框 bbox。
验收：参考目录得 1037 个位号、正面 450 / 反面 587、范围 37.6×37.5mm。

**T3 状态 join**
新建 `app/backend/smt_view/state.py`：按位号 join 成品 BOM 与 NC 汇总 → §3 状态模型；
输出 `bom_only` / `xy_only` 两份清单及计数。
验收：join 后每个 XY 位号有且只有一个状态；两份差异清单计数正确。

**T4 契约与 API**
`app/backend/contracts/smt_view.py` + `app/backend/api/routers/smt_view.py`：
`POST /api/v1/smt-view/boards`（入参：资料目录 + BOM 来源）→ 一次返回全部位号与状态。
`GET .../boards/{id}` 复取。**不做分页**（1037 条一次给完）。

**T5 前端板面视图**
`frontend/src/tools/smtView/`：`SmtViewPane` + `BoardCanvas` + `RefList`。
按 §4/§5/§6 实现。复用 `spatialIndex`、`drawingViewport`。

**T6 工具注册**
`analysis_tools.py` 注册 `smt_view`「贴片位号视图」归类 SMT；
`config/capabilities.json` 同步登记；`App.tsx` 路由。
**同时移除** `refdes_viewer`（含 `app/backend/refdes/`、`services/refdes_service.py`、
`api/routers/refdes.py`、`contracts/refdes.py`、`tools/refdes_viewer.py`、
`frontend/src/tools/refdes/`、`tests/test_refdes.py`、`frontend/src/test/refdes-viewer.test.tsx`），
并同步修正工具数断言（`test_platform_api` / `test_fastapi_api` /
`test_backend_refactor_api` / `test_capabilities_registry`）。

**T7 测试**（预算：跨模块 ≤12 用例，表驱动）
后端：目录识别、1037 位号与面别、状态 join 的四种状态 + 两份差异清单、缺 XY 时报错。
真实目录用例经 env 变量 opt-in（沿用 `SMT_REAL_SAMPLE_DIR` 模式），缺失则跳过。
前端：状态配色、正反面镜像、搜索定位、图→列表反向联动。

**T8 文档**
更新 `docs/Insta360_HW_Platform_Guide.md`。

---

## 8. 验收标准

1. 上传参考目录 + 一份处理过的 BOM → 立即出板面，1037 个位号全部可见、可搜、可点。
2. 切「NC 专项」→ 只亮 NC 红点，数量与 NC 汇总行数一致。
3. 正反面切换正确，反面已镜像并有标注。
4. `bom_only` / `xy_only` 两份清单有计数、可查看。
5. 1037 位号下缩放平移无可感卡顿。
6. `refdes_viewer` 已完全移除，工具数断言同步更新。
7. `pytest` + `vitest` + `npm run build` 全绿。

## 9. 禁止事项

- 禁止用 PDF 文字层作为坐标源（覆盖率仅 77%）。
- 禁止用 DXF 作板框（坐标系对不上）。
- 禁止要求用户逐个指认文件——传目录即可。
- 禁止把 `bom_only` / `xy_only` 静默忽略。
- 禁止做拼板（用户已明确不需要）。
- 不动 `VERSION` / `REVISION` / `UPDATE_NOTICE.json` / 签名；不动 `data/`；
  不执行安装器与 OTA；推送只用 `git send-pack`。
