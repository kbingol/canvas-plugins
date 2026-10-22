#!/usr/bin/env python3
"""Create a deterministic, credential-free plugin archive after validation."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

from validate import ROOT, validate


def build(output: Path) -> Path:
    report = validate()
    package = ROOT / "plugins/canvas"
    version = report["packages"][0]["version"]
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"canvas-{version}.zip"
    files = sorted(p for p in package.rglob("*") if p.is_file())
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(package).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / f"{target.name}.sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    print(build(parser.parse_args().output))
