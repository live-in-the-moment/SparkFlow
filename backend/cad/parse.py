from __future__ import annotations

import os
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .autocad_com import convert_dwg_to_dxf_via_autocad
from .dwg_converter import DwgConvertOptions, convert_dwg_to_dxf
from .dxf_ascii import parse_ascii_dxf
from .entities import ParsedCad
from .errors import CadParseError
from .errors import UnsupportedCadFormatError


@dataclass(frozen=True)
class CadParseOptions:
    dwg_backend: str | None = None
    dwg_converter_cmd: list[str] | None = None
    dwg_work_dir: Path | None = None
    dwg_timeout_sec: float | None = None
    dxf_backend: str | None = None
    topology_tol: float | None = None


def parse_cad(path: Path, *, options: CadParseOptions | None = None) -> ParsedCad:
    suffix = path.suffix.lower()
    if suffix == '.dxf':
        backend = (options.dxf_backend if options and options.dxf_backend else 'auto').strip().lower()
        return _parse_dxf_with_backend(path, backend=backend)
    if suffix == '.dwg':
        backend = (options.dwg_backend if options and options.dwg_backend else 'auto').strip().lower()
        cmd = _resolve_cli_cmd(options)
        if backend not in {'auto', 'cli', 'autocad'}:
            raise UnsupportedCadFormatError(f'DWG 后端不支持：{backend}')

        if backend == 'cli' or (backend == 'auto' and cmd):
            if not cmd:
                raise UnsupportedCadFormatError(
                    'DWG 暂不支持直接解析。可配置 DWG→DXF 转换器：'
                    '设置环境变量 SPARKFLOW_DWG2DXF_CMD，或在批处理模式中传入 --dwg-converter。'
                    '转换器命令约定：<cmd...> <input.dwg> <output.dxf>；也可用 {in}/{out} 占位符。'
                )
            conv_opts = DwgConvertOptions(
                converter_cmd=list(cmd),
                work_dir=(options.dwg_work_dir if options else None),
            )
            if options is not None and options.dwg_timeout_sec is not None:
                conv_opts = DwgConvertOptions(
                    converter_cmd=conv_opts.converter_cmd,
                    work_dir=conv_opts.work_dir,
                    timeout_sec=options.dwg_timeout_sec,
                )
            dxf_path = convert_dwg_to_dxf(path, options=conv_opts)
            parsed = _parse_dxf_with_backend(dxf_path, backend=(options.dxf_backend if options and options.dxf_backend else 'auto'))
            return _attach_dwg_meta(parsed, source_path=path, dwg_backend='cli', converted_dxf=dxf_path)

        work_dir = (options.dwg_work_dir if options else None)
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix='sparkflow_dwg2dxf_'))
        else:
            work_dir.mkdir(parents=True, exist_ok=True)
        out_path = work_dir / (path.stem + '.dxf')
        try:
            dxf_path = convert_dwg_to_dxf_via_autocad(path, out_path)
        except CadParseError as exc:
            if backend == 'autocad':
                raise
            raise UnsupportedCadFormatError(
                'DWG 暂不支持直接解析，且未检测到可用转换器。'
                '可选择：配置 SPARKFLOW_DWG2DXF_CMD（外部工具），或安装 AutoCAD+pywin32。'
                f' 详情：{exc}'
            ) from exc
        parsed = _parse_dxf_with_backend(dxf_path, backend=(options.dxf_backend if options and options.dxf_backend else 'auto'))
        return _attach_dwg_meta(parsed, source_path=path, dwg_backend='autocad', converted_dxf=dxf_path)
    raise UnsupportedCadFormatError('仅支持 DWG/DXF 文件。')


def _parse_dxf_with_backend(path: Path, *, backend: str) -> ParsedCad:
    backend = (backend or 'auto').strip().lower()
    if backend not in {'ascii', 'ezdxf', 'auto'}:
        raise UnsupportedCadFormatError(f'DXF 后端不支持：{backend}')
    if backend == 'ascii':
        parsed = parse_ascii_dxf(path)
        return ParsedCad(
            parser_id=parsed.parser_id,
            entities=parsed.entities,
            meta={'requested_dxf_backend': 'ascii', 'chosen_dxf_backend': 'ascii', 'parser_id': parsed.parser_id},
        )
    if backend == 'ezdxf':
        from .dxf_ezdxf import parse_ezdxf_dxf

        parsed = parse_ezdxf_dxf(path)
        return ParsedCad(
            parser_id=parsed.parser_id,
            entities=parsed.entities,
            meta={'requested_dxf_backend': 'ezdxf', 'chosen_dxf_backend': 'ezdxf', 'parser_id': parsed.parser_id},
        )

    ascii_err: str | None = None
    ascii_parsed: ParsedCad | None = None
    try:
        ascii_parsed = parse_ascii_dxf(path)
    except CadParseError as exc:
        ascii_err = str(exc)

    if ascii_parsed is not None:
        metrics = _dxf_parse_metrics(ascii_parsed)
        if _dxf_metrics_ok(metrics):
            return ParsedCad(
                parser_id=ascii_parsed.parser_id,
                entities=ascii_parsed.entities,
                meta={
                    'requested_dxf_backend': 'auto',
                    'chosen_dxf_backend': 'ascii',
                    'parser_id': ascii_parsed.parser_id,
                    'auto_reason': 'ascii_metrics_ok',
                    'ascii_metrics': metrics,
                },
            )
        try:
            from .dxf_ezdxf import parse_ezdxf_dxf

            ez = parse_ezdxf_dxf(path)
            return ParsedCad(
                parser_id=ez.parser_id,
                entities=ez.entities,
                meta={
                    'requested_dxf_backend': 'auto',
                    'chosen_dxf_backend': 'ezdxf',
                    'parser_id': ez.parser_id,
                    'auto_reason': 'ascii_metrics_not_ok',
                    'ascii_metrics': metrics,
                    'ezdxf_metrics': _dxf_parse_metrics(ez),
                },
            )
        except CadParseError as exc:
            return ParsedCad(
                parser_id=ascii_parsed.parser_id,
                entities=ascii_parsed.entities,
                meta={
                    'requested_dxf_backend': 'auto',
                    'chosen_dxf_backend': 'ascii',
                    'parser_id': ascii_parsed.parser_id,
                    'auto_reason': 'ascii_metrics_not_ok_and_ezdxf_failed',
                    'ascii_metrics': metrics,
                    'ezdxf_error': str(exc),
                },
            )

    from .dxf_ezdxf import parse_ezdxf_dxf

    ez = parse_ezdxf_dxf(path)
    meta = {
        'requested_dxf_backend': 'auto',
        'chosen_dxf_backend': 'ezdxf',
        'parser_id': ez.parser_id,
        'auto_reason': 'ascii_parse_failed',
        'ezdxf_metrics': _dxf_parse_metrics(ez),
    }
    if ascii_err:
        meta['ascii_error'] = ascii_err
    return ParsedCad(parser_id=ez.parser_id, entities=ez.entities, meta=meta)


def _attach_dwg_meta(parsed: ParsedCad, *, source_path: Path, dwg_backend: str, converted_dxf: Path) -> ParsedCad:
    meta = dict(parsed.meta)
    meta.update(
        {
            'source_format': 'dwg',
            'dwg_backend': dwg_backend,
            'converted_dxf': str(converted_dxf),
            'source_path': str(source_path.resolve()),
        }
    )
    return ParsedCad(parser_id=parsed.parser_id, entities=parsed.entities, meta=meta)


def _resolve_cli_cmd(options: CadParseOptions | None) -> list[str] | None:
    if options is not None and options.dwg_converter_cmd:
        return options.dwg_converter_cmd
    env_cmd = os.environ.get('SPARKFLOW_DWG2DXF_CMD', '').strip()
    if env_cmd:
        return shlex.split(env_cmd, posix=False)
    return None


def _dxf_parse_metrics(parsed: ParsedCad) -> dict[str, int | bool | dict[str, int] | None]:
    entities = parsed.entities
    kinds = {'LINE': 0, 'LWPOLYLINE': 0, 'POLYLINE': 0, 'TEXT': 0, 'MTEXT': 0, 'INSERT': 0}
    has_any_coords = False
    min_x = None
    min_y = None
    max_x = None
    max_y = None
    for entity in entities:
        kind = entity.kind.upper()
        if kind in kinds:
            kinds[kind] += 1
        for xk, yk in (('gc_10', 'gc_20'), ('gc_11', 'gc_21')):
            sx = entity.props.get(xk)
            sy = entity.props.get(yk)
            try:
                x = float(sx) if sx is not None else None
                y = float(sy) if sy is not None else None
            except (TypeError, ValueError):
                x = None
                y = None
            if x is None or y is None:
                continue
            has_any_coords = True
            min_x = x if min_x is None else min(min_x, x)
            min_y = y if min_y is None else min(min_y, y)
            max_x = x if max_x is None else max(max_x, x)
            max_y = y if max_y is None else max(max_y, y)

    bbox_missing = not has_any_coords or min_x is None
    return {
        'entity_count': len(entities),
        'kinds': kinds,
        'has_any_coords': has_any_coords,
        'bbox_missing': bbox_missing,
    }


def _dxf_metrics_ok(metrics: dict[str, object]) -> bool:
    entity_count = int(metrics.get('entity_count') or 0)
    kinds = metrics.get('kinds') if isinstance(metrics.get('kinds'), dict) else {}
    bbox_missing = bool(metrics.get('bbox_missing'))
    has_any_coords = bool(metrics.get('has_any_coords'))

    if entity_count <= 0:
        return False
    if not has_any_coords:
        return False
    if bbox_missing and entity_count >= 100:
        return False
    wires = 0
    if isinstance(kinds, dict):
        wires += int(kinds.get('LINE') or 0)
        wires += int(kinds.get('LWPOLYLINE') or 0)
        wires += int(kinds.get('POLYLINE') or 0)
    if entity_count >= 200 and wires <= 0:
        return False
    return True
