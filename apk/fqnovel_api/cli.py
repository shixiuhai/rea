#!/usr/bin/env python3
"""One-stop CLI for the fqnovel API client.

Examples:
    python cli.py list --tab store
    python cli.py list --tab mall --count 10
    python cli.py search --query "斗罗大陆"
    python cli.py download --book-id 7221013548120411151 --item-ids 1,2,3
    python cli.py selftest
    python cli.py extract-so
    python cli.py probe-native
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from fqnovel import (
    FqnovelClient,
    GatedError,
    Response,
    DeviceProfile,
    default_signer,
    extract_book_ids,
)
from fqnovel import config, endpoints
from fqnovel.signer import HeaderFileSigner, NativeSigner, RemoteSigner

DEFAULT_APK = os.path.join(os.path.dirname(__file__), "..", "novelapp_43536163a_v1327_73932_73932_9e6c_1790564338.apk")
DEFAULT_APK = os.path.abspath(DEFAULT_APK)
LIBS_DIR = os.path.join(os.path.dirname(__file__), "fqnovel", "native", "libs")


def make_client(args) -> FqnovelClient:
    device = DeviceProfile(
        device_id=args.device_id, iid=args.iid,
        openudid=args.openudid or DeviceProfile.random().openudid,
        cdid=args.cdid or DeviceProfile.random().cdid,
    ) if (args.device_id or args.iid) else DeviceProfile.random()
    if args.sign_headers:
        signer = HeaderFileSigner(args.sign_headers)
    elif args.sign_server:
        signer = RemoteSigner(args.sign_server)
    elif args.native_lib:
        signer = NativeSigner(args.native_lib)
    else:
        signer = default_signer()
    return FqnovelClient(device=device, signer=signer, host=args.host, timeout=args.timeout)


def dump(resp: Response, args) -> None:
    print(f"# {resp.status}  {resp.url.split('?')[0]}")
    if args.json or resp.json is None:
        if resp.json is not None:
            print(json.dumps(resp.json, ensure_ascii=False, indent=2)[: args.limit])
        else:
            print(f"# non-JSON body, {len(resp.raw)} bytes")
            if args.raw:
                sys.stdout.write(resp.text[: args.limit])
                print()
    else:
        print(json.dumps(resp.json, ensure_ascii=False, indent=2)[: args.limit])


def cmd_list(args) -> int:
    c = make_client(args)
    if args.tab == "store":
        r = c.book_list_store_home()
    elif args.tab == "mall":
        r = c.book_list_tab(tab_index=args.tab_index, tab_type=args.tab_type,
                            offset=args.offset, stream_count=args.count)
    elif args.tab == "category":
        r = c.book_list_category(offset=args.offset, count=args.count)
    else:
        raise SystemExit(f"unknown --tab {args.tab}")
    dump(r, args)
    return 0 if r.ok else 1


def cmd_search(args) -> int:
    c = make_client(args)
    r = c.search_page(args.query, offset=args.offset, count=args.count)
    dump(r, args)
    return 0 if r.ok else 1


def cmd_download(args) -> int:
    c = make_client(args)
    if args.batch:
        r = c.reader_batch_full(args.book_id, args.item_ids or "")
    else:
        r = c.reader_full(args.book_id, args.item_ids or "0")
    dump(r, args)
    return 0 if r.ok else 1


def cmd_download_book(args) -> int:
    c = make_client(args)
    book_id = args.book_id
    if not book_id:
        r = c.book_list_tab(stream_count=10)
        ids = extract_book_ids(r.json)
        if not ids:
            print("[download-book] could not pick a book from the open list")
            return 1
        book_id = ids[0]
        print(f"[download-book] picked book_id={book_id} from book mall")
    try:
        info = c.download_book_to_txt(
            book_id, args.out, max_chapters=args.max_chapters,
            progress=lambda m: print(m))
        print(json.dumps(info, ensure_ascii=False))
        return 0
    except GatedError as exc:
        print(f"[download-book] GATED: {exc}")
        print("[download-book] Content endpoints require a Metasec signature.")
        print("[download-book] Run hooks/signer_bridge.py on a device, then:")
        print("  FQNOVEL_SIGN_SERVER=http://127.0.0.1:8686/sign ./run.sh download-book --book-id " + book_id)
        return 3


def cmd_detail(args) -> int:
    c = make_client(args)
    dump(c.book_detail(args.book_id), args)
    return 0


def cmd_directory(args) -> int:
    c = make_client(args)
    dump(c.directory_all_items(args.book_id), args)
    return 0


def cmd_selftest(args) -> int:
    c = make_client(args)
    print(f"# signer = {c.signer.name}, device_id={c.device.device_id}, host={c.host}")
    results = []

    r = c.book_list_store_home()
    results.append(("list:store_home", r.ok, r.status, len(r.raw),
                    (r.json or {}).get("code") if r.json else "non-json"))
    print(f"[selftest] list:store_home  ok={r.ok} status={r.status} bytes={len(r.raw)} code={(r.json or {}).get('code')}")

    r = c.book_list_tab(stream_count=5)
    results.append(("list:mall_tab", r.ok, r.status, len(r.raw),
                    (r.json or {}).get("code") if r.json else "non-json"))
    print(f"[selftest] list:mall_tab   ok={r.ok} status={r.status} bytes={len(r.raw)} code={(r.json or {}).get('code')}")

    r = c.search_page("斗罗大陆")
    print(f"[selftest] search:page     ok={r.ok} status={r.status} code={(r.json or {}).get('code')} msg={(r.json or {}).get('message')}")

    r = c.reader_full("7221013548120411151", "0")
    print(f"[selftest] download:full   ok={r.ok} status={r.status} bytes={len(r.raw)}")

    print("\n[selftest] summary:")
    for name, ok, st, n, code in results:
        print(f"  {name:20s} {'PASS' if ok else 'FAIL'}  http={st} bytes={n} code={code}")
    print("\nNote: search/content endpoints are gateway-gated; they return")
    print("PARAM_INVALID / empty body without a valid Metasec signature.")
    print("Open list endpoints must PASS above.")
    return 0


def cmd_extract_so(args) -> int:
    from fqnovel.native.extract_so import extract
    extract(args.apk, args.out, args.abi)
    return 0


def cmd_probe_native(args) -> int:
    from fqnovel.native.load_metasec import probe
    lib = args.native_lib or os.path.join(LIBS_DIR, "libmetasec_ml.so")
    return probe(lib)


def cmd_emulate(args) -> int:
    from fqnovel.native import emulate_so
    argv = [args.lib]
    if args.symbol:
        argv.append(args.symbol)
    if args.list:
        argv.append("--list")
    if args.as_str:
        argv.append("--str")
    if args.args:
        argv += ["--args", args.args]
    return emulate_so.main(argv)


DEFAULTS = {
    "host": config.API_HOST,
    "device_id": "",
    "iid": "",
    "openudid": "",
    "cdid": "",
    "timeout": 20.0,
    "sign_headers": os.environ.get("FQNOVEL_SIGN_HEADERS"),
    "sign_server": os.environ.get("FQNOVEL_SIGN_SERVER"),
    "native_lib": os.environ.get("FQNOVEL_NATIVE_LIB"),
    "json": False,
    "raw": False,
    "limit": 4000,
}


def add_common(p: argparse.ArgumentParser, suppress: bool) -> None:
    """Add global options so they work both before and after the subcommand."""
    def dflt(v):
        return argparse.SUPPRESS if suppress else v
    p.add_argument("--host", default=dflt(config.API_HOST))
    p.add_argument("--device-id", default=dflt(""))
    p.add_argument("--iid", default=dflt(""))
    p.add_argument("--openudid", default=dflt(""))
    p.add_argument("--cdid", default=dflt(""))
    p.add_argument("--timeout", type=float, default=dflt(20.0))
    p.add_argument("--sign-headers", default=dflt(os.environ.get("FQNOVEL_SIGN_HEADERS")),
                   help="JSON file with captured signature headers")
    p.add_argument("--sign-server", default=dflt(os.environ.get("FQNOVEL_SIGN_SERVER")),
                   help="HTTP signer bridge URL")
    p.add_argument("--native-lib", default=dflt(os.environ.get("FQNOVEL_NATIVE_LIB")),
                   help="path to a host-compatible signer .so")
    p.add_argument("--json", action="store_true", default=dflt(False), help="force JSON output")
    p.add_argument("--raw", action="store_true", default=dflt(False), help="print raw text for non-JSON")
    p.add_argument("--limit", type=int, default=dflt(4000))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common(ap, suppress=False)
    common = argparse.ArgumentParser(add_help=False)
    add_common(common, suppress=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="book list", parents=[common])
    p.add_argument("--tab", choices=["store", "mall", "category"], default="store")
    p.add_argument("--tab-index", type=int, default=0)
    p.add_argument("--tab-type", type=int, default=0)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="book search", parents=[common])
    p.add_argument("--query", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("download", help="chapter content / offline download", parents=[common])
    p.add_argument("--book-id", required=True)
    p.add_argument("--item-ids", default="", help="single id or comma list")
    p.add_argument("--batch", action="store_true", help="use batch_full endpoint")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("download-book", help="download a whole book to .txt", parents=[common])
    p.add_argument("--book-id", default="", help="omit to auto-pick from the open list")
    p.add_argument("--out", default="book.txt")
    p.add_argument("--max-chapters", type=int, default=0)
    p.set_defaults(func=cmd_download_book)

    p = sub.add_parser("detail", help="book detail (gated)", parents=[common])
    p.add_argument("--book-id", required=True)
    p.set_defaults(func=cmd_detail)

    p = sub.add_parser("directory", help="chapter directory (gated)", parents=[common])
    p.add_argument("--book-id", required=True)
    p.set_defaults(func=cmd_directory)

    p = sub.add_parser("selftest", help="run end-to-end checks", parents=[common])
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("extract-so", help="extract native libs from the APK", parents=[common])
    p.add_argument("--apk", default=DEFAULT_APK)
    p.add_argument("--out", default=LIBS_DIR)
    p.add_argument("--abi", default="armeabi-v7a")
    p.set_defaults(func=cmd_extract_so)

    p = sub.add_parser("probe-native", help="attempt to load the signer .so", parents=[common])
    p.set_defaults(func=cmd_probe_native)

    p = sub.add_parser("emulate", help="emulate an exported function of a native lib",
                       parents=[common])
    p.add_argument("--lib", required=True, help="path to the .so")
    p.add_argument("symbol", nargs="?", default=None, help="mangled symbol to call")
    p.add_argument("--list", action="store_true", help="list exported functions")
    p.add_argument("--str", dest="as_str", action="store_true", help="treat r0 as a C string")
    p.add_argument("--args", default="", help="comma-separated integer args")
    p.set_defaults(func=cmd_emulate)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # Global options may be omitted (SUPPRESS on subparsers): restore defaults.
    for key, value in DEFAULTS.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
