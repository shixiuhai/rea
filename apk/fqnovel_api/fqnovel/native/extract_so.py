"""Extract native shared objects (e.g. libmetasec_ml.so) from the APK.

Usage:
    python -m fqnovel.native.extract_so <apk> [--out DIR] [--abi armeabi-v7a]
or via the CLI:
    python cli.py extract-so
"""

from __future__ import annotations

import argparse
import hashlib
import os
import zipfile
from typing import List

DEFAULT_LIBS = [
    "libmetasec_ml.so",
    "libdragon_crypt.so",
    "libencrypt.so",
    "libEncryptor.so",
]


def extract(apk_path: str, out_dir: str, abi: str = "armeabi-v7a",
            names: List[str] | None = None) -> List[str]:
    names = names or DEFAULT_LIBS
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    with zipfile.ZipFile(apk_path) as zf:
        members = set(zf.namelist())
        for name in names:
            member = f"lib/{abi}/{name}"
            if member not in members:
                continue
            data = zf.read(member)
            dst = os.path.join(out_dir, name)
            with open(dst, "wb") as fh:
                fh.write(data)
            digest = hashlib.sha256(data).hexdigest()
            print(f"[extract] {member} -> {dst}  sha256={digest}  bytes={len(data)}")
            written.append(dst)
    if not written:
        print(f"[extract] nothing found for abi={abi}; available lib dirs: " +
              ", ".join(sorted({n.split('/')[1] for n in members if n.startswith('lib/')})))
    return written


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("apk")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "libs"))
    ap.add_argument("--abi", default="armeabi-v7a")
    args = ap.parse_args(argv)
    extract(args.apk, args.out, args.abi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
