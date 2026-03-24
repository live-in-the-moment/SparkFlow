from __future__ import annotations

from pathlib import Path

from .errors import CadParseError


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
        try:
            app = win32com.client.DispatchEx("AutoCAD.Application")
        except Exception:
            app = win32com.client.Dispatch("AutoCAD.Application")

        try:
            app.Visible = False
        except Exception:
            pass

        doc = app.Documents.Open(str(dwg_path))
        try:
            doc.SaveAs(str(out_path))
        finally:
            try:
                doc.Close(False)
            except Exception:
                pass
        try:
            app.Quit()
        except Exception:
            pass
    except Exception as e:
        raise CadParseError(f"AutoCAD COM 转换失败：{e}") from e

    if not out_path.exists():
        raise CadParseError("AutoCAD COM 转换失败：未生成输出 DXF 文件。")
    if out_path.stat().st_size <= 0:
        raise CadParseError("AutoCAD COM 转换失败：输出 DXF 为空文件。")
    return out_path

