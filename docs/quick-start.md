# 快速开始与命令示例

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
python -X utf8 -m sparkflow audit "image\\111\\电缆CAD图纸\\国网低压典设第26章E模块2017-8-18.dxf" `
  --out out_demo `
  --ruleset rulesets\\example `
  --dxf-backend auto
```

### 审 DWG

```powershell
python -X utf8 -m sparkflow audit "image\\111\\配电部分CAD\\低压开关柜DK-1\\380V.dwg" `
  --out out_demo `
  --ruleset rulesets\\example `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe"
```

## 3. 批量审图

```powershell
python -X utf8 -m sparkflow audit-dataset "image\\111\\配电部分CAD" `
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

```powershell
python -X utf8 -m sparkflow audit-dataset `
  "image\\国家电网公司380220V配电网工程典型设计（2018年版）_1772430671059\\配电部分CAD" `
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
