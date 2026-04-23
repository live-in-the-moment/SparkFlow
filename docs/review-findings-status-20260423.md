# 审查问题状态说明（2026-04-23）

本文基于以下 6 条审查结果整理当前状态，并核对当前工作区代码是否已经修复：

1. `sparkflow/rules/project_rules.py:111-114`
   `distribution_transformer` 计数把所有 `device_type == "transformer"` 都算成台变
2. `sparkflow/rules/project_rules.py:129-130`
   只要识别到部分设备块，就丢弃纯文本命中的同类设备计数
3. `sparkflow/project_docs.py:167-168`
   `project_document_mentions()` 把数量为 `0` 的对象也视为“项目中提到/需要”
4. `sparkflow/model/build_options.py:66-70`
   当 `catalog/` 目录不可用时，内置设备模板退化为空
5. `sparkflow/project_docs.py:167-168`
   与第 3 条重复，本质仍是“数量为 `0` 仍被当作需要检查”
6. `sparkflow/review_workflow.py:957-963`
   `page_label` 优先使用 `page_seq`，导致常规图纸不再优先显示图签页码 `sheet_no`

## 结论

- 当前检查结果：上述问题 **均未修复**
- 补充说明：第 `3` 条和第 `5` 条是同一个缺陷的重复表述，因此按唯一问题口径应视为 `5` 个待修项

## 逐项状态

| 编号 | 状态 | 结论 | 当前证据 |
| --- | --- | --- | --- |
| 1 | 未修复 | 仍会把 `transformer` 类型设备整体计入台变数量 | `sparkflow/rules/project_rules.py:111-114` 仍然直接判断 `device.device_type == "transformer"` |
| 2 | 未修复 | 仍然在存在 `device_matches` 时忽略 `text_matches` | `sparkflow/rules/project_rules.py:129-130` 仍然是 `if device_matches: return len(device_matches)` |
| 3 | 未修复 | 数量为 `0` 仍会被认定为“项目中提到” | `sparkflow/project_docs.py:167-168` 仍然只判断 `key in context.expected_counts` |
| 4 | 未修复 | 缺少 `catalog/` 时仍返回空模板集合 | `sparkflow/model/build_options.py:66-70` 仍然在无 catalog 时 `return ()` |
| 5 | 未修复 | 与第 3 条重复，当前仍未处理 | 同第 3 条 |
| 6 | 未修复 | `page_label` 仍优先显示 `page_seq` 而不是 `sheet_no` | `sparkflow/review_workflow.py:957-963` 仍先读 `page_seq`，命中后直接返回 |

## 详细说明

### 1. 台变计数会把电流互感器一起算进去

当前实现：

- 文件：`sparkflow/rules/project_rules.py`
- 位置：`111-114`

现状：

- `distribution_transformer` 规则仍然先把所有 `device_type == "transformer"` 的设备加入 `device_matches`
- 但当前模板体系里，`transformer` 并不只表示台变，也覆盖了 `电流互感器`

影响：

- 带 `TA` / `电流互感器` 的一次系统图，可能在台变数量规则上误报

状态判断：

- **未修复**

### 2. 混合“块识别 + 纯文本”场景仍会少算数量

当前实现：

- 文件：`sparkflow/rules/project_rules.py`
- 位置：`129-130`

现状：

- 只要 `device_matches` 非空，就直接返回设备数量
- 这会丢弃同一对象在文本中出现、但未被识别成 `Device` 的那部分数量

影响：

- 图纸里一部分对象来自块识别、另一部分只以文本出现时，`project.*.count_mismatch` 仍可能误报

状态判断：

- **未修复**

### 3 / 5. 数量为 0 的对象仍被视为“项目需要检查”

当前实现：

- 文件：`sparkflow/project_docs.py`
- 位置：`167-168`

现状：

- `project_document_mentions()` 只要发现 `key` 存在于 `expected_counts`，就返回 `True`
- 没有区分这个对象的数量是 `0` 还是 `> 0`

影响：

- `project.measurement_comm_unit.missing_presence`
- `project.secondary_cabinet.missing_quantity_note`

在附件里数量明确为 `0` 时，仍可能错误触发

状态判断：

- **未修复**

补充说明：

- 第 `5` 条只是对第 `3` 条的另一种描述
- 建议后续修复和跟踪时将二者合并处理

### 4. 缺失 catalog 时仍没有后备内置模板

当前实现：

- 文件：`sparkflow/model/build_options.py`
- 位置：`66-70`

现状：

- `builtin_device_templates()` 现在完全依赖 `load_catalog_model_build_options()`
- 若 `catalog/` 不存在或未随运行环境一起分发，就直接返回空元组

影响：

- 设备模板和端子模板都可能为空
- 设备识别会显著退化，进一步影响规则执行结果

状态判断：

- **未修复**

### 6. 整改单页标签仍优先展示 page_seq

当前实现：

- 文件：`sparkflow/review_workflow.py`
- 位置：`957-963`

现状：

- `_page_index_label()` 先取 `page_seq`
- 只有没有 `page_seq` 时才退回 `sheet_no`
- 但当前 manifest 中普通页面普遍都有 `page_seq`

影响：

- 生成的 `page_label`
- 评审规则关联页面标签

会优先显示扫描顺序，而不是图签页号，降低与原图对照时的可读性

状态判断：

- **未修复**

## 建议修复顺序

建议按以下优先级处理：

1. 先修第 `1` 条和第 `2` 条
   这两条直接影响新引入的项目附件数量规则准确性
2. 再修第 `3/5` 条
   这能消除数量为 `0` 时的误报
3. 然后修第 `4` 条
   这是安装/分发场景下的稳定性问题
4. 最后修第 `6` 条
   主要影响整改清单与原图页号的映射体验

## 当前结论摘要

截至当前工作区代码状态：

- `6/6` 条审查意见对应的问题都还存在
- 去重后是 `5` 个唯一问题
- 目前没有证据表明这些问题已在当前未提交修改中被修复
