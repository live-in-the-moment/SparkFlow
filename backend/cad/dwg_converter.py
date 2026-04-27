from __future__ import annotations

import os
import shutil
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
    if _looks_like_oda_converter(template):
        return _convert_with_oda_file_converter(dwg_path, out_path, template, timeout_sec=options.timeout_sec)
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


def _looks_like_oda_converter(template: list[str]) -> bool:
    if not template:
        return False
    first = Path(template[0]).name.lower()
    return 'odafileconverter' in first


def _convert_with_oda_file_converter(
    dwg_path: Path,
    out_path: Path,
    template: list[str],
    *,
    timeout_sec: float | None,
) -> Path:
    oda = template[0]
    outver = template[1] if len(template) > 1 and template[1] else 'ACAD2018'
    recursive = template[2] if len(template) > 2 and template[2] else '0'
    audit = template[3] if len(template) > 3 and template[3] else '1'

    src_dir = Path(tempfile.mkdtemp(prefix='sparkflow_oda_in_'))
    dst_dir = Path(tempfile.mkdtemp(prefix='sparkflow_oda_out_'))
    try:
        local_inp = src_dir / 'input.dwg'
        shutil.copy2(dwg_path, local_inp)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            oda,
            str(src_dir),
            str(dst_dir),
            outver,
            'DXF',
            recursive,
            audit,
            local_inp.name,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(Path(oda).parent if Path(oda).exists() else Path.cwd()),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            raise CadParseError(f'DWG 转 DXF 超时（>{timeout_sec}s）。')
        except OSError as exc:
            raise CadParseError(f'DWG 转换器启动失败：{exc}') from exc

        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or '').strip()
            detail = f'：{msg}' if msg else ''
            raise CadParseError(f'DWG 转 DXF 失败（exit={proc.returncode}）{detail}')

        produced = dst_dir / 'input.dxf'
        if not produced.exists():
            produced_candidates = [p for p in dst_dir.rglob('*.dxf') if p.is_file()]
            if produced_candidates:
                exact = [p for p in produced_candidates if p.name.lower() == 'input.dxf']
                produced = exact[0] if exact else produced_candidates[0]
            else:
                msg = (proc.stderr or proc.stdout or '').strip()
                detail = f'；converter_output={msg}' if msg else ''
                raise CadParseError(f'DWG 转 DXF 失败：未生成输出 DXF 文件{detail}')

        shutil.copy2(produced, out_path)
        if not out_path.exists():
            raise CadParseError('DWG 转 DXF 失败：未生成输出 DXF 文件。')
        if out_path.stat().st_size <= 0:
            raise CadParseError('DWG 转 DXF 失败：输出 DXF 为空文件。')
        return out_path
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dst_dir, ignore_errors=True)


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
