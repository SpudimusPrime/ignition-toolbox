# Report Language — Spec & Implementation Plan

## Language Specification

### Overview

The `report` block is an optional declaration on any manifest item within a
`perspective.execute_test_manifest` step. When declared, it evaluates a
Playwright selector after the item's action executes and records the outcome
as a named report entry. Items without a `report` block execute silently and
produce no report row.

### Syntax

```yaml
- component_id: es_1_click_state_group_card
  selector: text="{{ parameter.state_group_name }}"
  action: click
  expected: State Group Card Selected        # becomes the report row label
  report:                                    # optional
    selector: "has-text('{{ parameter.state_group_name }}') >> .psc-bubble-selected"  # mandatory
    result: pass                             # mandatory — polarity of selector match
    skip-to: end                             # optional — fires on mismatch
```

### Fields

| Field | Required | Values | Description |
|---|---|---|---|
| `selector` | yes | Playwright selector string | Evaluated against the live page after the action runs |
| `result` | yes | `pass` \| `fail` | Declares what a selector **match** means. `pass` = found is good. `fail` = found is bad (negative/deletion test) |
| `skip-to` | no | `<component_id>` \| `end` \| `abort` | Jump target when actual outcome does not match declared result |

### Result Polarity

`result` defines whether finding the selector is the **expected good outcome**:

| `result` declared | Selector found? | Outcome recorded |
|---|---|---|
| `pass` | yes | PASS (element present as expected) |
| `pass` | no | FAIL (element missing — unexpected) |
| `fail` | yes | FAIL (element present — should be absent) |
| `fail` | no | PASS (element absent as expected — e.g. deletion confirmed) |

### skip-to Trigger

`skip-to` fires **only on mismatch** — when actual outcome ≠ declared `result`.

| `result` | Actual | skip-to fires? |
|---|---|---|
| `pass` | PASS | no |
| `pass` | FAIL | yes |
| `fail` | FAIL | no |
| `fail` | PASS | yes |

### skip-to Targets

- `<component_id>` — jump to a named sibling item in the current manifest
- `end` — stop this manifest; playbook continues to the next step
- `abort` — stop the manifest **and** abort the entire playbook run

### CSV Output (future)

Each `report` entry will produce one CSV row. Columns:
`execution_id`, `playbook`, `step_name`, `component_id`, `label` (from `expected`),
`declared_result`, `actual_result`, `matched`, `skip_to_fired`, `timestamp`

---

## Implementation Plan

### Step 1 — Pydantic models for the report block ✅
**File:** `backend/ignition_toolkit/playbook/models.py`

- [x] Add `ReportBlock` dataclass (`selector`, `result`, `skip_to`)
- [x] Add `ReportEntry` dataclass (runtime result stored in step output)
- Note: manifest items remain dicts; no typed `ManifestItem` needed

### Step 2 — Executor: evaluate report selector and handle skip-to ✅
**File:** `backend/ignition_toolkit/playbook/executors/perspective_executor.py`

- [x] Converted `for` loop to `while` loop with index for jump support
- [x] Report selector evaluated via `page.query_selector` after each action
- [x] Polarity: `matched = selector_found if declared=="pass" else not selector_found`
- [x] `actual_result = "pass" if matched else "fail"`
- [x] `skip-to` handled for `end` (break), `abort` (break + flag), `<component_id>` (jump_index)
- [x] `report_entries` + `abort_requested` / `abort_message` included in return dict
- [x] Supports both `skip-to` (YAML) and `skip_to` (dict) key forms

### Step 3 — Engine: handle abort signal ✅
**File:** `backend/ignition_toolkit/playbook/engine.py`

- [x] Checks `step_result.output.get("abort_requested")` after step completes
- [x] Transitions playbook to `FAILED` with `abort_message` as error

### Step 4 — CSV export endpoint ✅
**File:** `backend/ignition_toolkit/api/routers/executions/main.py`

- [x] `GET /api/executions/{execution_id}/report.csv`
  - Tries active engine first, falls back to database
  - Streams `text/csv` with filename `report_<id[:8]>.csv`
- [x] Route is part of existing executions router (no new file needed)

### Step 5 — Validation & tests ✅
- [x] Unit tests: `backend/tests/test_playbook/test_report.py` (17 tests, all passing)
  - `ReportBlock` / `ReportEntry` model instantiation
  - All 4 polarity combinations
  - All 4 skip-to trigger conditions (parametrized)
  - Executor integration: pass, negative/deletion, skip-to end, skip-to abort, skip-to component_id, no report
- [ ] YAML schema validation (future — enforce `selector`/`result` required when `report` declared)
- [ ] Update `step_delete_state.yaml` with finalized syntax as live example
