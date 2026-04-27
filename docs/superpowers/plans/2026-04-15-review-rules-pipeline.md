# Review Rules Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把评审意见目录解析为结构化评审规则，并对解析后的图纸执行规则审查，输出新的规则审查报告和整改清单。

**Architecture:** 在 `sparkflow/review.py` 中引入 `load_review_rules()` 和规则执行器，替换旧的 `requirements` 语义；`sparkflow/review_workflow.py` 只消费规则执行结果；`tests/test_review.py` 以脱敏项目夹具作为正式基线校验整条链路。

**Tech Stack:** Python, pytest, ezdxf, 当前 SparkFlow review/audit 流程

---

### Task 1: 切换测试到 review rules 语义

**Files:**
- Modify: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

```python
from sparkflow.review import load_review_rules, review_audit

def test_load_review_rules_extracts_project_rules():
    rules_doc = load_review_rules(review_dir, project_code=fixture["project"]["project_code"])
    assert rules_doc["review_rules"][0]["check_type"] == "drawing_text_presence"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL with `ImportError: cannot import name 'load_review_rules'`

- [ ] **Step 3: Write minimal implementation**

```python
def load_review_rules(review_dir: Path, *, project_code: str | None = None) -> dict[str, Any]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: targeted tests move past import failure

- [ ] **Step 5: Commit**

```bash
git add tests/test_review.py sparkflow/review.py
git commit -m "refactor(review): switch tests to review rules model"
```

### Task 2: 实现评审规则加载与规则执行

**Files:**
- Modify: `sparkflow/review.py`

- [ ] **Step 1: Write the failing test**

```python
def test_review_audit_writes_rule_driven_report():
    report = json.loads(output.review_report_json_path.read_text(encoding="utf-8"))
    assert report["summary"]["review_rule_counts"] == {"passed": 1, "failed": 1, "manual_review": 10}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL because `review_rule_counts` / `review_rule_results` are missing

- [ ] **Step 3: Write minimal implementation**

```python
def _evaluate_review_rule(rule: dict[str, Any], unique_texts: list[str]) -> dict[str, Any]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS for all review tests

- [ ] **Step 5: Commit**

```bash
git add sparkflow/review.py tests/test_review.py
git commit -m "feat(review): execute project review rules against drawing texts"
```

### Task 3: 让整改清单消费 review rule results

**Files:**
- Modify: `sparkflow/review_workflow.py`

- [ ] **Step 1: Write the failing test**

```python
def test_review_pipeline_writes_split_pages_and_rectification_checklist():
    checklist_md = output.rectification_checklist_md_path.read_text(encoding="utf-8")
    assert "需人工复核" in checklist_md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review.py -q`
Expected: FAIL if workflow still depends on `requirements`

- [ ] **Step 3: Write minimal implementation**

```python
def _build_review_issues(review_report: dict[str, Any], manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in review_report.get("review_rule_results") or []:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sparkflow/review_workflow.py tests/test_review.py
git commit -m "refactor(review): build rectification checklist from review rule results"
```

### Task 4: 更新文档并跑回归

**Files:**
- Modify: `readme.md`
- Modify: `docs/review-pipeline.md`
- Modify: `tests/fixtures/review_baseline/030451DY26030001/README.md`

- [ ] **Step 1: Write the failing test**

```python
def test_review_baseline_fixture_exists():
    fixture = _load_review_fixture()
    assert fixture["source"]["type"] == "real_project_sanitized"
```

- [ ] **Step 2: Run targeted and regression tests**

Run: `python -m pytest tests/test_review.py tests/test_main_cli.py tests/test_audit.py -q`
Expected: PASS

- [ ] **Step 3: Update docs**

```markdown
- review rules are generated from the review directory
- report uses review_rules.json / review_rule_results
```

- [ ] **Step 4: Run broader verification**

Run: `python -m pytest tests/test_main_cli.py tests/test_review.py tests/test_audit.py tests/test_model_build_options.py tests/test_ruleset_loading.py tests/test_wire_classifier.py tests/test_symbol_recognition.py tests/test_symbol_recognition_labels.py tests/test_dataset_report.py tests/test_rectification_checklist.py tests/test_drawing_selection.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add readme.md docs/review-pipeline.md tests/fixtures/review_baseline/030451DY26030001/README.md
git commit -m "docs(review): describe review rules pipeline"
```
