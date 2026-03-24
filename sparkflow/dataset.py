from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .util import sha256_file


@dataclass(frozen=True)
class DatasetEntry:
    rel_path: str
    abs_path: str
    ext: str
    size_bytes: int
    mtime_epoch: float
    sha256: str | None


@dataclass(frozen=True)
class DatasetIndex:
    root_dir: str
    entries: tuple[DatasetEntry, ...]


def scan_dataset(root_dir: Path, *, compute_sha256: bool) -> DatasetIndex:
    root_dir = root_dir.resolve()
    if not root_dir.exists():
        raise FileNotFoundError(str(root_dir))
    if not root_dir.is_dir():
        raise NotADirectoryError(str(root_dir))

    exts = {".dwg", ".dxf", ".pdf"}
    entries: list[DatasetEntry] = []

    for p in sorted(root_dir.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in exts:
            continue
        st = p.stat()
        sha = sha256_file(p) if compute_sha256 else None
        entries.append(
            DatasetEntry(
                rel_path=str(p.relative_to(root_dir)).replace("\\", "/"),
                abs_path=str(p),
                ext=ext.lstrip("."),
                size_bytes=int(st.st_size),
                mtime_epoch=float(st.st_mtime),
                sha256=sha,
            )
        )

    return DatasetIndex(root_dir=str(root_dir), entries=tuple(entries))
