from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="summarize_drawing_info")
    ap.add_argument("info_json", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    raw = json.loads(args.info_json.read_text(encoding="utf-8"))
    texts: list[str] = list(raw.get("unique_texts") or [])
    blocks: list[str] = list(raw.get("unique_blocks") or [])

    tokens = _tokenize(texts)
    drawing_codes = sorted({t for t in tokens if _is_drawing_code(t)})

    materials = sorted({m for s in texts for m in _find_materials(s)})
    concretes = sorted({m for s in texts for m in _find_concretes(s)})
    dims = sorted({m for s in texts for m in _find_dimensions(s)})

    top_tokens = [t for t, _ in Counter(tokens).most_common(200)]

    summary = {
        "input": str(args.info_json.resolve()),
        "entity_count": raw.get("entity_count"),
        "kinds": raw.get("kinds"),
        "layers": raw.get("layers"),
        "bbox": raw.get("bbox"),
        "blocks": blocks,
        "drawing_codes": drawing_codes,
        "materials": materials,
        "concretes": concretes,
        "dimensions": dims,
        "top_tokens": top_tokens,
    }

    if args.out is None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(args.out))
    return 0


_SPLIT_RE = re.compile(r"[\s,;，。；、:/\\\[\]（）(){}<>《》“”\"'|]+")


def _tokenize(texts: list[str]) -> list[str]:
    out: list[str] = []
    for s in texts:
        s = s.strip()
        if not s:
            continue
        parts = _SPLIT_RE.split(s)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            out.append(p)
    return out


_DRAWING_CODE_RE = re.compile(r"^[A-Za-z]+-\d+(?:-\d+)*$")


def _is_drawing_code(t: str) -> bool:
    return _DRAWING_CODE_RE.match(t) is not None


def _find_materials(s: str) -> list[str]:
    return re.findall(r"(?:HRB|HPB)\d{3,4}", s.upper())


def _find_concretes(s: str) -> list[str]:
    return re.findall(r"C\d{2}", s.upper())


def _find_dimensions(s: str) -> list[str]:
    out: list[str] = []
    out += re.findall(r"[Φφ]\s*\d+(?:\.\d+)?\s*[×xX]\s*\d+(?:\.\d+)?\s*mm", s)
    out += re.findall(r"[Φφ]\s*\d+(?:\.\d+)?\s*mm", s)
    out += re.findall(r"\d+(?:\.\d+)?\s*(?:kPa|MPa|kN/m)", s)
    out += re.findall(r"\d+(?:\.\d+)?\s*mm", s)
    return [x.replace(" ", "") for x in out]


if __name__ == "__main__":
    raise SystemExit(main())
