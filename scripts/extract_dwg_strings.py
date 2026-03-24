from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(prog="extract_dwg_strings")
    ap.add_argument("path", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--min-len", type=int, default=4)
    ap.add_argument("--limit", type=int, default=2000)
    args = ap.parse_args()

    p = args.path.resolve()
    raw = p.read_bytes()

    ascii_s = _extract_ascii(raw, min_len=args.min_len)
    u16_s = _extract_utf16le(raw, min_len=args.min_len)

    strings = sorted(set(ascii_s) | set(u16_s))
    model_candidates = sorted({s for s in strings if _looks_like_model(s)})

    info = {
        "input_path": str(p),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "total_strings": len(strings),
        "model_candidates": model_candidates[: args.limit],
        "examples": strings[: min(len(strings), 200)],
    }

    if args.out is None:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(args.out))
    return 0


def _extract_ascii(raw: bytes, *, min_len: int) -> list[str]:
    out: list[str] = []
    buf: list[int] = []
    for b in raw:
        if 32 <= b <= 126:
            buf.append(b)
        else:
            if len(buf) >= min_len:
                out.append(bytes(buf).decode("ascii", errors="ignore"))
            buf = []
    if len(buf) >= min_len:
        out.append(bytes(buf).decode("ascii", errors="ignore"))
    return out


def _extract_utf16le(raw: bytes, *, min_len: int) -> list[str]:
    out: list[str] = []
    buf: list[int] = []
    i = 0
    while i + 1 < len(raw):
        lo = raw[i]
        hi = raw[i + 1]
        if hi == 0 and 32 <= lo <= 126:
            buf.append(lo)
        else:
            if len(buf) >= min_len:
                out.append(bytes(buf).decode("ascii", errors="ignore"))
            buf = []
        i += 2
    if len(buf) >= min_len:
        out.append(bytes(buf).decode("ascii", errors="ignore"))
    return out


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


if __name__ == "__main__":
    raise SystemExit(main())

