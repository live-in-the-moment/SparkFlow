from __future__ import annotations

import time
from pathlib import Path

from .errors import CadParseError

_AC_R15_DXF = 13


def convert_dwg_to_dxf_via_autocad(dwg_path: Path, out_path: Path) -> Path:
    dwg_path = dwg_path.resolve()
    out_path = out_path.resolve()
    if not dwg_path.exists():
        raise FileNotFoundError(str(dwg_path))

    try:
        import win32com.client  # type: ignore
    except Exception as e:
        raise CadParseError("AutoCAD COM 不可用：缺少 pywin32（可尝试安装 pywin32）。") from e

    try:
        app = _retry_autocad_call(lambda: _dispatch_autocad(win32com.client))

        try:
            app.Visible = False
        except Exception:
            pass

        doc = _retry_autocad_call(lambda: app.Documents.Open(str(dwg_path)))
        try:
            _retry_autocad_call(lambda: doc.SaveAs(str(out_path), _AC_R15_DXF))
        finally:
            try:
                _retry_autocad_call(lambda: doc.Close(False))
            except Exception:
                pass
        try:
            _retry_autocad_call(lambda: app.Quit())
        except Exception:
            pass
    except Exception as e:
        raise CadParseError(f"AutoCAD COM 转换失败：{e}") from e

    _wait_for_output(out_path)
    if not out_path.exists():
        raise CadParseError("AutoCAD COM 转换失败：未生成输出 DXF 文件。")
    if out_path.stat().st_size <= 0:
        raise CadParseError("AutoCAD COM 转换失败：输出 DXF 为空文件。")
    return out_path


def _dispatch_autocad(client):
    try:
        return client.DispatchEx("AutoCAD.Application")
    except Exception:
        return client.Dispatch("AutoCAD.Application")


def _retry_autocad_call(fn, *, retries: int = 8, delay_sec: float = 1.0):
    last_error = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if not _is_retryable_autocad_error(exc) or attempt == retries - 1:
                raise
            time.sleep(delay_sec * (attempt + 1))
    if last_error is not None:
        raise last_error


def _is_retryable_autocad_error(exc: Exception) -> bool:
    text = str(exc)
    return "-2147418111" in text or "被呼叫方拒绝接收呼叫" in text or "Call was rejected by callee" in text


def _wait_for_output(out_path: Path, *, timeout_sec: float = 5.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if out_path.exists() and out_path.stat().st_size > 0:
            return
        time.sleep(0.5)
