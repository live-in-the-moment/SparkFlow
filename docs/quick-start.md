# 快速开始与命令示例

## 0. 当前实测基线

当前仓库优先以这条真实复审链路作为基线：

```powershell
python -X utf8 -m sparkflow review-pipeline `
  "docs\\珠海金湾供电局2026年3月配网业扩配套项目--2项\\评审前\\030451DY26030001-南水供电所景旺电子（厂房一）10kV业扩配套工程\\附件3 施工图\\南水供电所景旺电子（厂房一）10kV业扩配套工程.dwg" `
  --review-dir "docs\\珠海金湾供电局2026年3月配网业扩配套项目--2项\\评审意见" `
  --out "tmp\\review_pipeline_030451DY26030001_docdriven" `
  --project-code 030451DY26030001 `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe" `
  --dxf-backend ascii `
  --skip-sparkflow-audit
```

如果是在 Windows / PowerShell 下反复跑同一项目，优先直接用仓库里的包装脚本，避免反引号续行粘贴导致参数串行：

```powershell
.\scripts\run_review_pipeline.ps1
```

这个脚本默认读取 [scripts/run_review_pipeline.ps1](../scripts/run_review_pipeline.ps1) 顶部的预设变量；常改的只有：

- `$defaultDwg`
- `$defaultReview`
- `$defaultOut`
- `$defaultDwgConverter`

如果只是临时覆盖其中一个参数，也可以这样用：

```powershell
.\scripts\run_review_pipeline.ps1 -Out "tmp\\review_pipeline_cli_override"
```

已验证输出目录：

- `tmp\\review_pipeline_030451DY26030001_docdriven\\20260415T070348Z`

补充验证案例：

- `tmp\\review_pipeline_jiayi_cli_case\\20260422T062918Z`
- 该案例覆盖 `擎能` 模板分页，`split_page_count = 94`
- 当前也已验证 `.\scripts\run_review_pipeline.ps1` 可直接跑通罗定加益项目，输出目录示例：`tmp\\review_pipeline_cli\\20260423T014320Z`

`image/` 下的历史样例数据可以继续用于研究或回归，但不再作为当前主流程说明的默认输入。

## 1. 安装

```powershell
python -m pip install -U pip
python -m pip install -e .
```

建议：

```powershell
$env:PYTHONUTF8='1'
```

或：

```powershell
python -X utf8 -m sparkflow --help
```

## 2. 单图审图

### 审 DXF

```powershell
python -X utf8 -m sparkflow audit "D:\\path\\drawing.dxf" `
  --out out_demo `
  --ruleset rulesets\\example `
  --dxf-backend auto
```

### 审 DWG

```powershell
python -X utf8 -m sparkflow audit "D:\\path\\drawing.dwg" `
  --out out_demo `
  --ruleset rulesets\\example `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe"
```

## 3. 批量审图

```powershell
python -X utf8 -m sparkflow audit-dataset "D:\\path\\dataset_root" `
  --out out_dataset `
  --ruleset rulesets\\example `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe" `
  --workers 3 `
  --dwg-timeout 300
```

输出重点：

- `dataset_selection.json`
- `dataset_summary.json`
- `dataset_summary.md`

## 4. 生成数据集总报告

```powershell
python -X utf8 -m sparkflow dataset-report out_dataset\\20260325T100443Z `
  --ruleset rulesets\\example
```

输出：

- `final_audit_report.md`
- `final_audit_report.docx`

## 5. 生成整改清单

```powershell
python -X utf8 -m sparkflow rectification-checklist out_dataset\\20260325T100443Z
```

输出：

- `rectification_checklist.md`
- `rectification_checklist.docx`
- `rectification_checklist.json`

## 6. 严格规则重跑

如果要把 `wire.floating_endpoints` 按更严格标准处理：

- 命令里传入的规则集目录：`rulesets\\stategrid_peidian_strict`
- 最终产物里显示的规则版本：`stategrid_peidian_strict_v1`

```powershell
python -X utf8 -m sparkflow audit-dataset `
  "D:\\path\\dataset_root" `
  --out out_stategrid_peidian_audit `
  --ruleset rulesets\\stategrid_peidian_strict `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe" `
  --workers 3 `
  --dwg-timeout 300
```

## 7. 规则集差异比较

```powershell
python -X utf8 -m sparkflow ruleset-diff `
  rulesets\\example `
  rulesets\\stategrid_peidian_strict `
  --out out\\ruleset_diff
```

输出：

- `ruleset_diff.json`
- `ruleset_diff.md`

## 8. 常见参数

### 8.1 导线过滤

```powershell
--wire-layer-include
--wire-layer-exclude
--wire-ltype-include
--wire-ltype-exclude
--wire-min-length
```

### 8.2 拓扑吸附容差

```powershell
--topo-tol 1.0
```

### 8.3 DWG 后端

```powershell
--dwg-backend auto|cli|autocad
--dwg-converter "<converter>"
--dwg-timeout 300
```

## 9. Windows 编码建议

为了避免中文 Markdown 或 PowerShell 输出乱码，建议：

- 优先使用 `python -X utf8`
- 输入输出文件统一 `UTF-8`
- 不要用临时 PowerShell 内联脚本去拼接大段中文报告
- 优先使用仓库内正式命令：
  - `dataset-report`
  - `rectification-checklist`

## 10. `review-pipeline` 分页结果怎么看

`split/manifest.json` 中，建议优先关注这几个字段：

- `page_seq`：逐页顺序编号，适合在一套施工图中唯一定位页面
- `primary_code`：标题栏提取出的工程图号
- `title`：标题栏提取出的页名
- `title_part_no/title_part_total`：标题中的 `1/3、2/3、3/3`
- `placeholder_texts`：该页是否存在 `XXX/FXX/暂命名` 等未定稿文本

对于 `擎能` 模板这类一个工程图号覆盖多页的图纸：

- 不要把 `primary_code` 当成逐页唯一编号
- 优先使用 `page_seq + title`
- 若标题本身带 `1/3、2/3、3/3`，再结合 `title_part_no/title_part_total`
