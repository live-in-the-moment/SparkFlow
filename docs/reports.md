# 报告与整改清单说明

## 1. 单图报告

每张进入电气审图的图纸都会输出：

- `report.json`
- `report.md`
- `report.docx`

主要内容：

- 审图时间
- 输入路径
- 规则版本
- `passed`
- 问题清单
- 条文映射
- 整改建议
- 风险等级
- 置信度

## 2. 数据集汇总

`audit-dataset` 会直接生成：

- `dataset_selection.json`
- `dataset_summary.json`
- `dataset_summary.md`

用于回答：

- 哪些图进入审图
- 哪些图被筛掉
- 哪些图失败/通过/未处理
- 问题数量按规则如何分布

## 3. 数据集最终总报告

命令：

```powershell
python -X utf8 -m sparkflow dataset-report <run_dir> --ruleset <ruleset_dir>
```

输出：

- `final_audit_report.md`
- `final_audit_report.docx`

适合：

- 项目级汇报
- 数据集归档
- 给非开发同事查看总体结果

## 4. 整改清单

命令：

```powershell
python -X utf8 -m sparkflow rectification-checklist <run_dir>
```

输出：

- `rectification_checklist.md`
- `rectification_checklist.docx`
- `rectification_checklist.json`

特点：

- 只纳入失败图纸
- 逐问题展开
- 带坐标
- 带整改建议
- 带单图报告回链

## 5. 严格审图示例

对国家电网 `配电部分CAD` 的严格跑批结果示例：

- [final_audit_report.md](../out_stategrid_peidian_audit/20260325T100443Z/final_audit_report.md)
- [rectification_checklist.md](../out_stategrid_peidian_audit/20260325T100443Z/rectification_checklist.md)

## 6. 中文编码建议

历史上最容易出问题的是“数据集级临时总报告”。

建议：

- 所有 Markdown 一律 `UTF-8`
- 统一通过仓库命令生成总报告和整改清单
- Windows 上优先 `python -X utf8`
- 不要用 PowerShell 内联脚本直接拼大段中文报告文本

## 7. 推荐查看顺序

### 面向研发

1. `dataset_summary.json`
2. `dataset_selection.json`
3. 单图 `report.json`
4. `final_audit_report.md`
5. `rectification_checklist.json`

### 面向项目/交付

1. `final_audit_report.docx`
2. `rectification_checklist.docx`
3. 必要时附各单图 `report.docx`
