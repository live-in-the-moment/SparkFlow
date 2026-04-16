# REST API 快速入门

> 3 分钟快速上手 SparkFlow REST API 审图服务

## 1. 启动 API 服务

```bash
# 安装（如果未安装）
pip install -e .

# 启动 API 服务（监听 0.0.0.0:8600）
python -m sparkflow serve
```

输出示例：
```
SparkFlow 审图 API 服务已启动: http://0.0.0.0:8600
  POST /api/review-audit       评审规则审查
  POST /api/review-pipeline    完整复审流程
  GET  /api/health             健康检查
```

## 2. 测试健康检查

```bash
curl http://localhost:8600/api/health
```

响应：
```json
{
  "status": "ok",
  "service": "sparkflow-review-api"
}
```

## 3. 执行评审规则审查

### 准备文件

- 图纸文件：`D:/drawings/project.dwg`
- 评审意见目录：`D:/reviews/project_review/`
- 输出目录：`D:/outputs/`

### 发送请求

```bash
curl -X POST http://localhost:8600/api/review-audit \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/drawings/project.dwg",
    "review_dir": "D:/reviews/project_review/",
    "out_dir": "D:/outputs/",
    "project_code": "PRJ001"
  }'
```

### 响应示例

```json
{
  "success": true,
  "data": {
    "run_dir": "D:/outputs/20260415T120000Z",
    "drawing_info_json": "D:/outputs/20260415T120000Z/drawing_info.json",
    "review_report_json": "D:/outputs/20260415T120000Z/review_report.json",
    "review_report_md": "D:/outputs/20260415T120000Z/review_report.md",
    "review_report": {
      "created_at": "2026-04-15T12:00:00Z",
      "rules": [
        {
          "rule_id": "design.naming_consistency",
          "status": "passed",
          "message": "工程名称一致"
        }
      ]
    }
  }
}
```

## 4. 执行完整复审流程

```bash
curl -X POST http://localhost:8600/api/review-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/drawings/project.dwg",
    "review_dir": "D:/reviews/project_review/",
    "out_dir": "D:/outputs/",
    "project_code": "PRJ001"
  }'
```

响应包含额外的拆分与整改清单字段：

```json
{
  "success": true,
  "data": {
    "run_dir": "...",
    "split_manifest_json": "D:/outputs/20260415T120000Z/split/manifest.json",
    "rectification_checklist_md": "D:/outputs/20260415T120000Z/整改问题清单.md",
    "rectification_checklist_json": "D:/outputs/20260415T120000Z/整改问题清单.json",
    "rectification_checklist": {
      "issues": [
        {
          "page": 1,
          "category": "design",
          "issue": "工程名称与图框不一致",
          "severity": "error",
          "action": "修正设计说明书"
        }
      ]
    }
  }
}
```

## 5. Python 客户端示例

```python
import requests
import json

# 健康检查
resp = requests.get("http://localhost:8600/api/health")
print(resp.json())

# 提交审图请求
payload = {
    "drawing_path": "D:/drawings/project.dwg",
    "review_dir": "D:/reviews/project_review/",
    "out_dir": "D:/outputs/",
    "project_code": "PRJ001"
}

resp = requests.post(
    "http://localhost:8600/api/review-pipeline",
    json=payload
)

if resp.status_code == 200:
    result = resp.json()
    if result["success"]:
        data = result["data"]
        print(f"审图完成")
        print(f"输出目录: {data['run_dir']}")
        print(f"评审报告: {data['review_report_json']}")
        print(f"整改清单: {data['rectification_checklist_json']}")

        # 查看整改问题
        checklist = data.get("rectification_checklist", {})
        for issue in checklist.get("issues", []):
            print(f"  - [{issue['severity']}] {issue['issue']}")
    else:
        print(f"错误: {result.get('error')}")
else:
    print(f"HTTP 错误: {resp.status_code}")
```

## 6. 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `drawing_path` | 图纸文件路径 | `"D:/drawings/project.dwg"` |
| `review_dir` | 评审意见目录 | `"D:/reviews/project_review/"` |
| `out_dir` | 输出目录 | `"D:/outputs/"` |
| `project_code` | 工程编号 | `"PRJ001"` |
| `dwg_converter` | DWG 转换器路径 | `"C:/ODA/ODAFileConverter.exe"` |
| `skip_sparkflow_audit` | 跳过通用审图 | `true` / `false` |

完整参数列表见 [REST API 文档](../docs/rest-api.md#api-端点)

## 7. 常见问题

### 请求返回 422 错误

确认文件路径存在且格式正确：

```bash
# 验证文件是否存在
ls -la "D:/drawings/project.dwg"
ls -la "D:/reviews/project_review/"
```

### DWG 无法识别

需要配置 DWG 转换器：

```bash
curl -X POST http://localhost:8600/api/review-audit \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/drawings/project.dwg",
    "review_dir": "D:/reviews/project_review/",
    "out_dir": "D:/outputs/",
    "dwg_backend": "cli",
    "dwg_converter": "C:/Program Files/ODA/ODAFileConverter.exe"
  }'
```

### API 响应超时

增加 `dwg_timeout` 参数：

```json
{
  "drawing_path": "...",
  "review_dir": "...",
  "out_dir": "...",
  "dwg_timeout": 600
}
```

## 8. 更多资源

- [REST API 完整文档](../docs/rest-api.md)
- [项目架构](../docs/architecture.md)
- [命令行快速开始](../docs/quick-start.md)
