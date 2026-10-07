"""Execute an exported ARM/Thumb function from an extracted Android .so on x86_64.

The APK's native libraries are armeabi-v7a / Android bionic, so a plain
``ctypes.CDLL`` cannot load them on this host (wrong architecture + wrong ABI).
This module instead *emulates* the ARM code with the Unicorn engine, which lets
us actually call exported functions and observe their behaviour without a
device — a concrete way to answer "can we just run the .so?".

Scope / honesty:
    * Maps the ELF PT_LOAD segments, applies the dynamic relocations it can, and
      points unresolved imports at trapping stubs that return 0.
    * Anything needing a live ``JNIEnv``/``JavaVM``, an Android ``Context``,
      ``libandroid``/``liblog`` or device state is stubbed and reported — that is
      the honest boundary of off-device execution.

Usage:
    python -m fqnovel.native.emulate_so <lib.so> --list
    python -m fqnovel.native.emulate_so libencrypt.so _Z13get_aes_tokenv --str
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                                   UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_SP,
                                   UC_ARM_REG_PC)
except ImportError:  # pragma: no cover
    Uc = None  # type: ignore

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_HASH, DT_STRTAB, DT_SYMTAB = 0, 4, 5, 6
DT_REL, DT_RELSZ, DT_RELENT, DT_JMPREL, DT_PLTRELSZ = 17, 18, 19, 23, 2

R_ARM_ABS32, R_ARM_GLOB_DAT, R_ARM_JUMP_SLOT, R_ARM_RELATIVE = 2, 21, 22, 23

BASE = 0x10000000        # load bias (Unicorn dislikes mapping at 0)
STUB_BASE = 0x60000000   # trapping stubs for unresolved imports
STACK_BASE = 0x70000000
RET_MAGIC = 0x5EED0000   # magic LR value that stops emulation


@dataclass
class Seg:
    vaddr: int
    offset: int
    filesz: int
    memsz: int
    flags: int


class ArmEmulator:
    def __init__(self, path: str):
        if Uc is None:
            raise RuntimeError("unicorn is not installed (pip install unicorn)")
        self.path = path
        self.data = open(path, "rb").read()
        self.traps: Dict[int, str] = {}
        self.trap_log: List[str] = []
        self._parse_elf()
        self._map_and_relocate()
        self.symbols = self._exported_symbols()

    # -- parsing -----------------------------------------------------------
    def _parse_elf(self) -> None:
        d = self.data
        if d[:4] != b"\x7fELF" or d[4] != 1 or d[5] != 1:
            raise ValueError("not a little-endian ELF32 file")
        self.e_phoff = struct.unpack_from("<I", d, 0x1C)[0]
        self.e_phentsize = struct.unpack_from("<H", d, 0x2A)[0]
        self.e_phnum = struct.unpack_from("<H", d, 0x2C)[0]
        self.segs: List[Seg] = []
        self.dynamic: List[Tuple[int, int]] = []
        for i in range(self.e_phnum):
            o = self.e_phoff + i * self.e_phentsize
            t, po, pv, _pp, fs, ms, fl, _al = struct.unpack_from("<IIIIIIII", d, o)
            if t == PT_LOAD:
                self.segs.append(Seg(pv, po, fs, ms, fl))
            elif t == PT_DYNAMIC:
                off = 0
                while True:
                    tag, val = struct.unpack_from("<iI", d, po + off)
                    off += 8
                    if tag == DT_NULL:
                        break
                    self.dynamic.append((tag, val))
        if not self.segs:
            raise ValueError("no PT_LOAD segments")

    def _dyn(self, tag: int) -> Optional[int]:
        for t, v in self.dynamic:
            if t == tag:
                return v
        return None

    def _file_off(self, va: int) -> Optional[int]:
        for s in self.segs:
            if s.vaddr <= va < s.vaddr + s.filesz:
                return s.offset + (va - s.vaddr)
        return None

    def _cstr(self, va: int) -> str:
        off = self._file_off(va)
        if off is None:
            return f"<unmapped 0x{va:x}>"
        end = self.data.find(b"\x00", off)
        return self.data[off:end].decode("latin-1", "replace")

    # -- loading -----------------------------------------------------------
    def _map_and_relocate(self) -> None:
        d = self.data
        end = max(s.vaddr + s.memsz for s in self.segs)
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(BASE, (end + 0x1000) & ~0xFFF)
        self.uc.mem_map(STUB_BASE, 0x1000)
        self.uc.mem_map(STACK_BASE, 0x100000)
        for s in self.segs:
            if s.filesz:
                self.uc.mem_write(BASE + s.vaddr, d[s.offset:s.offset + s.filesz])
        # each stub = "bx lr" (ARM) so an unresolved call returns immediately
        for i in range(256):
            self.uc.mem_write(STUB_BASE + i * 4, b"\x1e\xff\x2f\xe1")
        self._relocate()
        self.uc.hook_add(UC_HOOK_CODE, self._on_code)

    def _relocate(self) -> None:
        uc = self.uc
        rel = self._dyn(DT_REL)
        relsz = self._dyn(DT_RELSZ) or 0
        strtab = self._dyn(DT_STRTAB)
        symtab = self._dyn(DT_SYMTAB)
        jmprel = self._dyn(DT_JMPREL)
        pltrelsz = self._dyn(DT_PLTRELSZ) or 0

        def entry_table(pos: int, count: int):
            for i in range(count):
                yield struct.unpack_from("<II", self.data, pos + i * 8)

        def apply(offset: int, info: int) -> None:
            rtype, sym = info & 0xFF, info >> 8
            addr = BASE + offset
            if rtype == R_ARM_RELATIVE:
                val = struct.unpack("<I", uc.mem_read(addr, 4))[0]
                uc.mem_write(addr, struct.pack("<I", BASE + val))
            elif rtype in (R_ARM_GLOB_DAT, R_ARM_JUMP_SLOT):
                name, sym_shndx, sym_val = "?", 0, 0
                if strtab is not None and symtab is not None:
                    name_off, sym_val, _sz, _info, _o, sym_shndx = struct.unpack_from(
                        "<IIIBBH", self.data, symtab + sym * 16)
                    name = self._cstr(strtab + name_off)
                if sym_shndx != 0:  # symbol defined in this DSO -> real address
                    uc.mem_write(addr, struct.pack("<I", BASE + sym_val))
                else:               # genuine import -> stub that returns 0
                    stub = STUB_BASE + (len(self.traps) % 256) * 4
                    self.traps[stub] = name
                    uc.mem_write(addr, struct.pack("<I", stub))
            elif rtype == R_ARM_ABS32:
                addend = struct.unpack("<I", uc.mem_read(addr, 4))[0]
                sym_shndx, sym_val, name = 0, 0, "?"
                if strtab is not None and symtab is not None:
                    name_off, sym_val, _sz, _info, _o, sym_shndx = struct.unpack_from(
                        "<IIIBBH", self.data, symtab + sym * 16)
                    name = self._cstr(strtab + name_off)
                if sym == 0:
                    uc.mem_write(addr, struct.pack("<I", BASE + addend))
                elif sym_shndx != 0:
                    uc.mem_write(addr, struct.pack("<I", BASE + sym_val + addend))
                else:
                    stub = STUB_BASE + (len(self.traps) % 256) * 4
                    self.traps[stub] = name
                    uc.mem_write(addr, struct.pack("<I", stub))

        if rel is not None:
            for off, info in entry_table(rel, relsz // 8):
                apply(off, info)
        if jmprel is not None:
            for off, info in entry_table(jmprel, pltrelsz // 8):
                apply(off, info)

    def _on_code(self, uc, address, size, user) -> None:
        if (address & ~1) == RET_MAGIC:
            uc.emu_stop()
            return
        name = self.traps.get(address & ~1)
        if name is not None:
            self.trap_log.append(name)
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) & ~1)

    # -- symbols / calls ---------------------------------------------------
    def _exported_symbols(self) -> Dict[str, Tuple[int, int]]:
        symtab, strtab, has = self._dyn(DT_SYMTAB), self._dyn(DT_STRTAB), self._dyn(DT_HASH)
        if not symtab or not strtab or not has:
            return {}
        n = struct.unpack_from("<I", self.data, has + 4)[0]  # nchain
        out: Dict[str, Tuple[int, int]] = {}
        for i in range(n):
            name_off, value, size, info, _o, _sh = struct.unpack_from("<IIIBBH", self.data, symtab + i * 16)
            if value and (info & 0xF) == 2:  # STT_FUNC, defined
                out[self._cstr(strtab + name_off)] = (value, size)
        return out

    def call(self, func_addr: int, args: Tuple[int, ...] = ()) -> int:
        uc = self.uc
        uc.reg_write(UC_ARM_REG_SP, STACK_BASE + 0x80000)
        regs = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
        for reg, val in zip(regs, args[:4]):
            uc.reg_write(reg, val)
        uc.reg_write(UC_ARM_REG_LR, RET_MAGIC | 1)
        start = BASE + func_addr
        if not (start & 1):
            start |= 1  # thumb
        self.trap_log.clear()
        try:
            uc.emu_start(start, RET_MAGIC, timeout=5_000_000)
        except Exception as exc:
            code = exc.args[0] if exc.args else 0
            raise RuntimeError(f"emulation stopped: {exc}") from exc
        return uc.reg_read(UC_ARM_REG_R0) & 0xFFFFFFFF

    def read_cstr(self, va: int, n: int = 128) -> bytes:
        try:
            return bytes(self.uc.mem_read(va, n)).split(b"\x00", 1)[0]
        except Exception:
            return b""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lib")
    ap.add_argument("func", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--str", action="store_true", help="interpret r0 as a C string")
    ap.add_argument("--args", default="")
    args = ap.parse_args(argv)

    emu = ArmEmulator(args.lib)
    if args.list or not args.func:
        print(f"# {args.lib}: {len(emu.symbols)} exported functions")
        for name, (val, size) in sorted(emu.symbols.items(), key=lambda kv: kv[1][0]):
            print(f"  0x{val:06x}  size={size:<4} {name}")
        return 0
    if args.func not in emu.symbols:
        print(f"# symbol not found: {args.func}", file=sys.stderr)
        return 2
    addr = emu.symbols[args.func][0]
    call_args = tuple(int(x, 0) for x in args.args.split(",") if x.strip())
    r0 = emu.call(addr, call_args)
    print(f"# call {args.func} (0x{addr:x}) -> r0 = 0x{r0:x}")
    if emu.trap_log:
        print(f"# trapped imports hit: {sorted(set(emu.trap_log))}")
    if args.str:
        print(f"# string@r0 = {emu.read_cstr(r0)!r}" if r0 else "# string@r0 = (null)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
