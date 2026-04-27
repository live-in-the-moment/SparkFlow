from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CATALOG_FILENAMES = ('wire_filter.json', 'device_templates.json')
_EMBEDDED_DEVICE_TEMPLATES_JSON = r'''
[
  {
    "device_type": "breaker",
    "block_name": "BKR*",
    "match_mode": "glob",
    "text_keywords": ["断路器", "隔离开关", "熔断器式隔离开关", "负荷开关", "自动空气开关", "复合开关"],
    "label_globs": ["*QF*", "*QS*"],
    "terminals": [
      {"name": "line_in", "x": -10.0, "y": 0.0},
      {"name": "line_out", "x": 10.0, "y": 0.0}
    ],
    "footprint_radius": 18.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "text_group_radius": 8.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "breaker",
    "block_name": "BREAKER*",
    "match_mode": "glob",
    "terminals": [
      {"name": "line_in", "x": -10.0, "y": 0.0},
      {"name": "line_out", "x": 10.0, "y": 0.0}
    ],
    "footprint_radius": 18.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "breaker",
    "block_name": "A$C22066BF2",
    "match_mode": "equals",
    "label_globs": ["*QF*", "*QS*"],
    "footprint_radius": 18.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "text_group_radius": 6.0,
    "terminal_layout": "vertical"
  },
  {
    "device_type": "transformer",
    "block_name": "TR*",
    "match_mode": "glob",
    "text_keywords": ["变压器", "主变", "电流互感器"],
    "label_globs": ["TA*"],
    "terminals": [
      {"name": "hv", "x": -12.0, "y": 0.0},
      {"name": "lv", "x": 12.0, "y": 0.0}
    ],
    "footprint_radius": 24.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "text_group_radius": 10.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "transformer",
    "block_name": "TRANS*",
    "match_mode": "glob",
    "terminals": [
      {"name": "hv", "x": -12.0, "y": 0.0},
      {"name": "lv", "x": 12.0, "y": 0.0}
    ],
    "footprint_radius": 24.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "transformer",
    "block_name": "A$C3A3E583B",
    "match_mode": "equals",
    "label_globs": ["TA*"],
    "footprint_radius": 16.0,
    "min_terminals": 2,
    "max_terminals": 2,
    "text_group_radius": 6.0,
    "terminal_layout": "vertical"
  },
  {
    "device_type": "switchgear_unit",
    "block_name": "DK*",
    "match_mode": "glob",
    "text_keywords": ["开关柜", "进线柜", "出线柜", "联络柜", "进线总柜"],
    "label_globs": ["DK*", "*DK*"],
    "terminals": [
      {"name": "left", "x": -12.0, "y": 0.0},
      {"name": "right", "x": 12.0, "y": 0.0}
    ],
    "footprint_radius": 26.0,
    "min_terminals": 2,
    "max_terminals": 4,
    "text_group_radius": 12.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "switchgear_unit",
    "block_name": "DP*",
    "match_mode": "glob",
    "text_keywords": ["配电箱", "综合配电箱", "低压柜"],
    "label_globs": ["DP*", "*DP*"],
    "terminals": [
      {"name": "left", "x": -12.0, "y": 0.0},
      {"name": "right", "x": 12.0, "y": 0.0}
    ],
    "footprint_radius": 26.0,
    "min_terminals": 2,
    "max_terminals": 4,
    "text_group_radius": 12.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "switchgear_unit",
    "text_keywords": ["进线单元", "出线单元", "计量单元", "无功补偿单元", "进线总柜", "联络柜", "出线柜", "电容器柜"],
    "terminals": [
      {"name": "line_in", "x": -12.0, "y": 0.0},
      {"name": "line_out", "x": 12.0, "y": 0.0}
    ],
    "footprint_radius": 24.0,
    "min_terminals": 2,
    "max_terminals": 4,
    "text_group_radius": 12.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "cable_branch_box",
    "block_name": "DF*",
    "match_mode": "glob",
    "text_keywords": ["电缆分支箱", "分支箱"],
    "label_globs": ["DF*", "*DF*"],
    "terminals": [
      {"name": "feed", "x": -14.0, "y": 0.0},
      {"name": "branch_a", "x": 14.0, "y": 8.0},
      {"name": "branch_b", "x": 14.0, "y": -8.0},
      {"name": "branch_c", "x": 14.0, "y": 16.0}
    ],
    "footprint_radius": 28.0,
    "min_terminals": 2,
    "max_terminals": 4,
    "text_group_radius": 12.0
  },
  {
    "device_type": "busbar",
    "text_keywords": ["母线"],
    "footprint_radius": 36.0,
    "min_terminals": 2,
    "max_terminals": 8,
    "text_group_radius": 12.0,
    "terminal_layout": "horizontal"
  },
  {
    "device_type": "feeder",
    "text_keywords": ["电缆进线", "电缆出线", "进线回路", "出线回路", "进线侧", "出线侧", "进线", "出线", "馈线"],
    "terminals": [
      {"name": "line", "x": 0.0, "y": 0.0}
    ],
    "footprint_radius": 18.0,
    "min_terminals": 1,
    "max_terminals": 1,
    "text_group_radius": 8.0
  },
  {
    "device_type": "load",
    "text_keywords": ["所用电", "负荷", "用户", "SPD", "浪涌保护器", "避雷器", "电容器", "电能表", "集中器", "配电智能终端", "低压避雷器", "回路状态", "巡检仪", "智能电容补偿", "无功补偿控制器"],
    "label_globs": ["SPD*", "BK*", "C[0-9]*", "FB*"],
    "terminals": [
      {"name": "load", "x": 0.0, "y": 0.0}
    ],
    "footprint_radius": 18.0,
    "min_terminals": 1,
    "max_terminals": 1,
    "text_group_radius": 8.0
  }
]
'''


@dataclass(frozen=True)
class WireFilter:
    include_layers: tuple[str, ...] = ()
    exclude_layers: tuple[str, ...] = ()
    include_linetypes: tuple[str, ...] = ()
    exclude_linetypes: tuple[str, ...] = ()
    min_length: float = 0.0
    exclude_closed_polylines: bool = True
    exclude_internal_device_wires: bool = True
    device_radius_padding: float = 4.0
    exclude_text_dense_wires: bool = True
    text_density_radius: float = 18.0
    text_density_threshold: int = 5
    text_dense_max_length: float = 120.0
    specified_fields: frozenset[str] | None = None


@dataclass(frozen=True)
class TerminalDef:
    name: str | None
    x: float
    y: float


@dataclass(frozen=True)
class TerminalTemplate:
    block_name: str
    match_mode: str = 'equals'
    terminals: tuple[TerminalDef, ...] = ()
    attrib_equals: dict[str, str] | None = None


@dataclass(frozen=True)
class DeviceTemplate:
    device_type: str
    block_name: str | None = None
    match_mode: str = 'equals'
    text_keywords: tuple[str, ...] = ()
    label_globs: tuple[str, ...] = ()
    terminals: tuple[TerminalDef, ...] = ()
    attrib_equals: dict[str, str] | None = None
    footprint_radius: float = 18.0
    min_terminals: int = 2
    max_terminals: int | None = None
    text_group_radius: float = 10.0
    terminal_layout: str = 'auto'


@dataclass(frozen=True)
class ModelBuildOptions:
    wire_filter: WireFilter | None = None
    terminal_templates: tuple[TerminalTemplate, ...] = ()
    device_templates: tuple[DeviceTemplate, ...] = ()


def builtin_device_templates() -> tuple[DeviceTemplate, ...]:
    catalog = load_catalog_model_build_options()
    if catalog is not None and catalog.device_templates:
        return catalog.device_templates
    return _embedded_device_templates()


def default_terminal_templates() -> tuple[TerminalTemplate, ...]:
    templates: list[TerminalTemplate] = []
    for device_template in builtin_device_templates():
        if not device_template.block_name or not device_template.terminals:
            continue
        templates.append(
            TerminalTemplate(
                block_name=device_template.block_name,
                match_mode=device_template.match_mode,
                terminals=device_template.terminals,
                attrib_equals=device_template.attrib_equals,
            )
        )
    return tuple(templates)


def default_model_build_options() -> ModelBuildOptions:
    fallback = ModelBuildOptions(
        wire_filter=WireFilter(
            exclude_layers=('DIM', '标注', '文字', '图框', '标题', '尺寸', '中心线'),
            min_length=3.0,
            exclude_closed_polylines=True,
            exclude_internal_device_wires=True,
            device_radius_padding=4.0,
            exclude_text_dense_wires=True,
            text_density_radius=18.0,
            text_density_threshold=5,
            text_dense_max_length=120.0,
        ),
    )
    catalog = load_catalog_model_build_options()
    merged = merge_model_build_options(fallback, catalog) or fallback
    if merged.device_templates and not merged.terminal_templates:
        synthesized = _terminal_templates_from_device_templates(merged.device_templates)
        merged = ModelBuildOptions(
            wire_filter=merged.wire_filter,
            terminal_templates=synthesized,
            device_templates=merged.device_templates,
        )
    return merged


def load_catalog_model_build_options(catalog_dir: Path | None = None) -> ModelBuildOptions | None:
    root = catalog_dir or (Path(__file__).resolve().parents[2] / 'catalog')
    if not root.exists() or not root.is_dir():
        return None
    merged: ModelBuildOptions | None = None
    for name in _CATALOG_FILENAMES:
        path = root / name
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            continue
        options = model_build_options_from_dict(payload)
        merged = merge_model_build_options(merged, options)
    return merged


def _embedded_device_templates() -> tuple[DeviceTemplate, ...]:
    # Source of truth is catalog/device_templates.json. Keep this embedded
    # fallback in lockstep with that file so packaged/runtime use stays aligned.
    payload = {"device_templates": json.loads(_EMBEDDED_DEVICE_TEMPLATES_JSON)}
    return model_build_options_from_dict(payload).device_templates


def model_build_options_from_dict(d: dict[str, Any] | None) -> ModelBuildOptions:
    if not isinstance(d, dict):
        return ModelBuildOptions()
    wf_raw = d.get('wire_filter')
    wf = None
    if isinstance(wf_raw, dict):
        wf = WireFilter(
            include_layers=tuple(str(x) for x in (wf_raw.get('include_layers') or ()) if isinstance(x, (str, int, float))),
            exclude_layers=tuple(str(x) for x in (wf_raw.get('exclude_layers') or ()) if isinstance(x, (str, int, float))),
            include_linetypes=tuple(str(x) for x in (wf_raw.get('include_linetypes') or ()) if isinstance(x, (str, int, float))),
            exclude_linetypes=tuple(str(x) for x in (wf_raw.get('exclude_linetypes') or ()) if isinstance(x, (str, int, float))),
            min_length=float(wf_raw.get('min_length') or 0.0),
            exclude_closed_polylines=bool(wf_raw.get('exclude_closed_polylines', True)),
            exclude_internal_device_wires=bool(wf_raw.get('exclude_internal_device_wires', True)),
            device_radius_padding=float(wf_raw.get('device_radius_padding') or 0.0),
            exclude_text_dense_wires=bool(wf_raw.get('exclude_text_dense_wires', True)),
            text_density_radius=float(wf_raw.get('text_density_radius') or 18.0),
            text_density_threshold=int(wf_raw.get('text_density_threshold') or 5),
            text_dense_max_length=float(wf_raw.get('text_dense_max_length') or 120.0),
            specified_fields=frozenset(str(key) for key in wf_raw.keys()),
        )

    terminal_templates = _parse_terminal_templates(d.get('terminal_templates') or ())
    device_templates = _parse_device_templates(d.get('device_templates') or ())
    if device_templates:
        synthesized_terminals = _terminal_templates_from_device_templates(device_templates)
        if not terminal_templates:
            terminal_templates = synthesized_terminals
    elif terminal_templates:
        device_templates = tuple(
            DeviceTemplate(
                device_type='unknown_component',
                block_name=item.block_name,
                match_mode=item.match_mode,
                terminals=item.terminals,
                attrib_equals=item.attrib_equals,
            )
            for item in terminal_templates
        )

    return ModelBuildOptions(wire_filter=wf, terminal_templates=terminal_templates, device_templates=device_templates)


def merge_model_build_options(base: ModelBuildOptions | None, override: ModelBuildOptions | None) -> ModelBuildOptions | None:
    if base is None:
        return override
    if override is None:
        return base

    wf = _merge_wire_filter(base.wire_filter, override.wire_filter)

    terminal_templates = base.terminal_templates
    if override.terminal_templates:
        terminal_templates = override.terminal_templates

    device_templates = base.device_templates
    if override.device_templates:
        device_templates = override.device_templates

    return ModelBuildOptions(wire_filter=wf, terminal_templates=terminal_templates, device_templates=device_templates)


def _merge_wire_filter(base: WireFilter | None, override: WireFilter | None) -> WireFilter | None:
    if base is None:
        return override
    if override is None:
        return base

    specified = override.specified_fields
    if specified is None:
        return override if override != base else base
    if not specified:
        return base

    field_names = tuple(name for name in WireFilter.__dataclass_fields__ if name != 'specified_fields')
    merged = {
        name: getattr(override, name) if name in specified else getattr(base, name)
        for name in field_names
    }
    return WireFilter(**merged, specified_fields=frozenset(field_names))

def effective_device_templates(options: ModelBuildOptions | None) -> tuple[DeviceTemplate, ...]:
    if options is None:
        return ()
    if options.device_templates:
        return options.device_templates
    if options.terminal_templates:
        return tuple(
            DeviceTemplate(
                device_type='unknown_component',
                block_name=item.block_name,
                match_mode=item.match_mode,
                terminals=item.terminals,
                attrib_equals=item.attrib_equals,
            )
            for item in options.terminal_templates
        )
    return ()


def _parse_terminal_templates(raw: object) -> tuple[TerminalTemplate, ...]:
    templates: list[TerminalTemplate] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            block_name = item.get('block_name')
            if not isinstance(block_name, str) or not block_name.strip():
                continue
            terms = _parse_terminals(item.get('terminals') or ())
            mode = item.get('match_mode')
            match_mode = str(mode) if isinstance(mode, str) and mode.strip() else 'equals'
            attrib_equals = item.get('attrib_equals')
            attrib_eq = None
            if isinstance(attrib_equals, dict):
                attrib_eq = {str(k): str(v) for k, v in attrib_equals.items() if v is not None}
            templates.append(
                TerminalTemplate(
                    block_name=block_name.strip(),
                    match_mode=match_mode,
                    terminals=terms,
                    attrib_equals=attrib_eq,
                )
            )
    return tuple(templates)


def _parse_device_templates(raw: object) -> tuple[DeviceTemplate, ...]:
    templates: list[DeviceTemplate] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            device_type = item.get('device_type')
            if not isinstance(device_type, str) or not device_type.strip():
                continue
            block_name = item.get('block_name')
            normalized_block = block_name.strip() if isinstance(block_name, str) and block_name.strip() else None
            mode = item.get('match_mode')
            match_mode = str(mode) if isinstance(mode, str) and mode.strip() else 'equals'
            attrib_equals = item.get('attrib_equals')
            attrib_eq = None
            if isinstance(attrib_equals, dict):
                attrib_eq = {str(k): str(v) for k, v in attrib_equals.items() if v is not None}
            raw_keywords = item.get('text_keywords') or ()
            text_keywords = tuple(str(x).strip() for x in raw_keywords if isinstance(x, (str, int, float)) and str(x).strip())
            raw_globs = item.get('label_globs') or ()
            label_globs = tuple(str(x).strip() for x in raw_globs if isinstance(x, (str, int, float)) and str(x).strip())
            templates.append(
                DeviceTemplate(
                    device_type=device_type.strip(),
                    block_name=normalized_block,
                    match_mode=match_mode,
                    text_keywords=text_keywords,
                    label_globs=label_globs,
                    terminals=_parse_terminals(item.get('terminals') or ()),
                    attrib_equals=attrib_eq,
                    footprint_radius=float(item.get('footprint_radius') or 18.0),
                    min_terminals=int(item.get('min_terminals') or 0),
                    max_terminals=(int(item['max_terminals']) if item.get('max_terminals') is not None else None),
                    text_group_radius=float(item.get('text_group_radius') or 10.0),
                    terminal_layout=(str(item.get('terminal_layout')).strip() if item.get('terminal_layout') is not None and str(item.get('terminal_layout')).strip() else 'auto'),
                )
            )
    return tuple(templates)


def _parse_terminals(raw: object) -> tuple[TerminalDef, ...]:
    terminals: list[TerminalDef] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            x = item.get('x')
            y = item.get('y')
            if x is None or y is None:
                continue
            try:
                fx = float(x)
                fy = float(y)
            except (TypeError, ValueError):
                continue
            name_raw = item.get('name')
            name = str(name_raw).strip() if isinstance(name_raw, str) and name_raw.strip() else None
            terminals.append(TerminalDef(name=name, x=fx, y=fy))
    return tuple(terminals)


def _terminal_templates_from_device_templates(device_templates: tuple[DeviceTemplate, ...]) -> tuple[TerminalTemplate, ...]:
    out: list[TerminalTemplate] = []
    for item in device_templates:
        if not item.block_name or not item.terminals:
            continue
        out.append(
            TerminalTemplate(
                block_name=item.block_name,
                match_mode=item.match_mode,
                terminals=item.terminals,
                attrib_equals=item.attrib_equals,
            )
        )
    return tuple(out)
