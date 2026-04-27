# Review Rules Design

**Date:** 2026-04-15

## Goal

把当前“评审意见目录 -> requirements 关键词闭环”的实现，重构为“评审意见目录 -> 结构化评审规则 -> 对解析后的图纸执行规则审查”。

## Current Problem

- `sparkflow/review.py` 当前输出的是 `requirements`，本质是把技术意见和造价意见拆句后，用关键词去图纸文本里查命中。
- `review_report.json` 的语义是 `evidence_found / not_found_in_drawing / manual_required`，更像复核记录，不是规则执行结果。
- `review_workflow.py` 与 `tests/test_review.py` 都依赖这套旧语义，导致“评审意见”与“评审规则”混在一起。

## Target Architecture

### 1. 输入

- `DWG / DXF`
- `评审意见目录`

### 2. 中间产物

- `drawing_info.json`
- `review_rules.json`

### 3. 核心流程

1. 从 `评审意见目录` 读取项目行和专家意见。
2. 把技术/造价意见拆解成结构化 `review_rules`。
3. 对解析后的图纸文本执行每条规则。
4. 输出规则执行结果和整改问题清单。

## Data Model

### review_rules.json

包含：

- `project_code`
- `project_name`
- `review_dir`
- `source_files`
- `project_summary`
- `major_issues`
- `review_rules`

每条 `review_rule` 包含：

- `rule_id`
- `source_type`
- `item_no`
- `source_text`
- `reply`
- `scope`
- `check_type`
- `keywords`

### review_report.json

包含：

- `summary.review_rule_counts`
- `review_rule_results`

每条 `review_rule_result` 包含：

- 规则元数据
- `result`
- `matches`
- `explanation`

结果值统一为：

- `passed`
- `failed`
- `manual_review`

## Rule Execution Strategy

### drawing_text_presence

- 适用：需要在图纸文本中找到证据的规则
- 规则：从 `keywords` 中查找图纸文本命中
- 判定：
  - 找到匹配：`passed`
  - 没找到：`failed`

### manual_review

- 适用：依赖说明书、预算书、附件、物探报告等非图纸资料
- 判定：统一 `manual_review`

## Compatibility Decision

- 不再把 `requirements` 作为主输出。
- 主输出统一切换为 `review_rules` / `review_rule_results`。
- `review_workflow.py` 的整改问题清单改为基于 `review_rule_results` 汇总。

## Testing Strategy

- `tests/test_review.py` 使用脱敏夹具生成临时 `评审意见` 与 `DXF`
- 基线断言覆盖：
  - `load_review_rules()`
  - `review_audit()`
  - `review_pipeline()`
  - `review-pipeline` CLI
- 规则结果基线：
  - `passed = 1`
  - `failed = 1`
  - `manual_review = 10`
