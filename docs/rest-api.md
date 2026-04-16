# REST API 接口说明

> SparkFlow v0.2.0+ 支持 HTTP REST API 审图服务

## 概述

REST API 提供了一种**无需命令行的方式**来使用 SparkFlow 审图能力，适合与其他系统集成、Web 前端调用或远程审图场景。

## 启动服务

### 本地启动（开发/测试）

```bash
# 默认监听 0.0.0.0:8600
python -m sparkflow serve

# 指定端口
python -m sparkflow serve --port 8601

# 指定监听地址
python -m sparkflow serve --host 127.0.0.1 --port 8600
```

### Docker 部署（可选）

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8600
CMD ["python", "-m", "sparkflow", "serve", "--host", "0.0.0.0", "--port", "8600"]
```

启动容器：
```bash
docker run -p 8600:8600 sparkflow-api:latest
```

## API 端点

### 1. 健康检查

```
GET /api/health
```

检查 API 服务是否正常运行。

**响应示例（200 OK）：**
```json
{
  "status": "ok",
  "service": "sparkflow-review-api"
}
```

---

### 2. 评审规则审查

```
POST /api/review-audit
```

基于评审意见目录生成评审规则，对图纸执行审查并输出评审报告。

**请求体（JSON）：**

```json
{
  "drawing_path": "D:/path/to/file.dwg",
  "review_dir": "D:/path/to/评审意见/",
  "out_dir": "D:/path/to/output/",
  "project_code": "030451DY26030001",
  "dwg_backend": "auto",
  "dxf_backend": "auto",
  "dwg_converter": "path/to/ODAFileConverter.exe",
  "dwg_timeout": 300,
  "level": 3,
  "topo_tol": 1.0,
  "selection": "auto",
  "graph": "electrical",
  "skip_sparkflow_audit": false,
  "ruleset": "D:/path/to/ruleset"
}
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `drawing_path` | string | ✅ | - | 图纸文件路径（.dwg/.dxf） |
| `review_dir` | string | ✅ | - | 评审意见目录 |
| `out_dir` | string | ❌ | `"out"` | 输出目录 |
| `project_code` | string | ❌ | - | 工程编号 |
| `dwg_backend` | string | ❌ | `"auto"` | DWG 转换后端：`auto`, `cli`, `autocad` |
| `dxf_backend` | string | ❌ | `"auto"` | DXF 解析后端：`ascii`, `ezdxf`, `auto` |
| `dwg_converter` | string | ❌ | - | DWG 转 DXF 转换器路径 |
| `dwg_timeout` | number | ❌ | - | DWG 转换超时（秒） |
| `level` | number | ❌ | `3` | 审图深度等级：1(图元), 2(设备), 3(拓扑+规则) |
| `topo_tol` | number | ❌ | `1.0` | 拓扑吸附容差 |
| `selection` | string | ❌ | `"auto"` | 图纸筛选策略 |
| `graph` | string | ❌ | `"electrical"` | 图类型 |
| `skip_sparkflow_audit` | boolean | ❌ | `false` | 跳过通用审图，仅执行评审规则审查 |
| `ruleset` | string | ❌ | - | 规则库目录路径 |
| `wire_filter` | object | ❌ | - | 导线过滤配置（见下表） |

**`wire_filter` 配置示例：**
```json
{
  "wire_filter": {
    "include_layers": ["0"],
    "exclude_layers": [],
    "include_linetypes": [],
    "exclude_linetypes": ["dashed"],
    "min_length": 0.0
  }
}
```

**响应示例（200 OK）：**

```json
{
  "success": true,
  "data": {
    "run_dir": "D:/path/to/output/20260415T120000Z",
    "drawing_info_json": "D:/path/to/output/20260415T120000Z/drawing_info.json",
    "review_rules_json": "D:/path/to/output/20260415T120000Z/review_rules.json",
    "review_report_json": "D:/path/to/output/20260415T120000Z/review_report.json",
    "review_report_md": "D:/path/to/output/20260415T120000Z/review_report.md",
    "sparkflow_report_json": "D:/path/to/output/20260415T120000Z/report.json",
    "sparkflow_report_md": "D:/path/to/output/20260415T120000Z/report.md",
    "review_report": {
      "created_at": "2026-04-15T12:00:00+00:00",
      "rules": [
        {
          "rule_id": "design.naming_consistency",
          "status": "passed",
          "message": "工程名称一致"
        },
        {
          "rule_id": "design.smart_device_count",
          "status": "passed",
          "message": "智能化设备数量满足要求"
        }
      ]
    }
  }
}
```

**错误响应示例（422 Unprocessable Entity）：**

```json
{
  "success": false,
  "errors": [
    "图纸文件不存在: D:/nonexist.dwg",
    "评审意见目录不存在: D:/nonexist"
  ]
}
```

---

### 3. 完整复审流程

```
POST /api/review-pipeline
```

执行完整复审流程，包括：
1. 评审规则审查
2. 图框识别与拆分
3. 单页文本提取
4. 整改问题清单生成

**请求体：** 同 `/api/review-audit`

**响应示例（200 OK）：**

```json
{
  "success": true,
  "data": {
    "run_dir": "D:/path/to/output/20260415T120000Z",
    "drawing_info_json": "...",
    "review_rules_json": "...",
    "review_report_json": "...",
    "review_report_md": "...",
    "sparkflow_report_json": "...",
    "split_manifest_json": "D:/path/to/output/20260415T120000Z/split/manifest.json",
    "rectification_checklist_md": "D:/path/to/output/20260415T120000Z/整改问题清单.md",
    "rectification_checklist_json": "D:/path/to/output/20260415T120000Z/整改问题清单.json",
    "review_report": { ... },
    "rectification_checklist": {
      "created_at": "2026-04-15T12:00:00+00:00",
      "issues": [
        {
          "page": 1,
          "category": "design",
          "issue": "工程名称与图框不一致",
          "severity": "error",
          "action": "修正设计说明书中工程名称"
        }
      ]
    }
  }
}
```

---

## 错误处理

### 常见错误码

| 状态码 | 场景 | 响应示例 |
|--------|------|---------|
| `200` | 请求成功 | `{"success": true, "data": {...}}` |
| `400` | 请求格式错误（无效 JSON） | `{"error": "无效的 JSON 格式。"}` |
| `404` | 端点不存在 | `{"error": "未知端点: /api/unknown"}` |
| `422` | 校验失败（字段缺失、文件不存在） | `{"success": false, "errors": [...]}` |
| `500` | 内部错误 | `{"success": false, "error": "内部错误: ..."}` |

### 校验错误示例

如果请求缺少必填字段或文件不存在，API 返回 `422` 并列出所有错误：

```json
{
  "success": false,
  "errors": [
    "缺少必填字段: drawing_path",
    "缺少必填字段: review_dir"
  ]
}
```

---

## 使用示例

### cURL 调用

```bash
# 健康检查
curl -s http://localhost:8600/api/health | jq .

# 评审规则审查
curl -s -X POST http://localhost:8600/api/review-audit \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/drawings/project01.dwg",
    "review_dir": "D:/reviews/项目01/",
    "out_dir": "D:/outputs/",
    "project_code": "PRJ001"
  }' | jq .

# 完整复审流程
curl -s -X POST http://localhost:8600/api/review-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_path": "D:/drawings/project01.dwg",
    "review_dir": "D:/reviews/项目01/",
    "out_dir": "D:/outputs/"
  }' | jq .
```

### Python 客户端

```python
import requests
import json

BASE_URL = "http://localhost:8600/api"

# 健康检查
resp = requests.get(f"{BASE_URL}/health")
print(resp.json())  # {'status': 'ok', 'service': 'sparkflow-review-api'}

# 评审规则审查
payload = {
    "drawing_path": "D:/drawings/project01.dwg",
    "review_dir": "D:/reviews/项目01/",
    "out_dir": "D:/outputs/",
    "project_code": "PRJ001"
}

resp = requests.post(f"{BASE_URL}/review-audit", json=payload)
if resp.status_code == 200:
    result = resp.json()
    if result["success"]:
        print(f"审图完成，报告保存在: {result['data']['review_report_json']}")
        print(f"审查结果: {result['data']['review_report']}")
    else:
        print(f"错误: {result['error']}")
else:
    print(f"HTTP 错误: {resp.status_code} - {resp.text}")
```

### JavaScript 客户端

```javascript
const BASE_URL = "http://localhost:8600/api";

// 健康检查
fetch(`${BASE_URL}/health`)
  .then(r => r.json())
  .then(d => console.log(d));

// 评审规则审查
const payload = {
  drawing_path: "D:/drawings/project01.dwg",
  review_dir: "D:/reviews/项目01/",
  out_dir: "D:/outputs/",
  project_code: "PRJ001"
};

fetch(`${BASE_URL}/review-audit`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload)
})
  .then(r => r.json())
  .then(d => {
    if (d.success) {
      console.log("审图完成:", d.data);
    } else {
      console.error("错误:", d.error || d.errors);
    }
  });
```

### HTTP 客户端配置（Postman/Insomnia）

**集合名称：** SparkFlow Review API

**环境变量：**
```json
{
  "base_url": "http://localhost:8600/api",
  "drawing_path": "D:/drawings/project01.dwg",
  "review_dir": "D:/reviews/项目01/",
  "out_dir": "D:/outputs/"
}
```

**请求 1：健康检查**
- Method: `GET`
- URL: `{{base_url}}/health`

**请求 2：评审规则审查**
- Method: `POST`
- URL: `{{base_url}}/review-audit`
- Body (raw JSON):
```json
{
  "drawing_path": "{{drawing_path}}",
  "review_dir": "{{review_dir}}",
  "out_dir": "{{out_dir}}"
}
```

---

## 性能与限制

### 性能指标

- 单图审图：取决于图纸复杂度和 DWG 转换时间
  - 简单图纸（<100KB）：3-10 秒
  - 复杂图纸（>500KB）：30-120 秒
  - DWG 转换开销：10-60 秒（取决于转换器选择）

- 并发处理：单服务实例建议 1-3 个并发请求

### 已知限制

- 无请求队列机制（高并发需求建议使用负载均衡）
- 无认证/授权机制（生产环境建议使用 API Gateway）
- DWG 支持依赖 `ODA File Converter` 或 `AutoCAD` 后端
- 长时间运行的图纸处理可能导致超时（建议调整 `dwg_timeout`）

---

## 生产部署建议

### 1. 使用 WSGI 应用服务器

将 `server.py` 改造为 WSGI 兼容后，可使用 Gunicorn/uWSGI：

```bash
gunicorn -w 4 -b 0.0.0.0:8600 sparkflow.server:app
```

### 2. API Gateway / 反向代理

使用 Nginx/Apache 作为反向代理：

```nginx
server {
    listen 80;
    server_name review-api.example.com;

    location / {
        proxy_pass http://localhost:8600;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
```

### 3. 监控与日志

- 监听 stderr 输出（API 日志）
- 建议配置日志聚合（ELK Stack / Splunk）
- 监控磁盘空间（输出目录）

### 4. 安全建议

- 不要直接暴露 API 到互联网（使用 VPN/内网）
- 考虑添加 API 密钥认证
- 限制输出目录权限
- 使用 HTTPS（通过 API Gateway 或 SSL 终止）

---

## 集成示例

### 与 Web 前端集成

前端表单提交审图请求：

```html
<form id="reviewForm">
  <input type="file" id="drawingFile" accept=".dwg,.dxf" required>
  <input type="file" id="reviewDirFile" webkitdirectory directory required>
  <button type="submit">提交审图</button>
</form>

<div id="result"></div>

<script>
document.getElementById('reviewForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  // 需要后端辅助上传文件
  const formData = new FormData(e.target);

  const response = await fetch('http://localhost:8600/api/review-pipeline', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      drawing_path: '/uploaded/file.dwg',
      review_dir: '/uploaded/review/',
      out_dir: '/outputs/'
    })
  });

  const result = await response.json();
  document.getElementById('result').innerHTML =
    `<pre>${JSON.stringify(result, null, 2)}</pre>`;
});
</script>
```

### 与 CI/CD 流程集成

GitHub Actions 示例：

```yaml
name: CAD Review Pipeline

on:
  push:
    paths:
      - 'drawings/**'

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start SparkFlow API
        run: |
          pip install -e .
          python -m sparkflow serve &
          sleep 3

      - name: Submit review
        run: |
          curl -X POST http://localhost:8600/api/review-pipeline \
            -H "Content-Type: application/json" \
            -d '{
              "drawing_path": "drawings/project.dwg",
              "review_dir": "reviews/",
              "out_dir": "outputs/"
            }'

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: review-results
          path: outputs/
```

---

## 故障排除

### API 无响应

1. 检查服务是否启动：`curl http://localhost:8600/api/health`
2. 检查防火墙设置
3. 查看 stderr 输出是否有错误信息

### 请求返回 422 错误

- 确认 `drawing_path` 和 `review_dir` 存在且路径正确
- 注意 Windows 路径要使用 `/` 或 `\\` 转义

### DWG 转换超时

- 增加 `dwg_timeout` 参数（秒）
- 检查 `ODA File Converter` 是否正常工作
- 简化图纸或拆分为多个小文件

### 磁盘空间不足

- 清理 `out_dir` 中的旧运行结果
- 检查报告文件大小（特别是大型数据集）

---

## API 更新日志

### v0.2.0（当前）

- ✅ 新增 `POST /api/review-audit` — 评审规则审查
- ✅ 新增 `POST /api/review-pipeline` — 完整复审流程
- ✅ 新增 `GET /api/health` — 健康检查
- ✅ 自动参数校验与详细错误提示
- ✅ CORS 支持
- ✅ 报告内容内联返回
