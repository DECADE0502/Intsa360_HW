# 修复方案：BOM 处理模块 4 项问题

给 codex 的实施说明。范围严格限定在下面列出的文件和函数，不要顺带重构、不要改动未提及的逻辑。每一项都包含：问题复现方式、具体改动、验收测试。改完请自行跑一遍对应测试文件确认通过，再跑一次 `pytest tests/ -q` 确认没有引入新的失败。

---

## 问题 1（最高优先级）：BOM 冲突合并把不同阻值/容值误判为"截断"而静默合并

### 文件与函数

`app/backend/tools/bom_process.py`，函数 `_conflict_recommendation`（第 236-316 行左右，具体看 `dominant` 判定这一段，约第 282-309 行）。

### 复现方式

```python
from app.backend.tools.bom_process import _conflict_recommendation

variants = [
    {"name": "CAP", "model": "100",  "desc": "0402 X7R 50V", "grade": "A", "unit": "PCS", "count": 1},
    {"name": "CAP", "model": "1000", "desc": "0402 X7R 50V", "grade": "A", "unit": "PCS", "count": 1},
]
print(_conflict_recommendation(variants))
# 当前输出：{'confidence': 'high', 'reason': 'truncation_prefix_completion',
#            'high_confidence': True, 'manual_choice_required': False,
#            'recommended_index': 1, ...}
```

100pF 和 1000pF 是两个完全不同的电容值（差 10 倍），不是同一个值被截断显示。当前代码把这个场景判定为"高置信度、无需人工确认"，会在 `build_records(merge_conflicts=True)` 流程里把两个位号的型号都静默改写成 1000。如果源 BOM 表里因为数据录入错误，同一个料号混入了两个真实不同的阻值/容值，这个 bug 会把其中一个"修复"成另一个，生产线会拿到错误规格的物料。

### 根因

现有判定逻辑（第 289-295 行左右）：

```python
for candidate_value, other_value in zip(candidate, other):
    if candidate_value == other_value:
        continue
    if not candidate_value or not other_value or not candidate_value.startswith(other_value):
        dominates_all = False
        break
    has_strict_prefix = True
```

这段代码认为"A 是 B 的字符串前缀"就等价于"A 是 B 被截断后的样子"。这个假设只对**文本型字段**（比如描述文字后面被追加了后缀说明）成立，对**数值型字段**（阻值、容值、封装尺寸等）完全不成立——数值本身天然存在前缀关系（`1`/`10`/`100`/`1000`，`1K`/`1K2`/`1K5`）。

### 改动方案

在 `bom_process.py` 里新增一个辅助函数，判断一个字段值是否"看起来像数值/元件规格值"：

```python
_NUMERIC_VALUE_RE = re.compile(
    r"^\d+(\.\d+)?\s*[kKmMuUnNpPfF]?(\s*[ΩΩ%℃VvAaWwFfHh])?$"
)


def _looks_numeric(value: str) -> bool:
    """判断字段值是否是数值型规格（阻值/容值/电压等），而非普通描述文本。

    数值型字段的前缀关系（如 "100" vs "1000"）不代表截断，代表两个不同的值；
    只有文本型字段（如描述后缀被截断）的前缀关系才可信地代表"同一值被截断"。
    """
    stripped = value.strip()
    if not stripped:
        return False
    return bool(_NUMERIC_VALUE_RE.match(stripped))
```

正则说明：匹配"数字开头，可选小数点，可选单位后缀字母（k/K 千, m/M 毫或兆, u/U 微, n/N 纳, p/P 皮, f/F 法拉）,可选量纲符号"。这个正则不需要做到完美识别所有电子元件规格写法，只需要能拦住"纯数字或数字+常见单位后缀"这一类最容易被误判的情况即可（100、1000、1K、1K2、4.7uF、10nF 这类）。如果值里包含中文字符、多个单词、明显是描述文本（比如"0402 X7R 50V"这种复合描述），该正则不会匹配，会被当作文本型继续走原有的前缀截断判定逻辑，不受影响。

然后修改 dominance 判定循环，在"值不相等且不为空"分支里，如果两个值都被判定为数值型，直接认定它们是不同值（不是截断关系）：

```python
for candidate_value, other_value in zip(candidate, other):
    if candidate_value == other_value:
        continue
    if not candidate_value or not other_value:
        dominates_all = False
        break
    if _looks_numeric(candidate_value) and _looks_numeric(other_value):
        # 两个数值型字段值不相等 => 是两个不同的规格值，不是截断关系。
        dominates_all = False
        break
    if not candidate_value.startswith(other_value):
        dominates_all = False
        break
    has_strict_prefix = True
```

这样改动后，效果是：
- 数值型字段出现前缀关系但值不同 → 不再判定为高置信度截断，会走到函数末尾的 `_fallback_recommendation(..., "conflicting_candidate_values")`，需要人工确认。这是正确的保守行为。
- 文本型字段的截断关系（现有测试覆盖的场景，比如描述文字后缀被截断）完全不受影响，因为文本不会匹配 `_looks_numeric`。

### 需要修改的代码位置

只改 `app/backend/tools/bom_process.py` 里的 `_conflict_recommendation` 函数体和文件顶部新增 `_looks_numeric` 辅助函数 + 正则常量。不要改动 `_fallback_recommendation`、`CONFLICT_FIELDS`、或其他冲突处理相关的函数。

### 验收测试

在 `tests/test_bom_process_conflicts.py` 里补充以下用例（可以另起一个测试方法，命名参考现有风格）：

1. **回归用例（新增，必须失败→修复后通过）**：构造两个变体，`model` 分别是 `"100"` 和 `"1000"`，其余 `CONFLICT_FIELDS`（`name`、`desc`、`grade`、`unit`）完全相同。断言 `_conflict_recommendation` 返回的 `reason` 不是 `"truncation_prefix_completion"`，而是 `"conflicting_candidate_values"`，且 `manual_choice_required` 为 `True`（或 fallback 逻辑里对应"需要人工确认"的字段，请先看一下 `_fallback_recommendation` 的返回结构确认字段名）。

2. **同类场景补充**：`model` 分别是 `"1K"` 和 `"1K2"`，同样断言不会被判定为高置信度截断。

3. **现有能力不能回退（回归保护）**：跑一遍现有测试文件里已经存在的 `truncation_prefix_completion` 相关用例（比如文本描述截断场景，如 `"10K电阻 0402 5%"` vs `"10K电阻 0402 5% RoHS环保"`），确认它们仍然被正确识别为高置信度截断——这一步是为了确保新增的数值型判断没有误伤原有的文本截断识别能力。如果现有测试文件里没有这类用例，直接手动跑一次 `_conflict_recommendation` 确认行为不变即可，不强制新增。

---

## 问题 2（最高优先级）：Excel 合并单元格导致料号被读成空值，整行被误判为"未使用"

### 文件与函数

两处需要修复，因为项目里有两套几乎重复的 BOM 行读取实现：

1. `app/backend/tools/bom_process.py`，函数 `load_source`（约第 139-163 行），内部调用 `_cell`（约第 95-97 行）读取单元格。
2. `app/backend/parsers/bom_excel.py`，函数 `read_bom_rows`（约第 97-128 行左右），直接用 `ws.cell(row, col).value`。

（注：`app/backend/tools/common.py` 里还有一个几乎一样的 `_read_bom_rows` 函数，是否也受影响需要一并检查，见下方"需要一并检查"小节。）

### 复现方式

用 openpyxl 构造一个测试文件：在料号列，把连续两行（比如第 2、3 行）合并成一个单元格，写入值 `"P1"`。用 `load_source` 或 `read_bom_rows` 读取，会发现：
- 第 2 行（合并区域左上角）正常读出 `part_number = "P1"`。
- 第 3 行读出 `part_number = ""`（空），触发 `exclusion_reason` 判定为"子项编码为空"，被排除进 NC 汇总——即这一行的元件会被当成"未使用/不需要贴装"处理，实际上它是需要贴装的，只是因为表格视觉排版用了合并单元格。

### 根因

openpyxl 打开 workbook 后，对于一个合并单元格区域（比如 `B2:B3`），只有左上角单元格（`B2`）保有实际值，区域内其他单元格（`B3`）的 `.value` 是 `None`。代码直接把这个 `None` 当作"这一行真的没有填料号"，而不是"这一行的料号被合并单元格覆盖，需要从左上角继承"。

### 改动方案

在 `app/backend/parsers/_workbook.py` 里新增一个共享工具函数，负责构建"合并单元格坐标 → 锚点值"的查找表，两个读取函数都调用它：

```python
def build_merged_cell_lookup(worksheet: object) -> dict[tuple[int, int], object]:
    """返回一个字典：{(row, col): 锚点单元格的值}，覆盖 worksheet 中所有合并单元格区域内
    "非左上角"的坐标。用于在逐格读取时，把合并单元格视觉上共享的值正确地传播到区域内每一行/列，
    而不是把它们当作真的空值处理。

    注意：不修改 worksheet 本身（不调用 unmerge_cells），只返回一个只读的坐标映射表，
    调用方在读取某个单元格值时，如果该坐标在这个映射表里，就用映射表里的值代替
    ws.cell(...).value 本身返回的 None。
    """
    lookup: dict[tuple[int, int], object] = {}
    for merged_range in worksheet.merged_cells.ranges:
        anchor_value = worksheet.cell(merged_range.min_row, merged_range.min_col).value
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                if (row, col) == (merged_range.min_row, merged_range.min_col):
                    continue
                lookup[(row, col)] = anchor_value
    return lookup
```

**在 `bom_process.py` 里的改动**：

1. 在 `load_source` 函数里，打开 workbook 后（`with open_bom_workbook(...) as wb:` 之后，拿到 `ws` 之后），调用一次 `merged_lookup = build_merged_cell_lookup(ws)`。
2. 修改 `_cell` 函数签名，让它接收这个查找表并优先使用：

```python
def _cell(ws, row: int, mapping: dict[str, int], key: str, merged_lookup: dict[tuple[int, int], object] | None = None) -> str:
    col = mapping.get(key)
    if not col:
        return ""
    raw_value = ws.cell(row, col).value
    if raw_value is None and merged_lookup is not None:
        raw_value = merged_lookup.get((row, col))
    return str(raw_value or "").strip()
```

3. `load_source` 里调用 `_cell` 的地方（约第 143 行 `row = {key: _cell(ws, row_num, mapping, key) for key in SRC_ALIASES}`）改成传入 `merged_lookup`：`_cell(ws, row_num, mapping, key, merged_lookup)`。

**在 `bom_excel.py` 里的改动**：

在 `read_bom_rows` 函数里，打开 workbook 拿到 `ws` 之后调用 `merged_lookup = build_merged_cell_lookup(ws)`，然后把所有 `ws.cell(row, mapping[...]).value` 的读取模式，改成先读原值、如果是 `None` 就查 `merged_lookup.get((row, mapping[...]))`。因为这个函数里有多处重复这个模式（`reference`、`part_number`、`model`、`grade`、`description`、`quantity`、`name`、`package`、`value` 共 9 个字段），建议写一个局部小函数简化：

```python
def _resolve_cell(row: int, col: int) -> object:
    value = ws.cell(row, col).value
    if value is None:
        return merged_lookup.get((row, col))
    return value
```

然后把函数体内 `ws.cell(row, mapping["xxx"]).value` 的写法统一替换成 `_resolve_cell(row, mapping["xxx"])`。

### 需要一并检查

`app/backend/tools/common.py` 里的 `_read_bom_rows` 函数（约第 128-150 行）跟 `bom_excel.py` 的 `read_bom_rows` 几乎是同一份逻辑的重复实现，同样直接用 `ws.cell(row, col).value`，**同样受这个问题影响**。请对它做完全一样的修复（引入 `build_merged_cell_lookup` + `_resolve_cell` 局部函数）。

这三处修复请复用同一个 `build_merged_cell_lookup` 函数（从 `_workbook.py` 导入），不要在三个文件里各写一份。

### 验收测试

在合适的测试文件（`tests/test_bom_excel_parser.py` 或新建一个针对合并单元格的测试类）里，用 openpyxl 构造以下场景并验证：

1. 纵向合并两行的料号列（如 `B2:B3` 合并，值为 `"P1"`），对应行的位号列（`Reference` 列）在第 2、3 行填不同的位号（比如 `R1`、`R2`）。用 `load_source`（或 `read_bom_rows`，看你在哪个调用路径上补测试）解析后，断言：
   - 两行都出现在返回的 `rows` 列表里（不应该被排除）。
   - 两行的 `part_number` 都正确等于 `"P1"`。
2. 同样构造一个横向合并单元格场景（如果代码里有可能横向合并的列，比如"物料名称"横跨两列显示），验证同样能正确继承锚点值。如果业务上不存在横向合并场景，这一条可以跳过，纵向合并（发现问题里描述的场景）是必须覆盖的。
3. **回归保护**：跑一个没有任何合并单元格的普通 BOM 测试文件（用现有测试 fixture），确认解析结果和修复前完全一致——这一步验证 `merged_lookup` 为空查找表时不会影响任何正常解析路径。

---

## 问题 3（中等优先级）：数量=位号数风险检查对小数类型系统性误报

### 文件与函数

`app/backend/tools/bom_rules.py`，函数 `evaluate_bom_risks`（第 108-109 行附近，"数量=位号数"这条检查）。

### 复现方式

```python
from app.backend.tools.bom_rules import evaluate_bom_risks

rows = [{"part_number": "P1", "quantity": 3.0, "refs": ["R1", "R2", "R3"]}]
result = evaluate_bom_risks(rows)
# 结果里 "数量=位号数" 这条的 status 是 "warn"，尽管数量3与位号数3完全一致
```

### 根因

第 108 行：

```python
quantity_mismatches = [row for row in rows if (row.get("refs") or []) and str(row.get("quantity")).strip() not in ("", str(len(row["refs"])))]
```

`openpyxl` 读取数字类型单元格时默认返回 Python `float`（比如 `3.0`），`str(3.0)` 是 `"3.0"`，而 `str(len(refs))` 在位号数为 3 时是 `"3"`。两者永远不相等，导致几乎所有"数量列是数字格式"的正常行都会被误判为不符。

### 改动方案

`app/backend/tools/common.py` 里已经有一个正确处理这个问题的函数 `_to_qty`（第 120-124 行）：

```python
def _to_qty(value: object) -> int:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0
```

在 `bom_rules.py` 顶部导入这个函数（`from app.backend.tools.common import _to_qty`），然后把第 108 行的比较逻辑改成数值比较，同时保留"数量为空不算不符"的原有语义：

```python
def _quantity_mismatch(row: dict[str, object]) -> bool:
    raw_quantity = row.get("quantity")
    if raw_quantity is None or str(raw_quantity).strip() == "":
        return False
    return _to_qty(raw_quantity) != len(row["refs"])


quantity_mismatches = [row for row in rows if (row.get("refs") or []) and _quantity_mismatch(row)]
```

注意：`_to_qty` 对无法解析的值（比如空字符串或非数字文本）会返回 `0`，如果直接拿 `_to_qty(raw_quantity) != len(refs)` 来判断、不做空值短路，会导致"数量列本来就是空的"这种情况被误判为"数量0≠位号数"从而报警——这跟原有逻辑"数量为空时不算不符"的语义是矛盾的，所以上面的 `_quantity_mismatch` 函数先显式判断空值直接返回 `False`（不算不符），再进入数值比较。这一点在实施时必须保留，不能省略。

如果 `bom_rules.py` 因为循环引用或模块依赖顺序问题无法直接从 `common.py` 导入 `_to_qty`（先检查一下两个模块之间是否已经存在引用关系，或者是否会造成循环 import），退而求其次的方案是在 `bom_rules.py` 内部直接复制一份等价的转换逻辑（不导入，直接内联实现同样的 `int(float(str(value).strip()))` 转换 + 异常兜底），但优先尝试直接复用 `common.py` 的实现，避免同一逻辑维护两份。

### 验收测试

在 `tests/test_bom_risk_checks.py` 里补充：

1. **回归用例（新增，必须失败→修复后通过）**：`quantity=3.0`（float），`refs=["R1","R2","R3"]`（3个位号），断言"数量=位号数"这条检查的 `status` 是 `"ok"`，不是 `"warn"`。
2. **确保真实不符仍能检出**：`quantity=3.0`，`refs=["R1","R2"]`（2个位号，真的不符），断言 `status` 仍然是 `"warn"`。
3. **空数量语义不变**：`quantity=None` 或 `quantity=""`，`refs=["R1","R2","R3"]`，断言不触发警告（保持原有"数量为空不算不符"的语义）。
4. **整数类型不受影响**：`quantity=3`（int，不是 float），`refs` 3个位号，断言 `status` 是 `"ok"`（这条是防止修复引入新的回归）。

---

## 问题 4（低优先级，顺手修）：subprocess 调用缺少编码防护，中文环境下可能崩溃

### 背景

Windows 中文系统环境下，PowerShell 子进程输出的文本编码可能是系统代码页（GBK/936）而不是 UTF-8。Python 的 `subprocess.run(..., text=True, encoding="utf-8")` 如果不加 `errors="replace"`，遇到无法用 UTF-8 解码的字节会在后台读取线程里抛 `UnicodeDecodeError`，这个异常会被吞掉变成一个警告，但会导致 `stdout`/`stderr` 变成 `None`，后续任何对它们做字符串操作（拼接、`.strip()`）都会连带出错。

### 文件与具体行号

1. `app/backend/update_api.py` 第 235-241 行左右（`run_uninstall` 函数里的 `subprocess.run` 调用）。
2. `app/backend/api/cadence.py` 第 35-42 行左右（`redeploy_cadence_loader` 函数里的 `subprocess.run` 调用）。
3. `tests/test_release_identity.py` 第 124-149 行左右（两处 `subprocess.run` 调用，这个是测试代码，目前已确认会真实复现崩溃——运行 `pytest tests/test_release_identity.py -q` 可以直接看到 `TypeError: can only concatenate str (not "NoneType") to str`，报错位置是第 152 行 `dirty.stdout + dirty.stderr`）。

### 改动方案

给上面三处的 `subprocess.run` 调用统一补上两个参数：`encoding="utf-8"` 和 `errors="replace"`（如果调用里已经写了 `encoding="utf-8"` 但没写 `errors`，只需要补 `errors="replace"`）。

参考项目里已经采用这个正确写法的例子：`tests/test_lifecycle_v3_atomic.py` 第 200 行：
```python
subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
```

三处具体改法：

**`app/backend/update_api.py`**（第 235 行附近）：
```python
completed = subprocess.run(
    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-InstallDir", str(root)],
    cwd=str(root),
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=90,
)
```

**`app/backend/api/cadence.py`**（第 35 行附近）：
```python
completed = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
    cwd=str(root),
    text=True,
    capture_output=True,
    encoding="utf-8",
    errors="replace",
    timeout=30,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
```

**`tests/test_release_identity.py`**（第 124-149 行附近，两处 `subprocess.run` 调用都要改，它们已经有 `encoding="utf-8"`，只需要各加一行 `errors="replace"`）。

### 验收测试

这一项本身就是测试修复，不需要新增测试用例：
- `tests/test_release_identity.py` 修完后，直接运行 `pytest tests/test_release_identity.py -q`，之前失败的 `test_public_build_preflight_rejects_dirty_and_duplicate_identities_before_packaging` 应该变成通过。
- `update_api.py` 和 `cadence.py` 的改动不需要新增测试（这两个函数目前调用的脚本是纯 ASCII 输出，暂时不会触发这个问题，属于防御性修复），但改完后跑一次 `pytest tests/test_update_api.py tests/test_cadence_integration.py -q`（或项目里对应这两个模块的现有测试文件）确认没有破坏原有行为即可。

---

## 实施后的整体验收

四项改完后，请完整运行一次：

```
pytest tests/ -q
```

确认：
1. 之前唯一失败的 `test_release_identity.py` 用例转为通过。
2. 新增的所有用例（问题 1、2、3 各自新增的测试）全部通过。
3. 总通过数应该等于"修复前通过数 + 本次新增用例数"，不应该有任何原有测试从通过变成失败——如果有,说明某个改动的边界条件处理有问题（最可能出问题的地方是问题 2 的合并单元格查找表在"没有合并单元格"的普通文件上是否真的不影响任何现有解析结果，以及问题 3 的空值短路语义是否保留），需要回头检查对应的改动是否严格按照上面的方案实现，不要绕过验收测试直接标记完成。
