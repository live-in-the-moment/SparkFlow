"""SparkFlow REST API 审图服务。

使用 Python 标准库实现轻量级 HTTP 服务器，无额外依赖。
通过 POST 请求提交评审意见文件路径和图纸路径，自动执行审图核查并返回结果。

启动方式::

    sparkflow serve --port 8600

API 端点::

    GET  /api/health             健康检查
    POST /api/review-audit       执行评审规则审查
    POST /api/review-pipeline    执行完整复审流程（含图框拆分 + 整改清单）
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .cad.parse import CadParseOptions
from .model.build_options import model_build_options_from_dict
from .review import review_audit
from .review_workflow import review_pipeline


# ---------------------------------------------------------------------------
# 请求体校验
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("drawing_path", "review_dir")


def _validate_request(body: dict[str, Any]) -> list[str]:
    """返回错误消息列表，空列表表示校验通过。"""
    errors: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in body or not str(body[field]).strip():
            errors.append(f"缺少必填字段: {field}")
    if "drawing_path" in body:
        p = Path(str(body["drawing_path"]))
        if not p.exists():
            errors.append(f"图纸文件不存在: {body['drawing_path']}")
    if "review_dir" in body:
        p = Path(str(body["review_dir"]))
        if not p.exists():
            errors.append(f"评审意见目录不存在: {body['review_dir']}")
        elif not p.is_dir():
            errors.append(f"评审意见路径不是目录: {body['review_dir']}")
    return errors


# ---------------------------------------------------------------------------
# 公共辅助
# ---------------------------------------------------------------------------

def _parse_dwg_converter_cmd(raw: str) -> list[str] | None:
    cmd_str = (raw or "").strip()
    if not cmd_str:
        return None
    unquoted = cmd_str[1:-1] if len(cmd_str) >= 2 and cmd_str[0] == '"' and cmd_str[-1] == '"' else cmd_str
    candidate = Path(unquoted)
    if candidate.exists():
        return [str(candidate)]
    parsed = shlex.split(cmd_str, posix=False)
    if len(parsed) == 1:
        token = parsed[0]
        if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
            return [token[1:-1]]
    return parsed


def _build_parse_options(body: dict[str, Any]) -> CadParseOptions:
    cmd_str = str(body.get("dwg_converter", "")).strip() or os.environ.get("SPARKFLOW_DWG2DXF_CMD", "").strip()
    dwg_cmd = _parse_dwg_converter_cmd(cmd_str)
    return CadParseOptions(
        dwg_backend=body.get("dwg_backend", "auto"),
        dwg_converter_cmd=dwg_cmd,
        dwg_timeout_sec=body.get("dwg_timeout", None),
        dxf_backend=body.get("dxf_backend", "auto"),
        topology_tol=body.get("topo_tol", 1.0),
    )


def _build_model_options(body: dict[str, Any]):
    wire_filter = body.get("wire_filter")
    if wire_filter and isinstance(wire_filter, dict):
        return model_build_options_from_dict({"wire_filter": wire_filter})
    return None


def _json_response(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# 核心处理函数
# ---------------------------------------------------------------------------

def _handle_review_audit(body: dict[str, Any]) -> dict[str, Any]:
    drawing_path = Path(str(body["drawing_path"]))
    review_dir = Path(str(body["review_dir"]))
    out_dir = Path(str(body.get("out_dir", "out")))
    project_code = body.get("project_code") or None
    ruleset_dir = Path(body["ruleset"]) if body.get("ruleset") else None
    skip_audit = body.get("skip_sparkflow_audit", False)

    output = review_audit(
        drawing_path,
        review_dir,
        out_dir,
        project_code=project_code,
        parse_options=_build_parse_options(body),
        level=body.get("level", 3),
        model_options=_build_model_options(body),
        ruleset_dir=ruleset_dir,
        selection_mode=body.get("selection", "auto"),
        graph=body.get("graph", "electrical"),
        include_sparkflow_audit=not skip_audit,
    )

    result: dict[str, Any] = {
        "run_dir": str(output.run_dir),
        "drawing_info_json": str(output.drawing_info_json_path),
        "review_rules_json": str(output.review_rules_json_path),
        "review_report_json": str(output.review_report_json_path),
        "review_report_md": str(output.review_report_md_path),
    }
    if output.sparkflow_report_json_path:
        result["sparkflow_report_json"] = str(output.sparkflow_report_json_path)
    if output.sparkflow_report_md_path:
        result["sparkflow_report_md"] = str(output.sparkflow_report_md_path)

    # 读取 review_report JSON 内联返回
    report_json_path = output.review_report_json_path
    if report_json_path.exists():
        result["review_report"] = json.loads(report_json_path.read_text(encoding="utf-8"))

    return result


def _handle_review_pipeline(body: dict[str, Any]) -> dict[str, Any]:
    drawing_path = Path(str(body["drawing_path"]))
    review_dir = Path(str(body["review_dir"]))
    out_dir = Path(str(body.get("out_dir", "out")))
    project_code = body.get("project_code") or None
    ruleset_dir = Path(body["ruleset"]) if body.get("ruleset") else None
    skip_audit = body.get("skip_sparkflow_audit", False)

    output = review_pipeline(
        drawing_path,
        review_dir,
        out_dir,
        project_code=project_code,
        parse_options=_build_parse_options(body),
        level=body.get("level", 3),
        model_options=_build_model_options(body),
        ruleset_dir=ruleset_dir,
        selection_mode=body.get("selection", "auto"),
        graph=body.get("graph", "electrical"),
        include_sparkflow_audit=not skip_audit,
    )

    result: dict[str, Any] = {
        "run_dir": str(output.run_dir),
        "drawing_info_json": str(output.drawing_info_json_path),
        "review_rules_json": str(output.review_rules_json_path),
        "review_report_json": str(output.review_report_json_path),
        "review_report_md": str(output.review_report_md_path),
        "split_manifest_json": str(output.split_manifest_json_path),
        "rectification_checklist_md": str(output.rectification_checklist_md_path),
        "rectification_checklist_json": str(output.rectification_checklist_json_path),
    }
    if output.sparkflow_report_json_path:
        result["sparkflow_report_json"] = str(output.sparkflow_report_json_path)
    if output.sparkflow_report_md_path:
        result["sparkflow_report_md"] = str(output.sparkflow_report_md_path)

    # 读取核心报告内联返回
    for key in ("review_report_json", "rectification_checklist_json"):
        p = Path(result[key])
        if p.exists():
            result[key.replace("_json", "")] = json.loads(p.read_text(encoding="utf-8"))

    return result


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class SparkFlowAPIHandler(BaseHTTPRequestHandler):
    """SparkFlow 审图 REST API 请求处理器。"""

    server_version = "SparkFlowAPI/1.0"

    def _send_json(self, status: int, obj: Any) -> None:
        payload = _json_response(obj)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # -- CORS preflight --
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # -- GET --
    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(200, {"status": "ok", "service": "sparkflow-review-api"})
        else:
            self._send_json(404, {"error": f"未知端点: {self.path}"})

    # -- POST --
    def do_POST(self) -> None:
        route_map = {
            "/api/review-audit": _handle_review_audit,
            "/api/review-pipeline": _handle_review_pipeline,
        }

        handler = route_map.get(self.path)
        if handler is None:
            self._send_json(404, {"error": f"未知端点: {self.path}"})
            return

        try:
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "请求体不能为空，需提交 JSON 数据。"})
                return

            errors = _validate_request(body)
            if errors:
                self._send_json(422, {"success": False, "errors": errors})
                return

            result = handler(body)
            self._send_json(200, {"success": True, "data": result})

        except json.JSONDecodeError:
            self._send_json(400, {"error": "无效的 JSON 格式。"})
        except FileNotFoundError as exc:
            self._send_json(404, {"success": False, "error": str(exc)})
        except NotADirectoryError as exc:
            self._send_json(422, {"success": False, "error": str(exc)})
        except ValueError as exc:
            self._send_json(422, {"success": False, "error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            self._send_json(500, {"success": False, "error": f"内部错误: {exc}"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[SparkFlow API] {self.address_string()} - {format % args}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 启动函数
# ---------------------------------------------------------------------------

def run_server(host: str = "0.0.0.0", port: int = 8600) -> None:
    """启动 SparkFlow 审图 REST API 服务。"""
    server = HTTPServer((host, port), SparkFlowAPIHandler)
    print(f"SparkFlow 审图 API 服务已启动: http://{host}:{port}", file=sys.stderr)
    print(f"  POST /api/review-audit       评审规则审查", file=sys.stderr)
    print(f"  POST /api/review-pipeline    完整复审流程", file=sys.stderr)
    print(f"  GET  /api/health             健康检查", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。", file=sys.stderr)
        server.server_close()
