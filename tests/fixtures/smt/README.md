# SMT Test Fixtures

## Repository fixtures

`synthetic/` contains generated, non-confidential inputs for parser, board-outline,
NC-inference, FAI, API, and UI tests.

`contracts/analysis_run_v2.json` is the shared backend/frontend wire-contract
fixture for schema version 2.

## Local real-sample baseline

The original IAC4 files remain outside the repository. Only hashes, sizes, and
review expectations are recorded in
`contracts/iac4_v05_local_baseline.json`. This prevents company design files
from being copied into Git while still allowing an opt-in local golden test to
detect accidental source selection or count regressions.

Baseline behavior before the v2 workbench refactor:

- Release: `0.5.11`
- Commit: `c62f17d`
- Parsed coordinate placements: `1037`
- Top placements: `450`
- Bottom placements: `587`
- Focused SMT backend gate: `47 passed`

The role expectations in the local baseline are test or review expectations,
not production filename rules. Production classification must use content and
return evidence and an unresolved state when content is insufficient.
