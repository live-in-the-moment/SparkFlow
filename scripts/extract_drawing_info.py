from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sparkflow.cad.errors import CadParseError, UnsupportedCadFormatError
from sparkflow.cad.parse import CadParseOptions, parse_cad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="extract_drawing_info")
    ap.add_argument("path", type=Path)
    ap.add_argument("--dwg-backend", type=str, default="auto", choices=["auto", "cli", "autocad"])
    ap.add_argument("--dwg-converter", type=str, default="")
    ap.add_argument("--dwg-timeout", type=float, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cmd_str = (args.dwg_converter or "").strip()
    if not cmd_str:
        cmd_str = os.environ.get("SPARKFLOW_DWG2DXF_CMD", "").strip()
    dwg_cmd = shlex.split(cmd_str, posix=False) if cmd_str else None

    opts = CadParseOptions(
        dwg_backend=args.dwg_backend,
        dwg_converter_cmd=dwg_cmd,
        dwg_timeout_sec=args.dwg_timeout,
    )

    try:
        parsed = parse_cad(args.path, options=opts)
    except (UnsupportedCadFormatError, CadParseError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 2

    ents = parsed.entities
    kinds = Counter(e.kind for e in ents)
    layers = Counter((e.props.get("gc_8") or "").strip() for e in ents if e.props.get("gc_8"))

    texts: list[str] = []
    for e in ents:
        if e.kind in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            s = e.props.get("gc_1") or e.props.get("gc_3")
            if s:
                t = str(s).strip()
                if t:
                    texts.append(t)
    unique_texts = sorted(set(texts))

    blocks: list[str] = []
    for e in ents:
        if e.kind == "INSERT":
            bn = e.props.get("gc_2")
            if bn:
                t = str(bn).strip()
                if t:
                    blocks.append(t)
    unique_blocks = sorted(set(blocks))

    model_candidates = sorted(
        {t for t in unique_texts if _looks_like_model(t)},
        key=lambda s: (len(s), s),
    )

    bbox = _compute_bbox(ents)

    info = {
        "input_path": str(args.path.resolve()),
        "parser_id": parsed.parser_id,
        "entity_count": len(ents),
        "kinds": dict(kinds),
        "layers": {k: v for k, v in layers.items() if k},
        "bbox": bbox,
        "unique_blocks": unique_blocks,
        "unique_texts": unique_texts,
        "model_candidates": model_candidates,
    }

    out_path = args.out
    if out_path is None:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./+\\-]{2,}$")


def _looks_like_model(s: str) -> bool:
    s = s.strip()
    if len(s) < 3 or len(s) > 80:
        return False
    if " " in s or "\t" in s:
        return False
    if _MODEL_RE.match(s) is None:
        return False
    return any(ch.isdigit() for ch in s) and any(ch.isalpha() for ch in s)


def _compute_bbox(ents) -> dict | None:
    xs: list[float] = []
    ys: list[float] = []
    for e in ents:
        for xk, yk in (("gc_10", "gc_20"), ("gc_11", "gc_21")):
            sx = e.props.get(xk)
            sy = e.props.get(yk)
            if sx is None or sy is None:
                continue
            try:
                xs.append(float(sx))
                ys.append(float(sy))
            except ValueError:
                pass
    if not xs or not ys:
        return None
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


if __name__ == "__main__":
    raise SystemExit(main())
