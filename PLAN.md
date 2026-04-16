# 实现计划：REST API 审图服务

## 目标
创建一个 HTTP API 服务，通过 POST 请求提交评审意见文件路径和需要审核的图纸设计文件路径，自动执行审图核查并返回结果。

## 技术方案
- 使用 Python 标准库 `http.server` + `json` 实现轻量 HTTP 服务（无额外依赖）
- 复用现有 `review_audit()` 和 `review_pipeline()` 函数
- 新增 CLI 子命令 `sparkflow serve` 启动 API 服务

## 新增文件
1. **`sparkflow/server.py`** — HTTP API 服务模块（<500行）
   - `POST /api/review-audit` — 执行评审规则审查
   - `POST /api/review-pipeline` — 执行完整复审流程（含图框拆分+整改清单）
   - `GET /api/health` — 健康检查
   - 请求/响应均为 JSON

## 修改文件
2. **`sparkflow/__main__.py`** — 新增 `serve` 子命令

## API 设计

### POST /api/review-audit
```json
// 请求
{
  "drawing_path": "D:/path/to/file.dwg",
  "review_dir": "D:/path/to/评审意见/",
  "out_dir": "D:/path/to/output/",
  "project_code": "030451DY26030001",
  "dwg_backend": "auto",
  "dwg_converter": "",
  "skip_sparkflow_audit": false
}
// 响应
{
  "success": true,
  "data": {
    "run_dir": "...",
    "review_report_json": "...",
    "review_report_md": "...",
    "drawing_info_json": "...",
    "review_rules_json": "..."
  }
}
```

### POST /api/review-pipeline
```json
// 请求（同上）
// 响应增加 rectification_checklist 和 split_manifest
```
