# SparkFlow

SparkFlow 是一个面向配电/一次系统图审查场景的 CAD 自动审图 CLI 工具。它当前聚焦于 `DWG/DXF -> 解析 -> 建模 -> 抽取规则->规则检查 -> JSON/Markdown/DOCX 报告` 这条本地批处理链路，适合研发验证、规则迭代、样本集回归和项目级离线审图。

## 项目定位

- 优先场景：一次系统图、单线图、电气图、配电箱/开关柜/电缆分支箱类图纸
- 当前形态：本地 CLI 工具 + 批处理工作流
- 当前边界：不是在线平台，也不是“任意规范文档自动转规则”的完整产品
- 当前优势：可对目标图纸稳定输出结构化报告、数据集汇总、最终总报告、整改清单

## 核心能力

- `DWG/DXF` 图纸审图
- `drawing-info` 单图结构化信息提取
- `review-audit` 结合评审意见目录生成评审规则审查报告
- `review-pipeline` 一次完成复审、按图框拆分、整改问题清单生成
- `audit-dataset` 批量审图与筛图
- `dataset-report` 数据集最终总报告
- `rectification-checklist` 失败图纸坐标级整改清单
- `ruleset-diff` 规则集版本差异比对
- 规则集支持：
  - 结构化 `ruleset.json`
  - `CSV/TSV`
  - `XLSX`
  - 结构化规范摘要 `Markdown`
- 报告输出支持：
  - `report.json`
  - `report.md`
  - `report.docx`
  - 数据集总报告 `final_audit_report.md/.docx`
  - 整改清单 `rectification_checklist.md/.docx/.json`

## 总体流程图

```mermaid
flowchart LR
  A["DWG / DXF 图纸"] --> B["CAD 解析<br/>DXF 读取 / DWG 转 DXF"]
  B --> C["图纸筛选与分类<br/>supported_electrical / geometry_only / unsupported"]
  C --> D["结构化建模<br/>设备识别 / 导线抽取 / 端子推断"]
  D --> E["连通图与电气图"]
  E --> F["规则引擎<br/>规则集 + 参数 + 图纸类型分级"]
  F --> G["单图报告<br/>report.json / report.md / report.docx"]
  G --> H["数据集汇总<br/>dataset_summary / final_audit_report / rectification_checklist"]
```

### 当前阶段说明

- 本阶段仍是工具型产品（单场景闭环），不是在线平台服务
- 典型闭环流程：上传图纸、解析建模、规则检测、输出报告、人工整改、复审确认
- 当前默认最高能力层级是“拓扑 + 规则”，核心产物包括 `connectivity.json` 与 `electrical.json`

### 审图能力分级

- Level 1：图元抽取，输出实体类型/图层统计、bbox、关键坐标
- Level 2：设备对象识别，从 `INSERT +` 附近文本构建设备与端子
- Level 3：拓扑关系建模，对候选导线进行拆段、吸附聚类、连通分量分析，并运行拓扑级规则

### 语义边界

- 拓扑是“候选导线”的几何连通拓扑，需要通过图层/线型/长度过滤减少 DIM、标注引线等噪声
- 设备类型识别与端子模板依赖规则库持续补齐；未命中模板时会退回到附近线端点聚类/默认端子策略

## 功能架构图

```mermaid
flowchart TB
  U1["用户 / 审图工程师"] --> CLI["CLI 命令层<br/>audit / drawing-info / review-audit / review-pipeline / audit-dataset / dataset-report / rectification-checklist / ruleset-diff"]
  U2["HTTP 客户端 / 前端"] --> API["REST API 层<br/>POST /api/review-audit / /api/review-pipeline<br/>GET /api/health"]
  CLI --> CORE["核心流程层<br/>sparkflow/core.py"]
  API --> REVIEW["复审流程层<br/>sparkflow/review.py / review_workflow.py"]
  CLI --> REVIEW
  CLI --> RULESET["规则输入层<br/>JSON / CSV / TSV / XLSX / 规范摘要 Markdown"]

  CORE --> CAD["CAD 解析层<br/>sparkflow/cad"]
  CORE --> MODEL["建模层<br/>sparkflow/model"]
  CORE --> RULES["规则执行层<br/>sparkflow/rules"]
  CORE --> REPORT["报告层<br/>sparkflow/reporting"]
  REVIEW --> CAD
  REVIEW --> REPORT

  CAD --> MODEL
  MODEL --> RULES
  RULESET --> RULES
  RULES --> REPORT

  REPORT --> OUT1["单图产物<br/>report.json / report.md / report.docx"]
  REPORT --> OUT2["数据集产物<br/>dataset_summary / final_audit_report / rectification_checklist"]
  REVIEW --> OUT3["复审产物<br/>drawing_info / review_report / split manifest / 整改问题清单"]
  REVIEW --> OUT4["API 响应<br/>JSON 格式报告内联返回"]
```

## 评审规则审查实现方案

当前项目里已经把“输入一份 `DWG` + 一份评审意见目录，解析出项目专用评审规则，再对图纸执行审查并输出整改清单”的链路收口成稳定接口：

| 层级 | 文件 | 责任 |
| --- | --- | --- |
| CLI 入口 | `sparkflow/__main__.py` | 暴露 `drawing-info`、`review-audit`、`review-pipeline` 三个命令 |
| 图纸抽取 | `sparkflow/review.py` | 提取 `drawing_info.json`，加载 `评审意见` 目录并生成 `review_rules.json`，执行规则审查并输出 `review_report` |
| 复审编排 | `sparkflow/review_workflow.py` | 复用 `review_audit()` 结果，执行图框拆分、单页文本提取、整改清单汇总 |
| CAD 基础能力 | `sparkflow/cad/*` | `DWG -> DXF` 转换、`DXF` 解析、视口/图元基础读取 |
| 结果输出 | `docs/review-pipeline.md` | 说明命令、Python API、产物结构和已知限制 |

### `review-pipeline` 架构流程图

```mermaid
flowchart LR
  A["输入<br/>DWG / DXF + 评审意见目录"] --> B["CLI / Python API<br/>review-pipeline()"]
  B --> C["review_audit()<br/>drawing_info + review_rules + review_report"]
  C --> D["DWG 转 DXF<br/>复用 converted_dxf"]
  D --> E["Layout1 / 布局 图框识别<br/>A3/A4 + 擎能模板 + viewport"]
  E --> F["单页拆分<br/>SVG / PNG / texts.json / manifest.json"]
  C --> G["评审规则结果<br/>passed / failed / manual_review"]
  F --> H["逐页问题汇总<br/>placeholder / 暂命名 / 未定稿"]
  G --> I["评审规则问题汇总"]
  H --> J["整改问题清单.md / .json"]
  I --> J
```

### 典型输出

- `drawing_info.json`：图纸结构化摘要、唯一文本、占位符文本
- `review_rules.json`：从 `评审意见` 目录抽取出的项目/意见/回复与结构化评审规则
- `review_report.json/.md`：基于评审规则的图纸审查结论
- `split/manifest.json`：图框拆分页清单
  - 单页记录至少包含：`seq`、`page_seq`、`sheet_no`、`title_part_no`、`title_part_total`、`primary_code`、`title`、`codes`、`placeholder_texts`
- `split/pages/*.png|*.svg|*.texts.json`：单页图像和文本证据
- `整改问题清单.md/.json`：正式整改问题清单

### 当前实测基线

当前仓库这轮已经实际跑通、并作为基线保留的流程是：

- 输入图纸：`docs\珠海金湾供电局2026年3月配网业扩配套项目--2项\评审前\030451DY26030001-南水供电所景旺电子（厂房一）10kV业扩配套工程\附件3 施工图\南水供电所景旺电子（厂房一）10kV业扩配套工程.dwg`
- 评审意见目录：`docs\珠海金湾供电局2026年3月配网业扩配套项目--2项\评审意见`
- 已验证输出：`tmp\review_pipeline_030451DY26030001_docdriven\20260415T070348Z`
- 已迁移测试夹具：`tests/fixtures/review_baseline/030451DY26030001/fixture.json`

后续优先以这条 `review-pipeline` 真实链路为准，不再把早期 `image/` 历史样例数据集当成当前主流程基线。

### 补充验证案例：擎能模板（罗定加益项目）

这轮新增验证了韶关市擎能设计有限公司模板下的真实项目：

- 输入图纸：`docs\罗定供电局2025年中低压配电网第十批紧急项目--4项\罗定供电局2025年中低压配电网第十批紧急项目施工图--评审前\罗定供电局2025年中低压配电网第十批紧急项目施工图\加益供电所10kV合江线新增配变及黄沙公用台变改造工程\附件3 施工图\图纸-加益供电所10kV合江线新增配变及黄沙公用台变改造工程.dwg`
- 评审目录：`docs\罗定供电局2025年中低压配电网第十批紧急项目--4项\评审意见及回复\评审技术要点`
- 输出目录：`tmp\review_pipeline_jiayi_cli_case\20260422T062918Z`
- 已验证结果：
  - `split_page_count = 94`
  - `page_issue_count = 2`
  - `review_issue_count = 39`

这个案例主要覆盖：

- `擎能A3横/竖`、`擎能A4竖` 图框名识别
- `布局` 空间图框拆分
- 标题栏图号/图名提取
- `page_seq` 与标题中的 `1/3、2/3、3/3` 提取

## 输出示意图

```mermaid
flowchart TD
  RUN["一次 audit-dataset 运行"] --> IDX["dataset_index.json"]
  RUN --> SEL["dataset_selection.json"]
  RUN --> SUM["dataset_summary.json / dataset_summary.md"]
  RUN --> FINAL["final_audit_report.md / .docx"]
  RUN --> RECT["rectification_checklist.md / .docx / .json"]
  RUN --> FILES["files/"]

  FILES --> F1["<分类>/<图纸名__hash>/report.json"]
  FILES --> F2["<分类>/<图纸名__hash>/report.md"]
  FILES --> F3["<分类>/<图纸名__hash>/report.docx"]
  FILES --> F4["<分类>/<图纸名__hash>/connectivity.json"]
  FILES --> F5["<分类>/<图纸名__hash>/electrical.json"]
```

## 当前命令

```text
sparkflow audit
sparkflow index
sparkflow drawing-info
sparkflow review-audit
sparkflow review-pipeline
sparkflow audit-dataset
sparkflow dataset-report
sparkflow rectification-checklist
sparkflow ruleset-diff
sparkflow serve
```

### REST API 服务

自 `v0.2.0` 起支持 **HTTP REST API 接口**，可通过 POST 请求提交评审意见文件路径和图纸设计文件路径，自动执行审图核查并返回结果。

**启动服务：**

```powershell
python -X utf8 -m sparkflow serve --port 8600
```

**API 端点：**

| 方法 | 端点 | 功能 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/review-audit` | 评审规则审查 |
| `POST` | `/api/review-pipeline` | 完整复审流程（含图框拆分 + 整改清单） |

详见 [REST API 接口说明](docs/rest-api.md)

## 快速开始

### 1. 安装环境

要求：

- Python `3.10+`
- Windows PowerShell 或命令行
- 依赖包：
  - `ezdxf>=1.4.3`
  - `python-docx>=1.1.0`
- 可选：
  - `ODA File Converter`，用于 `DWG -> DXF`
  - `AutoCAD + pywin32`，用于 `autocad` 后端

安装：

```powershell
python -m pip install -U pip
python -m pip install -e .
```

推荐在 Windows 上开启 UTF-8：

```powershell
$env:PYTHONUTF8='1'
```

或直接：

```powershell
python -X utf8 -m sparkflow --help
```

### 2. 单图审图

```powershell
python -X utf8 -m sparkflow audit "D:\\path\\drawing.dwg" `
  --out out `
  --ruleset rulesets\\example `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe"
```

### 3. 数据集批量审图

```powershell
python -X utf8 -m sparkflow audit-dataset "D:\\path\\dataset_root" `
  --out out_oda_dataset `
  --ruleset rulesets\\example `
  --dwg-backend cli `
  --dwg-converter "D:\\Program Files\\ODA\\ODAFileConverter 27.1.0\\ODAFileConverter.exe" `
  --workers 3 `
  --dwg-timeout 300
```

### 4. 生成数据集总报告

```powershell
python -X utf8 -m sparkflow dataset-report out_oda_dataset\\20260325T100443Z `
  --ruleset rulesets\\example
```

### 5. 生成整改清单

```powershell
python -X utf8 -m sparkflow rectification-checklist out_oda_dataset\\20260325T100443Z
```

### 6. 比较规则集差异

```powershell
python -X utf8 -m sparkflow ruleset-diff rulesets\\example rulesets\\stategrid_peidian_strict `
  --out out\\ruleset_diff
```

### 7. 评审规则审查与整改清单

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

Windows 下如果是反复复跑同一个项目，建议直接执行：

```powershell
.\scripts\run_review_pipeline.ps1
```

这个包装脚本把常用 `DWG`、`评审目录`、`输出目录` 和 `ODAFileConverter.exe` 预设收口在 [scripts/run_review_pipeline.ps1](scripts/run_review_pipeline.ps1) 顶部，避免 PowerShell 多行粘贴时把两条命令拼成一条。

返回结果依次为：

1. `run_dir`
2. `整改问题清单.md`
3. `整改问题清单.json`
4. `split/manifest.json`
5. `review_report.json`

## 典型输出目录

`audit-dataset` 运行目录通常包含：

```text
<run_dir>/
  dataset_index.json
  dataset_selection.json
  dataset_summary.json
  dataset_summary.md
  final_audit_report.md
  final_audit_report.docx
  rectification_checklist.md
  rectification_checklist.docx
  rectification_checklist.json
  files/
    <分类>/<图纸名__hash>/
      report.json
      report.md
      report.docx
      connectivity.json
      electrical.json
```

## 文档导航

- [项目概览与架构](docs/architecture.md)
- [快速开始与命令示例](docs/quick-start.md)
- [REST API 接口说明](docs/rest-api.md)
- [规则集与规则输入](docs/rulesets.md)
- [报告与整改清单说明](docs/reports.md)
- [评审规则审查与整改清单流程](docs/review-pipeline.md)
- [部署、环境与运维建议](docs/deployment.md)

## 仓库结构

```text
sparkflow/        核心源码
rulesets/         当前规则集输入：示例规则、严格规则、表格/XLSX/规范摘要示例
catalog/          当前运行期模型配置：设备模板、导线过滤配置
scripts/          辅助/排障脚本，不属于 review-pipeline 对外接口
                 当前也包含 `run_review_pipeline.ps1` 这种面向 Windows 复跑场景的薄包装脚本
tests/            回归测试与 CLI 验证
image/            历史本地样例数据集，不是当前 review-pipeline 基线输入
docs/             使用文档 + 当前实测项目图纸/评审意见
```

## 目录是否参与当前流程

| 目录 | 当前是否直接参与主流程 | 作用 |
| --- | --- | --- |
| `rulesets/` | 是 | CLI 和测试会直接加载规则集目录 |
| `catalog/` | 是 | 默认设备模板和导线过滤配置的权威来源 |
| `scripts/` | 部分 | 仅保留通用辅助脚本；不再把硬编码旧样例路径的脚本视为主流程入口 |
| `tests/` | 是 | 当前接口、规则集、报告产物都靠这里回归验证 |
| `image/` | 否 | 历史本地样例数据，不是当前 `030451DY26030001` 复审基线 |
| `docs/` | 是 | 同时承载产品文档和本轮真实评审输入资料 |

## 现在适合用它做什么

- 对既有样本集做批量审图
- 对规则集做回归验证和差异比对
- 生成项目级最终总报告和整改清单
- 迭代设备识别、规则和报告格式

## 现在还不适合直接承诺什么

- 任意规范文档自动转可执行规则
- 任意图纸类型稳定审图
- 在线多用户平台能力
- 完整的人工复核闭环系统

## 相关规则集

- [example](rulesets/example/ruleset.json)：默认示例规则集
- [stategrid_peidian_strict](rulesets/stategrid_peidian_strict/ruleset.json)：严格规则集目录名；当前 `ruleset.json` 内部 `version` 为 `stategrid_peidian_strict_v1`，用于将 `wire.floating_endpoints` 提升为严格判定
- [example_table](rulesets/example_table/ruleset.json)：表格规则集示例
- [example_xlsx](rulesets/example_xlsx/ruleset.json)：Excel 规则集示例
- [example_normative](rulesets/example_normative/ruleset.json)：规范摘要规则集示例

## 开发提示

- 当前工作树可能包含大量实验产物和历史输出，提交或归档前建议先确认目标运行目录
- 处理中文路径和中文 Markdown/DOCX 时，建议始终使用 UTF-8
- 若在 PowerShell 中拼接内联脚本生成中文文本，容易出现 `?` 替换，建议优先使用仓库内正式命令和模块
