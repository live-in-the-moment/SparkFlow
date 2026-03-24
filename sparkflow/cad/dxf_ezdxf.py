from __future__ import annotations

from pathlib import Path

import ezdxf

from .entities import CadEntity, ParsedCad
from .errors import CadParseError


def parse_ezdxf_dxf(path: Path) -> ParsedCad:
    try:
        doc = ezdxf.readfile(str(path))
    except Exception as e:
        raise CadParseError(f"ezdxf 读取 DXF 失败：{e}") from e

    entities: list[CadEntity] = []
    try:
        space = doc.modelspace()
    except Exception as e:
        raise CadParseError(f"ezdxf 获取模型空间失败：{e}") from e

    for idx, ent in enumerate(space, start=1):
        try:
            kind = ent.dxftype().upper()
        except Exception:
            continue

        entity_id = _entity_id(ent, idx)
        props: dict[str, object] = {}
        layer = getattr(ent.dxf, "layer", None)
        if layer:
            props["gc_8"] = str(layer)
        linetype = getattr(ent.dxf, "linetype", None)
        if linetype:
            props["gc_6"] = str(linetype)

        try:
            if kind == "LINE":
                _set_point(props, "10", "20", ent.dxf.start)
                _set_point(props, "11", "21", ent.dxf.end)
            elif kind == "TEXT":
                _set_point(props, "10", "20", ent.dxf.insert)
                props["gc_1"] = str(ent.dxf.text)
            elif kind == "MTEXT":
                _set_point(props, "10", "20", ent.dxf.insert)
                txt = None
                if hasattr(ent, "plain_text"):
                    try:
                        txt = ent.plain_text()
                    except Exception:
                        txt = None
                if txt is None:
                    txt = getattr(ent.dxf, "text", None)
                if txt is not None:
                    props["gc_1"] = str(txt)
            elif kind == "INSERT":
                _set_point(props, "10", "20", ent.dxf.insert)
                name = getattr(ent.dxf, "name", None)
                if name:
                    props["gc_2"] = str(name)
                rot = getattr(ent.dxf, "rotation", None)
                if rot is not None:
                    props["gc_50"] = str(rot)
                xs = getattr(ent.dxf, "xscale", None)
                ys = getattr(ent.dxf, "yscale", None)
                if xs is not None:
                    props["gc_41"] = str(xs)
                if ys is not None:
                    props["gc_42"] = str(ys)
                attribs = {}
                try:
                    for a in getattr(ent, "attribs", []) or []:
                        tag = getattr(a.dxf, "tag", None)
                        val = getattr(a.dxf, "text", None)
                        if tag and val is not None:
                            attribs[str(tag)] = str(val)
                except Exception:
                    attribs = {}
                if attribs:
                    props["insert_attribs"] = attribs
            elif kind == "LWPOLYLINE":
                pts = list(ent.get_points("xy"))
                if pts:
                    _set_xy(props, "10", "20", pts[0][0], pts[0][1])
                    _set_xy(props, "11", "21", pts[-1][0], pts[-1][1])
                    props["gc_90"] = str(len(pts))
                    props["lwpolyline_xy"] = [(float(x), float(y)) for x, y in pts]
                    try:
                        props["lwpolyline_closed"] = bool(getattr(ent, "closed", False))
                    except Exception:
                        props["lwpolyline_closed"] = False
            elif kind == "POLYLINE":
                pts = []
                try:
                    pts = [(float(x), float(y)) for x, y, *_ in (ent.points() or [])]
                except Exception:
                    pts = []
                if pts:
                    _set_xy(props, "10", "20", pts[0][0], pts[0][1])
                    _set_xy(props, "11", "21", pts[-1][0], pts[-1][1])
                    props["gc_90"] = str(len(pts))
                    props["polyline_xy"] = pts
                    try:
                        props["polyline_closed"] = bool(getattr(ent, "is_closed", False)) or bool(
                            getattr(ent, "closed", False)
                        )
                    except Exception:
                        props["polyline_closed"] = False
            elif kind == "CIRCLE":
                _set_point(props, "10", "20", ent.dxf.center)
                props["gc_40"] = str(ent.dxf.radius)
            elif kind == "ARC":
                _set_point(props, "10", "20", ent.dxf.center)
                props["gc_40"] = str(ent.dxf.radius)
                props["gc_50"] = str(ent.dxf.start_angle)
                props["gc_51"] = str(ent.dxf.end_angle)
            elif kind == "POINT":
                _set_point(props, "10", "20", ent.dxf.location)
            elif kind == "DIMENSION":
                dp = getattr(ent.dxf, "defpoint", None)
                if dp is not None:
                    _set_point(props, "10", "20", dp)
            elif kind == "HATCH":
                pass
        except Exception:
            pass

        entities.append(CadEntity(entity_id=str(entity_id), kind=kind, props=props))

    if not entities:
        raise CadParseError("未能从 DXF 中解析到任何实体。")
    return ParsedCad(parser_id="dxf_ezdxf_v1", entities=tuple(entities))


def _entity_id(ent, fallback: int) -> str:
    handle = getattr(getattr(ent, "dxf", None), "handle", None)
    if handle:
        return str(handle)
    return str(fallback)


def _set_point(props: dict[str, object], x: str, y: str, p) -> None:
    if p is None:
        return
    _set_xy(props, x, y, getattr(p, "x", None), getattr(p, "y", None))


def _set_xy(props: dict[str, object], x: str, y: str, xv, yv) -> None:
    if xv is None or yv is None:
        return
    props[f"gc_{x}"] = str(xv)
    props[f"gc_{y}"] = str(yv)
