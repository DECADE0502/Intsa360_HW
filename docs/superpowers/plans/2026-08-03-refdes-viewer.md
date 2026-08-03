# 贴片位号图预览（PDF 直查）— 重做方案

状态：设计 + 待执行任务清单（交给 codex 执行）
日期：2026-08-03
分支：feature/v0.4.0-overhaul（当前 0.5.8 之后）

---

## 0. 需求（一句话）

**上传位号图 PDF → 左边列出该 PDF 里的所有位号 → 点一个位号 → 右边 PDF 上立刻定位并高亮。**

就这一件事，必须能独立、即时完成。不需要 BOM，不需要坐标文件，不需要配准，不需要走审查流程。

---

## 1. 现状有多差（实测证据）

当前「贴片布局对照」(`smt_layout`) 已被换成 `SmtAnalysisPane` 五步向导：
`资料 → 识别 → 配准 → 复核 → 交付`

### 1.1 致命：PDF 根本进不去

`frontend/src/tools/smtAnalysis/SmtAnalysisPane.tsx` 的 `start()`（约 L121-129）硬性两道门：

```js
if (!smtFiles.length)               { setError("请选择完整的 SMT 贴片资料目录。"); return; }
if (!workspace.historyBom && !bomFile) { setError("请选择处理后的 PLM/OA 成品 BOM。"); return; }
```

→ **只有一份位号图 PDF 时，第一步就被卡死，永远看不到任何东西。**

### 1.2 第二道门：没有坐标文件就走不下去

`IdentificationStep.tsx`（约 L191-195）：

```js
const canContinue = Boolean(selectedSet) && !duplicateSide && ...
```

`selectedSet` 来自 `run.coordinate_sets`（XY.txt 之类）。**没有坐标文件 → 「确认识别结果」永远置灰。**
还要额外选：坐标覆盖范围语义、坐标单位、每一页 PDF 归正面/背面。

### 1.3 第三道门：不配准不给看

`components/SmtBoardViewport.tsx`（L563-573）：

```
"位号图尚未完成配准，暂时不能显示叠加结果"
```

### 1.4 左边列表根本不是「这份 PDF 的位号」

`ReferenceNavigator.tsx` 列的是 `run.placements` —— BOM × 坐标 join 出来的装配对象，
而且被强制分成 `NC / 非 NC` 两个 Segmented 页签（审查视角，不是浏览视角）。

→ PDF 上印着、但不在 BOM/坐标里的位号，**永远不出现在列表里**。
→ 用户想「看这张图上有什么」，得到的却是「BOM 认为应该有什么」。

### 1.5 反差：PDF 自己其实什么都够

用真实位号图实测（`IAC4_MB_V05-260507SMD.pdf`）：

| 指标 | 结果 |
|---|---|
| 页数 | 2（正面/反面） |
| 正面提取位号 | **443 个** |
| 反面提取位号 | 358 个 |
| 精确定位成功 | **443 / 443（0 遗漏、0 重复）** |
| 耗时 | **0.02 秒** |

`app/backend/smt_analysis/refdes_extraction.py::extract_pdf_vector_refs` 已经能从 PDF 矢量文字里
把每个位号的 bbox / 中心点精确算到预览图像素坐标系，质量很好。
`pypdfium2` 已在 `scripts/build_release.ps1` 的运行时校验清单里，依赖是齐的。

### 1.6 结论

**能力是好的，外壳是错的。**
一个 0.02 秒就能出结果的能力，被包在「必须先交齐整套 SMT 资料 + 成品 BOM + 坐标文件，再做完配准和复核」的五步流程后面。
这就是「很垃圾」的根因——不是渲染差，是**门禁把简单需求变成了重工程**。

---

## 2. 方案：直查优先，审查降级为可选

### 2.1 核心原则

1. **PDF 自足**：只要一份 PDF（或图片），立刻可用。位号列表来自 PDF 本身。
2. **零门禁**：不要求 BOM / 坐标 / 配准 / 面别 / 单位。这些全部变成**可选增强**。
3. **一步到位**：上传 → 出列表 + 出图。中间没有向导步骤。
4. **点击即定位**：点位号 → 平滑缩放居中 + 高亮，图上也能反向点。

### 2.2 新工具形态

新增独立工具 **「位号图查看」`refdes_viewer`**，与现有 `smt_layout`（SMT 装配审查）并列，互不干扰。

```
┌─────────────────────────────────────────────────────┐
│  位号图查看        [选择 PDF]  页面▾  正面/反面      │
├──────────────┬──────────────────────────────────────┤
│ 搜索位号 ▢    │                                      │
│ ─────────    │        PDF 原页渲染                   │
│  C1          │           ● C107 ←高亮               │
│  C10         │                                      │
│ ▶C107  ←选中 │      滚轮缩放 / 拖动平移              │
│  C108        │                                      │
│  ...443 个    │                                      │
├──────────────┴──────────────────────────────────────┤
│  可选：叠加成品 BOM → 标出 NC / BOM 缺失（不强制）    │
└─────────────────────────────────────────────────────┘
```

### 2.3 后端

新增 `app/backend/tools/refdes_viewer.py` + 少量 API：

| 接口 | 作用 |
|---|---|
| `POST /api/v1/refdes-viewer/open` | 入参：pdf 路径（上传后）。返回 `doc_id` + 每页 `{page_id, w, h, preview_url, refs:[{ref,x,y,bbox}]}` |
| `GET  .../pages/{page_id}/preview` | 返回渲染好的页面位图（复用 `page_cache.PageCache`） |

复用现有模块，**不重写**：
- `smt_analysis/page_cache.py` → 页面渲染 + 本地缓存
- `smt_analysis/refdes_extraction.py::extract_pdf_vector_refs` → 位号定位
- `smt_analysis/drawings.py` 里的页面/面别启发式 → 只作提示，不作门禁

行为要求：
- 一次 open 把所有页的位号全提出来（实测 0.02s/页，无需懒加载）。
- 面别（正面/反面）只做**猜测并标注**，用户可切换，猜错不影响使用。
- 同一位号在一页出现多次 → 全部保留，点击时在多个命中之间循环定位。
- 无矢量文字的 PDF（扫描件）→ 明确告知「该 PDF 无可提取文字」，不静默空列表。

### 2.4 前端

新增 `frontend/src/tools/refdesViewer/`：

- `RefdesViewerPane.tsx` — 单页面，无 Steps，无向导
- `RefdesList.tsx` — 左侧：搜索框 + 虚拟列表（复用 `SmtPlacementVirtualList` 的虚拟滚动思路）
  - 默认**自然序**全量列出（C1, C2, C10 …），不预分 NC 页签
  - 可选筛选器（有 BOM 时才出现）：全部 / 仅 NC / 仅 BOM 缺失
- `RefdesCanvas.tsx` — 右侧：PDF 页图 + SVG 标记层
  - 复用 `components/smtBoardRenderer.ts`（变换/边界）与 `spatialIndex.ts`（命中测试）
  - 复用 `SmtBoardViewport` 已有的缩放/平移/键盘交互逻辑，**抽出共用**，不复制

**定位交互（必须做好，这是用户的核心诉求）：**
- 点列表项 → 右侧**平滑动画**移到该位号（约 250ms ease-out），缩放到可读级别（不小于当前，且至少能看清标号）
- 选中项：醒目高亮环 + 始终显示位号文字标签
- 图上点击标记 → 左侧列表同步选中并滚动到可见
- 键盘：`↑/↓` 在列表内移动即联动定位；`Enter` 居中；`Esc` 取消选中
- 同名多命中 → 显示 `2/3` 计数，重复点击/按 `Enter` 循环下一处

### 2.5 与现有审查流的关系

- `smt_layout`（SMT 装配审查五步流）**保持不动**，继续服务「完整资料 + BOM + 坐标 + 配准」的深度审查场景。
- 新工具是**轻量入口**：只想看图找位号时用它。
- 在 `smt_layout` 的识别步里加一个「先只看位号图」的跳转，缓解现有卡死体验（可选，低优先）。

---

## 3. 任务清单（交给 codex）

> 约束：不改 `VERSION` / `REVISION` / `UPDATE_NOTICE.json` / 签名；不动 `data/`；不执行安装器与 OTA；
> 不碰 `docs/fix_plan_bom_and_subprocess_2026-07-17.md`；推送只用 `git send-pack`；参考 PDF 只读。

**T1 — 后端：PDF 位号文档模型**
- 新增 `app/backend/tools/refdes_viewer.py`：`open_document(path) -> RefdesDocument`
- 复用 `page_cache` 渲染、`extract_pdf_vector_refs` 定位；支持 PDF 与 png/jpg（图片则位号列表为空并注明原因）
- 每页返回：尺寸、预览 URL、`refs[{ref, x, y, bbox, occurrence_index}]`、面别猜测
- 验收：对 `IAC4_MB_V05-260507SMD.pdf` 返回 2 页、正面 443 / 反面 358 个位号，全部带坐标；单测锁定计数与「0 遗漏」

**T2 — 后端：API 与契约**
- `POST /api/v1/refdes-viewer/open`、`GET /api/v1/refdes-viewer/docs/{doc_id}/pages/{page_id}/preview`
- 契约写入 `app/backend/contracts/`，与现有 smt_analysis 契约风格一致
- 路径越界防护沿用 `drawings.py` 的 `relative_to(root)` 校验
- 验收：接口契约测试；非法路径被拒；扫描件 PDF 返回明确提示而非空列表

**T3 — 前端：抽出可复用画布**
- 把 `SmtBoardViewport` 的缩放/平移/命中/键盘逻辑抽成 `components/boardCanvas/`（hook + 组件）
- `SmtBoardViewport` 改为消费抽出的公共件，**行为不变**（现有测试必须继续通过）
- 验收：`smt_layout` 相关既有 vitest 全绿，无回归

**T4 — 前端：位号图查看工具**
- 新增 `frontend/src/tools/refdesViewer/`（Pane + List + Canvas）
- 单页面直达：选 PDF → 立即出列表与图；无 Steps
- 左列表：自然序、搜索、虚拟滚动、计数
- 验收：仅上传一份 PDF 即可完整使用；443 个位号可搜索可点击

**T5 — 定位交互**
- 点击/键盘 → 平滑动画居中 + 缩放 + 高亮 + 文字标签
- 图 → 列表反向联动并滚动可见
- 同名多命中循环定位与 `n/m` 指示
- 验收：交互测试覆盖「点击定位」「反向选中」「多命中循环」「键盘上下联动」

**T6 — 可选 BOM 叠加（不作门禁）**
- 可选择一份成品 BOM；选了才出现 `仅 NC / 仅 BOM 缺失` 筛选与颜色标注
- 不选 BOM 时功能完全可用
- 验收：不传 BOM 全流程可用；传 BOM 后筛选与标注正确

**T7 — 注册与导航**
- 后端 `analysis_tools.py` 注册工具 `refdes_viewer`「位号图查看」，归类 SMT
- 前端 `App.tsx` 路由到 `RefdesViewerPane`（不走 `LegacyToolPane` 兜底）
- 验收：侧栏出现入口，点击直达

**T8 — 测试与文档**
- 后端：`tests/test_refdes_viewer.py`，真实 PDF 经 env 变量 opt-in（沿用 `HW_BOM_GOLDEN_PATH` 模式），缺失则跳过；另有合成 PDF 的确定性单测
- 前端：`refdes-viewer.test.tsx`
- 更新 `docs/Insta360_HW_Platform_Guide.md`
- 验收：`pytest` + `vitest` 全绿

---

## 4. 验收总标准

1. **只给一份位号图 PDF**，不给 BOM、不给坐标、不做配准 → 左侧出全部位号，右侧出图。
2. 点任意位号 → 右侧平滑定位、高亮、可读。
3. 图上点标记 → 左侧同步选中并滚动可见。
4. 443 个位号搜索、滚动、点击均流畅（虚拟列表，无卡顿）。
5. 现有 `smt_layout` 五步审查流行为不回归，既有测试全绿。
6. 未触碰版本/签名/OTA/`data/` 与禁改文件。

---

## 5. 不做

- 扫描件 OCR（本期只支持矢量文字 PDF，遇到扫描件明确提示）。
- 坐标文件配准、NC 推断、交付包生成——这些留在现有 `smt_layout` 审查流。
- 多板/拼板对照。
