from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import CadParseError


@dataclass(frozen=True)
class DwgConvertOptions:
    converter_cmd: list[str]
    work_dir: Path | None = None
    timeout_sec: float | None = 120.0


def convert_dwg_to_dxf(dwg_path: Path, *, options: DwgConvertOptions) -> Path:
    dwg_path = dwg_path.resolve()
    if not dwg_path.exists():
        raise FileNotFoundError(str(dwg_path))

    work_dir = options.work_dir
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix='sparkflow_dwg2dxf_'))
    else:
        work_dir.mkdir(parents=True, exist_ok=True)

    out_path = work_dir / (dwg_path.stem + '.dxf')

    template = [_strip_wrapping_quotes(arg) for arg in options.converter_cmd]
    if any('{in}' in arg or '{out}' in arg for arg in template):
        cmd = [arg.replace('{in}', str(dwg_path)).replace('{out}', str(out_path)) for arg in template]
    else:
        cmd = template + [str(dwg_path), str(out_path)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=options.timeout_sec,
        )
    except subprocess.TimeoutExpired:
        raise CadParseError(f'DWG 转 DXF 超时（>{options.timeout_sec}s）。')
    except OSError as exc:
        raise CadParseError(f'DWG 转换器启动失败：{exc}') from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or '').strip()
        detail = f'：{msg}' if msg else ''
        raise CadParseError(f'DWG 转 DXF 失败（exit={proc.returncode}）{detail}')

    if not out_path.exists():
        raise CadParseError('DWG 转 DXF 失败：未生成输出 DXF 文件。')
    if out_path.stat().st_size <= 0:
        raise CadParseError('DWG 转 DXF 失败：输出 DXF 为空文件。')

    return out_path


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
