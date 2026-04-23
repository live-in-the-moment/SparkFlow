# SparkFlow REST API 快速参考卡

## 🚀 启动

```bash
python -m sparkflow serve --port 8600
```

## 📍 端点速览

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/api/health` | 健康检查 ✓ |
| POST | `/api/review-audit` | 评审规则审查 |
| POST | `/api/review-pipeline` | 复审+拆分+整改清单 |

## 🔧 最小化请求

### review-audit

```bash
curl -X POST http://localhost:8600/api/review-audit \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/file.dwg",
    "review_dir": "D:/review/",
    "out_dir": "D:/out/",
    "project_code": "PRJ001"
  }'
```

### review-pipeline

```bash
curl -X POST http://localhost:8600/api/review-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/file.dwg",
    "review_dir": "D:/review/",
    "out_dir": "D:/out/"
  }'
```

## 📋 主要参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `drawing_path` | ✅ | - | 图纸文件路径 |
| `review_dir` | ✅ | - | 评审意见目录 |
| `out_dir` | ❌ | `"out"` | 输出目录 |
| `project_code` | ❌ | - | 工程编号 |
| `dwg_converter` | ❌ | - | DWG 转换器路径 |
| `skip_sparkflow_audit` | ❌ | `false` | 跳过通用审图 |
| `level` | ❌ | `3` | 审图深度（1/2/3） |
| `dwg_backend` | ❌ | `"auto"` | `auto/cli/autocad` |

## ✅ 成功响应

```json
{
  "success": true,
  "data": {
    "run_dir": "D:/out/20260415T120000Z",
    "review_report_json": "...",
    "review_report": { ... },
    "rectification_checklist": { ... }
  }
}
```

## ❌ 错误响应

```json
{
  "success": false,
  "errors": [
    "图纸文件不存在: D:/file.dwg",
    "评审意见目录不存在: D:/review/"
  ]
}
```

## 🐍 Python 客户端（最小化）

```python
import requests

resp = requests.post(
    "http://localhost:8600/api/review-pipeline",
    json={
        "drawing_path": "D:/file.dwg",
        "review_dir": "D:/review/",
        "out_dir": "D:/out/"
    }
)

if resp.status_code == 200:
    data = resp.json()["data"]
    print(f"✓ 完成: {data['run_dir']}")
    print(f"报告: {data['review_report_json']}")
else:
    print(f"✗ 错误: {resp.status_code}")
```

## 🔗 关键链接

- [完整文档](rest-api.md)
- [快速入门](rest-api-quickstart.md)
- [实现总结](REST_API_IMPLEMENTATION_SUMMARY.md)
- [架构说明](architecture.md)

## 📊 状态码速查

| 码 | 含义 |
|----|------|
| 200 | ✓ 成功 |
| 400 | ✗ JSON 格式错误 |
| 404 | ✗ 端点不存在 |
| 422 | ✗ 参数校验失败 |
| 500 | ✗ 服务器错误 |

## 💡 常见场景

### 场景 1: 仅审图（跳过通用规则）

```json
{
  "drawing_path": "...",
  "review_dir": "...",
  "skip_sparkflow_audit": true
}
```

### 场景 2: 使用 DWG 转换器

```json
{
  "drawing_path": "...",
  "review_dir": "...",
  "dwg_backend": "cli",
  "dwg_converter": "C:/ODA/ODAFileConverter.exe",
  "dwg_timeout": 300
}
```

### 场景 3: 导线层过滤

```json
{
  "drawing_path": "...",
  "review_dir": "...",
  "wire_filter": {
    "include_layers": ["0"],
    "exclude_layers": [],
    "min_length": 0.5
  }
}
```

## 📞 支持

- 查看 stderr 日志了解详细错误
- 调整 `dwg_timeout` 处理大文件
- 确保文件路径存在且格式正确
- 更多问题见 [rest-api-quickstart.md 常见问题](rest-api-quickstart.md#7-常见问题)
