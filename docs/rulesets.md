# 规则集与规则输入

## 1. 规则集目录

规则集位于 [`rulesets/`](../rulesets)：

- [`example`](../rulesets/example/ruleset.json)
- [`example_table`](../rulesets/example_table/ruleset.json)
- [`example_xlsx`](../rulesets/example_xlsx/ruleset.json)
- [`example_normative`](../rulesets/example_normative/ruleset.json)
- [`stategrid_peidian_strict`](../rulesets/stategrid_peidian_strict/ruleset.json)

## 2. 支持的输入形式

### 2.1 结构化 JSON

最常用方式。

支持字段：

- `version`
- `model`
- `rules`
- 每条规则可设置：
  - `rule_id`
  - `enabled`
  - `severity`
  - `params`
  - `applies_to`
  - `title`
  - `clause`

### 2.2 表格规则集

支持：

- `CSV`
- `TSV`
- `XLSX`

典型列：

- `rule_id`
- `enabled`
- `severity`
- `params`
- `applies_to`
- `title`
- `clause`

### 2.3 规范摘要

支持结构化 Markdown 摘要。

示例见：

- [`example_normative/normative_summary.md`](../rulesets/example_normative/normative_summary.md)

适合：

- 从规范摘要里提取少量规则配置
- 管理标题、条款号、严重级别等元信息

## 3. 默认规则集与严格规则集

### 3.1 默认规则集

- [`rulesets/example/ruleset.json`](../rulesets/example/ruleset.json)

特点：

- 适合日常跑批
- 一些问题按 `warning` 判定

### 3.2 严格规则集

- [`rulesets/stategrid_peidian_strict/ruleset.json`](../rulesets/stategrid_peidian_strict/ruleset.json)

特点：

- 将 `wire.floating_endpoints` 提升为严格判定
- 适合正式整改或严审场景

## 4. 当前规则能力范围

当前规则更偏：

- 连线闭合
- 设备标注完整性
- 标签重复/格式异常
- 母线/分支箱/开关柜拓扑关系
- 变压器与母线方向关系

还不是完整规范库。

## 5. 规则集差异比较

命令：

```powershell
python -X utf8 -m sparkflow ruleset-diff rulesets\\example rulesets\\stategrid_peidian_strict --out out\\ruleset_diff
```

输出：

- JSON 差异报告
- Markdown 差异报告

当前差异报告会比较：

- `enabled`
- `severity`
- `params`
- `applies_to`
- `title`
- `clause`
- `version`

## 6. 规则集设计建议

- 先用 `example` 跑通，再派生项目专用规则集
- 严格规则不要直接改默认规则集，建议单独建目录
- 如果需要交付性更强的报告，建议补全 `title` 与 `clause`
- 表格/XLSX 适合规则维护，JSON 更适合最终落库
