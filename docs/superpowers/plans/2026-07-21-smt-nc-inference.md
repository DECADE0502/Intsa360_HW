# SMT NC Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SMT visualization derive NC components from design references minus the processed PLM/OA BOM, with evidence levels for confirmed NC, candidate NC, and unverified XY-only references.

**Architecture:** Keep file parsing in `smt_layout.py`, but isolate set classification in a pure `_infer_nc_evidence` helper. The backend response carries the evidence groups; the existing React pane and PCB canvas render those groups without requiring an uploaded companion NC workbook.

**Tech Stack:** Python 3, FastAPI/Pydantic, pytest, React 18, TypeScript, Ant Design, CSS modules, Vite.

---

### Task 1: Pure NC evidence inference

**Files:**
- Create: `tests/test_smt_layout_inference.py`
- Modify: `app/backend/tools/smt_layout.py`

- [ ] **Step 1: Write failing set-classification tests**

```python
from app.backend.tools.smt_layout import _infer_nc_evidence


def test_with_netlist_separates_confirmed_nc_from_xy_only_anomaly():
    evidence = _infer_nc_evidence(
        xy_refs={"R1", "R2", "R3"},
        bom_refs={"R1"},
        netlist_refs={"R1", "R2"},
        explicit_nc_refs=set(),
        explicit_summary_used=False,
    )
    assert evidence.confirmed_refs == {"R2"}
    assert evidence.candidate_refs == set()
    assert evidence.unverified_refs == {"R3"}


def test_without_netlist_treats_xy_minus_bom_as_candidate_nc():
    evidence = _infer_nc_evidence(
        xy_refs={"R1", "R2"},
        bom_refs={"R1"},
        netlist_refs=None,
        explicit_nc_refs=set(),
        explicit_summary_used=False,
    )
    assert evidence.candidate_refs == {"R2"}
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_smt_layout_inference.py -q`

Expected: FAIL because `_infer_nc_evidence` does not exist.

- [ ] **Step 3: Add the pure evidence model**

```python
@dataclass(frozen=True)
class NcEvidence:
    confirmed_refs: set[str]
    candidate_refs: set[str]
    unverified_refs: set[str]
    conflict_refs: set[str]
    inference_mode: str
    explicit_summary_used: bool


def _infer_nc_evidence(*, xy_refs, bom_refs, netlist_refs, explicit_nc_refs, explicit_summary_used):
    explicit = set(explicit_nc_refs)
    missing_from_bom = set(xy_refs) - set(bom_refs)
    conflicts = explicit & set(bom_refs)
    if netlist_refs is None:
        confirmed = missing_from_bom & explicit
        return NcEvidence(
            confirmed,
            missing_from_bom - explicit,
            set(),
            conflicts,
            "without_netlist",
            explicit_summary_used,
        )
    confirmed = missing_from_bom & (set(netlist_refs) | explicit)
    return NcEvidence(
        confirmed,
        set(),
        missing_from_bom - set(netlist_refs) - explicit,
        conflicts,
        "with_netlist",
        explicit_summary_used,
    )
```

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_smt_layout_inference.py -q`

Expected: PASS.

### Task 2: Use inferred evidence in components, sanity, and FAI output

**Files:**
- Modify: `tests/test_smt_layout.py`
- Modify: `tests/test_smt_layout_sanity.py`
- Modify: `tests/test_smt_layout_fai.py`
- Modify: `app/backend/tools/smt_layout.py`

- [ ] **Step 1: Add failing behavior tests**

Add these concrete assertions to isolated-BOM and explicit-conflict test cases:

```python
assert result["nc_summary"]["candidate_refs"] == ["R2"]
assert status_by_ref["R2"] == "candidate_nc"
assert "R2" not in {item["ref"] for item in sanity["missing_bom"]}
assert fai_rows["R2"][5] == "候选 NC，需确认"
assert conflict_result["components"][0]["status"] == "installed"
assert conflict_result["nc_summary"]["conflict_refs"] == ["R1"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_smt_layout.py tests/test_smt_layout_sanity.py tests/test_smt_layout_fai.py -q`

Expected: FAIL on missing evidence fields/statuses and old FAI text.

- [ ] **Step 3: Load explicit NC rows as supplemental metadata**

Change `_bom_by_ref` to return final-BOM rows plus explicit-NC rows keyed by normalized reference. Final-BOM membership remains authoritative; an explicit row is only used to populate description/model for a non-installed component.

- [ ] **Step 4: Assign evidence-driven component status**

Use this precedence:

```python
if ref in bom_by_ref:
    status = "installed"
elif ref in evidence.confirmed_refs:
    status = "nc"
elif ref in evidence.candidate_refs:
    status = "candidate_nc"
else:
    status = "unverified"
```

- [ ] **Step 5: Remove confirmed NC from false BOM-missing alarms**

In `_compute_sanity`, derive confirmed NC from component status and exclude it from `missing_bom`. Keep `unverified` XY-only references as high-severity anomalies.

- [ ] **Step 6: Write explicit FAI wording**

Map statuses to:

```python
{
    "nc": ("NC，不贴装", "网表/NC 证据确认"),
    "candidate_nc": ("候选 NC，需确认", "按 XY - 成品 BOM 推导"),
    "unverified": ("⚠ XY 独有", "检查 XY、网表与 BOM"),
}
```

- [ ] **Step 7: Verify GREEN**

Run: `python -m pytest tests/test_smt_layout.py tests/test_smt_layout_sanity.py tests/test_smt_layout_fai.py -q`

Expected: PASS.

### Task 3: Expand and validate the API contract

**Files:**
- Modify: `app/backend/contracts/api.py`
- Modify: `tests/test_smt_layout_contract.py`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Write failing contract assertions**

Change one component status to `candidate_nc`, then replace the summary fixture with:

```python
"nc_summary": {
    "total": 1,
    "refs": ["R2"],
    "confirmed_refs": [],
    "candidate_refs": ["R2"],
    "unverified_refs": ["R3"],
    "conflict_refs": [],
    "inference_mode": "without_netlist",
    "explicit_summary_used": False,
}
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_smt_layout_contract.py -q`

Expected: FAIL because current literals and summary schema reject the new fields.

- [ ] **Step 3: Update Pydantic and TypeScript types**

Add `candidate_nc` and `unverified` status literals and define all evidence fields with matching names and `with_netlist | without_netlist` values.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_smt_layout_contract.py -q`

Expected: PASS.

### Task 4: Present evidence levels in the SMT UI

**Files:**
- Modify: `frontend/src/tools/SmtLayoutPane.tsx`
- Modify: `frontend/src/components/PcbCanvas.tsx`
- Modify: `frontend/src/components/PcbCanvas.module.css`
- Modify: `frontend/src/components/RefdesVirtualList.tsx`
- Modify: `tests/test_frontend_build.py`

- [ ] **Step 1: Add failing source-level UI assertions**

Assert the pane contains `确定 NC`, `候选 NC`, `待确认`, `网表已交叉验证`, and `可导入 PLM/OA 的成品 BOM（不含 NC）`, and that the canvas maps `candidate_nc` and `unverified` to dedicated CSS classes.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_frontend_build.py -q`

Expected: FAIL because the labels and mappings do not exist.

- [ ] **Step 3: Add status filtering and evidence summary**

The default list includes `nc` and `candidate_nc`. A segmented control exposes confirmed, candidate, unverified, and all groups. Show counts from `nc_summary` and a warning when `conflict_refs` or `unverified_refs` is non-empty.

- [ ] **Step 4: Add stable PCB colors and row labels**

Use red for confirmed NC, amber for candidate NC, and blue for unverified. Add an optional status label to `RefdesListItem` so each row states its evidence level without changing list height.

- [ ] **Step 5: Verify GREEN and compile types**

Run: `python -m pytest tests/test_frontend_build.py -q`

Run: `npm run build --prefix frontend`

Expected: both commands PASS.

### Task 5: End-to-end regression and fixture correction

**Files:**
- Modify: `tests/fixtures/smt/synthetic/build_fixture.py`
- Modify: `tests/fixtures/smt/synthetic/bom_processed/PLM.xlsx`
- Modify: `tests/test_smt_layout_e2e.py`
- Modify: `docs/Insta360_HW_Platform_Guide.md`

- [ ] **Step 1: Make the synthetic processed BOM match production semantics**

Generate PLM fixture refs as all XY refs except `R8` and `C5`, plus BOM-only `R99`. Keep the explicit NC summary containing `R8` and `C5`.

- [ ] **Step 2: Add an isolated-upload E2E test**

Copy only `PLM.xlsx` into a temporary upload directory and assert:

```python
assert payload["nc_summary"]["confirmed_refs"] == ["C5", "R8"]
assert payload["nc_summary"]["explicit_summary_used"] is False
assert payload["nc_summary"]["unverified_refs"] == ["TP1"]
```

The netlist fixture omits `TP1`, so it must remain unverified rather than becoming confirmed NC.

- [ ] **Step 3: Verify the E2E test fails, regenerate the fixture, then pass**

Run: `python -m pytest tests/test_smt_layout_e2e.py -q`

Run: `python tests/fixtures/smt/synthetic/build_fixture.py`

Run: `python -m pytest tests/test_smt_layout_e2e.py -q`

Expected: first run FAIL before implementation/fixture regeneration; final run PASS.

- [ ] **Step 4: Update the hardware-engineer guide**

Replace the SMT input description with: `选择 BOM 处理生成、可直接导入 PLM/OA 的成品 BOM。平台以 XY 总位号减去该 BOM 位号推导不贴器件；提供 pstxprt.dat 后会进一步区分确定 NC 与数据异常。`

- [ ] **Step 5: Run focused and full verification**

Run: `python -m pytest tests/test_smt_layout*.py tests/test_frontend_build.py -q`

Run: `python -m pytest -q`

Run: `npm run build --prefix frontend`

Expected: all tests and the production build PASS without warnings introduced by this change.
