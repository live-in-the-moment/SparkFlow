# 项目概览与架构

## 1. 项目目标

SparkFlow 的目标是把配电/一次系统图的自动审图流程做成一条可复跑、可追溯的本地链路：

`CAD 图纸 -> 解析 -> 结构化建模 -> 规则检查 -> 单图报告 -> 数据集汇总 -> 总报告/整改清单`

当前重点是：

- 一次系统图、单线图、电气图
- 低压开关柜、综合配电箱、电缆分支箱
- 数据集批量审图与规则回归

## 2. 主流程

### 2.0 系统总览图

```mermaid
flowchart LR
  IN["输入图纸<br/>DWG / DXF / 数据集目录"] --> CLI["CLI 入口<br/>sparkflow/__main__.py"]
  CLI --> CORE["核心编排<br/>sparkflow/core.py"]
  CORE --> CAD["CAD 解析"]
  CORE --> MODEL["结构化建模"]
  CORE --> RULES["规则引擎"]
  CORE --> REPORT["报告生成"]
  RULESET["规则集目录<br/>rulesets/*"] --> RULES
  REPORT --> OUT["单图报告 / 数据集汇总 / 总报告 / 整改清单"]
```

### 2.1 单图流程

```mermaid
flowchart LR
  A["DWG / DXF"] --> B["parse"]
  B --> C["selection / classification"]
  C --> D["model build"]
  D --> E["electrical / connectivity graph"]
  E --> F["rules engine"]
  F --> G["report.json / report.md / report.docx"]
```

### 2.2 数据集流程

```mermaid
flowchart LR
  A["dataset dir"] --> B["index"]
  B --> C["selection"]
  C --> D["per-file audit"]
  D --> E["dataset_summary.json / dataset_summary.md"]
  E --> F["final_audit_report.md / final_audit_report.docx"]
  E --> G["rectification_checklist.md / .docx / .json"]
```

### 2.3 数据处理示意图

```mermaid
flowchart TD
  CAD["CAD 原始实体"] --> WIRES["导线候选抽取"]
  CAD --> DEV["设备与文本识别"]
  CAD --> META["图层 / 线型 / bbox / 坐标"]
  WIRES --> NETS["连通网络 nets"]
  DEV --> TERMS["端子推断"]
  META --> MODEL["结构化系统模型"]
  TERMS --> MODEL
  NETS --> MODEL
  MODEL --> CHECKS["规则检查"]
  CHECKS --> REPORTS["问题列表 + 风险等级 + 整改建议 + 条文映射"]
```

## 3. 主要模块

### 3.0 功能架构图

```mermaid
flowchart TB
  subgraph Input["输入与命令层"]
    CLI["sparkflow/__main__.py"]
    RULESET["rulesets/*"]
    DATA["DWG / DXF / dataset dir"]
  end

  subgraph Engine["核心处理层"]
    CORE["core.py"]
    CAD["cad/*"]
    MODEL["model/*"]
    RULES["rules/*"]
    REPORT["reporting/*"]
  end

  subgraph Output["输出层"]
    R1["单图报告"]
    R2["数据集汇总"]
    R3["最终总报告"]
    R4["整改清单"]
  end

  DATA --> CLI
  RULESET --> CLI
  CLI --> CORE
  CORE --> CAD
  CORE --> MODEL
  CORE --> RULES
  CORE --> REPORT
  CAD --> MODEL
  MODEL --> RULES
  RULES --> REPORT
  REPORT --> R1
  REPORT --> R2
  REPORT --> R3
  REPORT --> R4
```

### 3.1 入口

- [`sparkflow/__main__.py`](../sparkflow/__main__.py) — CLI 入口
- [`sparkflow/server.py`](../sparkflow/server.py) — REST API 服务入口

负责：

- CLI 参数解析与命令分发
- REST API 端点处理与请求校验
- `audit`
- `audit-dataset`
- `dataset-report`
- `rectification-checklist`
- `ruleset-diff`
- `serve` — 启动 HTTP API 服务

### 3.2 核心审图流程

- [`sparkflow/core.py`](../sparkflow/core.py)

负责：

- 单文件审图
- 数据集批量审图
- 汇总文件落盘

### 3.3 CAD 解析

- [`sparkflow/cad/`](../sparkflow/cad)

负责：

- `DXF` 解析
- `DWG -> DXF` 转换调用
- ODA / AutoCAD COM 后端适配

### 3.4 建模

- [`sparkflow/model/`](../sparkflow/model)

负责：

- 导线候选抽取
- 设备识别
- 端子推断
- 连通图与电气图建模

### 3.5 规则系统

- [`sparkflow/rules/`](../sparkflow/rules)

负责：

- 规则加载
- 规则注册
- 规则执行
- 规则集差异比对

### 3.6 报告系统

- [`sparkflow/reporting/`](../sparkflow/reporting)

负责：

- 单图 Markdown / DOCX 报告
- 数据集总报告
- 整改清单
- 正式交付字段，如条文映射、整改建议、风险等级、置信度

## 4. 支持的规则输入

当前规则输入支持四类：

- 结构化 `ruleset.json`
- `CSV/TSV`
- `XLSX`
- 结构化 `Markdown` 规范摘要

规则集都位于 [`rulesets/`](../rulesets)。

## 5. 当前产物类型

### 单图

- `report.json`
- `report.md`
- `report.docx`
- `connectivity.json`
- `electrical.json`

### 数据集

- `dataset_index.json`
- `dataset_selection.json`
- `dataset_summary.json`
- `dataset_summary.md`
- `final_audit_report.md`
- `final_audit_report.docx`
- `rectification_checklist.md`
- `rectification_checklist.docx`
- `rectification_checklist.json`

## 6. 当前边界

当前项目支持两种调用方式：

### 6.1 CLI 模式（命令行）

- 直接运行 `sparkflow audit|review-pipeline|...` 命令
- 适合：脚本化处理、CI/CD 集成、本地批处理

### 6.2 REST API 模式（新增 v0.2.0+）

- 启动 `sparkflow serve` 服务后通过 HTTP POST 提交请求
- 支持 `/api/review-audit` 和 `/api/review-pipeline` 两个端点
- 返回 JSON 格式结果，报告内容内联返回
- 适合：Web 前端集成、跨进程调用、多种编程语言客户端

详见 [REST API 接口说明](rest-api.md)

### 6.3 Python API 模式（现有）

直接导入模块调用核心函数：

```python
from sparkflow.review_workflow import review_pipeline

output = review_pipeline(
    drawing_path,
    review_dir,
    out_dir,
    project_code="PRJ001"
)
```

当前项目仍是 CLI-first 工具链，不是完整平台：

- 没有任务队列/数据库/用户系统
- 没有人工复核流转界面
- 没有自然语言规则自动抽取成生产级规则

但它已经适合：

- 样本集批量跑批
- 审图报告归档
- 规则回归和版本对比
- 坐标级整改清单生成
- Web 前端与第三方系统集成

## 7. 使用视角示意图

```mermaid
journey
  title SparkFlow 典型使用路径
  section 准备
    安装 Python 与依赖: 4: 用户
    配置 ODA File Converter: 4: 用户
    选择规则集: 4: 用户
  section 审图
    运行 audit 或 audit-dataset: 5: 用户, SparkFlow
    自动解析与建模: 5: SparkFlow
    执行规则检查: 5: SparkFlow
  section 交付
    查看单图报告: 5: 用户
    查看总报告与整改清单: 5: 用户
    根据坐标整改并复跑: 4: 用户, SparkFlow
```
