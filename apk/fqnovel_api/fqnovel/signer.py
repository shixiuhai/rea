"""Request signing abstraction.

Reverse-engineering result (see README):

    NetworkParams.tryAddSecurityFactor(url, headers)
        -> callback cast to `ms.bd.c.g5`
        -> ms.bd.c.k3.a(...)  (native, libmetasec_ml.so)
        -> Map<headerName, headerValue>

So the real signature is produced by ByteDance Metasec (native).  The header
names/values are decrypted at runtime and cannot be read statically.

This module exposes several interchangeable signers so the same client can be
used in different environments:

* ``NullSigner``    -- no security headers (works for the open list endpoints).
* ``HeaderFileSigner`` -- reuse headers captured from a real device (see
  ``hooks/frida_metasec.js``).
* ``RemoteSigner``  -- ask a local signing bridge (device / emulator) for
  fresh headers per URL.
* ``NativeSigner``  -- best-effort ctypes load of an extracted signer shared
  object.  Only works on a matching (Android/ARM) host runtime; raises a clear
  error elsewhere.

All signers return a ``dict`` of HTTP headers only; query-string signing (if a
deployment uses it) can be modelled by returning headers such as ``X-Bogus``.
"""

from __future__ import annotations

import json
import os
import platform
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests


class SignerError(RuntimeError):
    pass


class Signer:
    name = "base"

    def sign(self, method: str, url: str, headers: Dict[str, str],
             body: bytes = b"") -> Dict[str, str]:
        """Return extra headers to add to the request. May update nothing."""
        return {}

    def refresh(self) -> None:
        """Optional hook to refresh an expired signature/token."""


class NullSigner(Signer):
    name = "none"


@dataclass
class HeaderFileSigner(Signer):
    """Reuse a captured header map.

    File format (produced by hooks/frida_metasec.js):
        {"headers": {"x-gorgon": "...", "x-khronos": "...", ...},
         "captured_at": 1690000000}
    """
    path: str
    name = "header-file"
    _headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._headers = {str(k): str(v) for k, v in data.get("headers", {}).items()}

    def sign(self, method, url, headers, body=b""):
        return dict(self._headers)


@dataclass
class RemoteSigner(Signer):
    """Ask an external signer bridge (e.g. a Frida RPC/HTTP wrapper) for headers.

    The endpoint must accept ``POST {"method","url","headers"}`` and answer
    ``{"headers": {...}}``.
    """
    url: str
    timeout: float = 15.0
    name = "remote"

    def sign(self, method, url, headers, body=b""):
        resp = requests.post(self.url, json={"method": method, "url": url,
                                             "headers": headers}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return {str(k): str(v) for k, v in data.get("headers", {}).items()}


class NativeSigner(Signer):
    """Best-effort loader for the extracted native signer (libmetasec_ml.so).

    Note: libmetasec_ml.so is an Android/armeabi-v7a JNI library.  Loading it
    requires (a) an ARM host runtime and (b) a JNI ``JavaVM`` + Android
    ``Context`` for initialization.  On a plain x86_64 Linux host the load is
    expected to fail; use a device/emulator bridge instead.
    """
    name = "native"

    def __init__(self, lib_path: str):
        self.lib_path = os.path.abspath(lib_path)
        self._lib = None
        self._load()

    def _load(self) -> None:
        import ctypes
        machine = platform.machine().lower()
        if not self.lib_path or not os.path.exists(self.lib_path):
            raise SignerError(f"native library not found: {self.lib_path}")
        # Detect a clear architecture mismatch early with a helpful message.
        is_arm_lib = self._is_arm_elf(self.lib_path)
        host_is_arm = machine.startswith(("arm", "aarch"))
        if is_arm_lib and not host_is_arm:
            raise SignerError(
                "libmetasec_ml.so is an ARM (Android/bionic) library but the "
                f"host is {machine}. Run the signer on an ARM Android runtime "
                "(device/emulator + Frida) or use HeaderFileSigner/RemoteSigner."
            )
        try:
            self._lib = ctypes.CDLL(self.lib_path)
        except OSError as exc:  # pragma: no cover - host dependent
            raise SignerError(
                f"dlopen failed ({exc}); the library also needs JNI OnLoad and "
                "Android Context initialization. Use a device bridge."
            ) from exc

    @staticmethod
    def _is_arm_elf(path: str) -> bool:
        try:
            with open(path, "rb") as fh:
                magic = fh.read(20)
            if magic[:4] != b"\x7fELF":
                return False
            e_machine = int.from_bytes(magic[18:20], "little")
            return e_machine in (0x28, 0xB7)  # EM_ARM, EM_AARCH64
        except OSError:
            return False

    def sign(self, method, url, headers, body=b""):
        raise SignerError(
            "Native signing is not wired to the JNI entrypoints of this build. "
            "Extract the header map from a device with hooks/frida_metasec.js "
            "and use HeaderFileSigner, or run RemoteSigner against a device "
            "bridge. See README 'Signing'."
        )


def default_signer() -> Signer:
    """Pick a signer from environment without failing startup."""
    hdr = os.environ.get("FQNOVEL_SIGN_HEADERS")
    if hdr and os.path.exists(hdr):
        return HeaderFileSigner(hdr)
    remote = os.environ.get("FQNOVEL_SIGN_SERVER")
    if remote:
        return RemoteSigner(remote)
    lib = os.environ.get("FQNOVEL_NATIVE_LIB")
    if lib:
        try:
            return NativeSigner(lib)
        except SignerError as exc:
            print(f"[fqnovel] native signer unavailable: {exc}")
    return NullSigner()
