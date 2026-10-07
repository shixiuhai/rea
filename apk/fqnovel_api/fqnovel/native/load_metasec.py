"""Load the extracted signer shared object to wrap the signature algorithm.

Reality check (evidence from the reverse engineering):

* The signer used by the app is ByteDance **Metasec**:
      NetworkParams.tryAddSecurityFactor -> ms.bd.c.k3.a(...) -> libmetasec_ml.so
* ``libmetasec_ml.so`` is an **armeabi-v7a Android (bionic)** JNI library.
  Calling it requires:
    - an ARM host runtime (device / emulator), and
    - ``JNI_OnLoad`` with a live ``JavaVM`` plus an Android ``Context`` and a
      large amount of device state (metasec collects device fingerprint).
* Consequently it cannot be dlopen'd as-is on an x86_64 Linux host.  This
  module performs the load attempt and reports precisely why it fails, and it
  documents the JNI surfaces so a device-side harness can be built.

Recommended working paths (see README):
    1. hooks/frida_metasec.js  -> capture real headers on a device.
    2. A Frida RPC bridge       -> RemoteSigner (fresh headers per request).
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from typing import Optional

# JNI entrypoints exported by metasec builds (names are stable across versions;
# the Java layer is com.bytedance.mobsec.metasec.ml.MS / ms.bd.c.*).
KNOWN_JNI_SYMBOLS = [
    "JNI_OnLoad",
    "Java_com_bytedance_mobsec_metasec_ml_MSManagerUtils_init",
    "Java_com_bytedance_mobsec_metasec_ml_MS_1nativeInit",
]


def _elf_machine(path: str) -> Optional[int]:
    try:
        with open(path, "rb") as fh:
            b = fh.read(20)
        if b[:4] != b"\x7fELF":
            return None
        return int.from_bytes(b[18:20], "little")
    except OSError:
        return None


MACHINES = {0x03: "x86", 0x3E: "x86_64", 0x28: "ARM", 0xB7: "AArch64"}


def probe(lib_path: str) -> int:
    print(f"[load] host      : {platform.machine()} / {sys.platform}")
    print(f"[load] library   : {lib_path}")
    if not os.path.exists(lib_path):
        print("[load] ERROR: file does not exist. Run: python cli.py extract-so")
        return 2
    m = _elf_machine(lib_path)
    print(f"[load] ELF machine: {MACHINES.get(m, hex(m) if m else 'not-ELF')}")
    if m in (0x28, 0xB7) and not platform.machine().lower().startswith(("arm", "aarch")):
        print("[load] -> ARM library on a non-ARM host: cannot dlopen here.")
        print("[load]    Use hooks/frida_metasec.js on a device, or run this")
        print("[load]    script on an ARM Android runtime.")
        return 3
    import ctypes
    try:
        lib = ctypes.CDLL(lib_path)
    except OSError as exc:
        print(f"[load] dlopen failed: {exc}")
        print("[load]    Expected: the library needs JNI_OnLoad + Android Context.")
        return 4
    print("[load] dlopen OK")
    for sym in KNOWN_JNI_SYMBOLS:
        try:
            getattr(lib, sym)
            print(f"[load]   symbol present: {sym}")
        except AttributeError:
            print(f"[load]   symbol missing: {sym}")
    print("[load] NOTE: even with symbols present, signing requires a JavaVM,")
    print("[load]       an Android Context and device state; use a device bridge.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("lib", nargs="?", default=os.path.join(os.path.dirname(__file__), "libs", "libmetasec_ml.so"))
    args = ap.parse_args(argv)
    return probe(args.lib)


if __name__ == "__main__":
    raise SystemExit(main())
