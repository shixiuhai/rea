"""HTTP client for the discovered fqnovel endpoints."""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

from . import config, endpoints
from .common_params import DeviceProfile, build_common_params
from .signer import Signer, default_signer


class GatedError(RuntimeError):
    """Raised when an API-gateway-protected endpoint blocks the request."""


_ITEM_KEYS = {"item_id", "itemid", "itemId", "chapter_id", "chapterId"}
_CONTENT_KEYS = {"content", "origin_content", "chapter_content", "text", "contents"}


def extract_item_ids(obj: Any) -> list:
    """Recursively collect chapter/item ids preserving document order."""
    out: list = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _ITEM_KEYS and isinstance(v, (str, int)) and str(v).isdigit():
                    s = str(v)
                    if s not in out:
                        out.append(s)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


_BOOK_KEYS = {"book_id", "bookId", "bookid"}


def extract_book_ids(obj: Any) -> list:
    out: list = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _BOOK_KEYS and isinstance(v, (str, int)) and str(v).isdigit() and len(str(v)) > 10:
                    s = str(v)
                    if s not in out:
                        out.append(s)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


def extract_contents(obj: Any) -> Dict[str, str]:
    """Recursively map item_id -> best content string found in the response."""
    results: Dict[str, str] = {}

    def best_content(o) -> Optional[str]:
        found = []
        for k in _CONTENT_KEYS:
            if isinstance(o, dict) and isinstance(o.get(k), str) and o.get(k):
                found.append(o[k])
        return max(found, key=len) if found else None

    def walk(o, inherited_id=None):
        if isinstance(o, dict):
            iid = None
            for k in _ITEM_KEYS:
                if k in o and isinstance(o[k], (str, int)) and str(o[k]).isdigit():
                    iid = str(o[k])
                    break
            content = best_content(o)
            if content and (iid or inherited_id):
                results[iid or inherited_id] = content
            for v in o.values():
                walk(v, iid or inherited_id)
        elif isinstance(o, list):
            for x in o:
                walk(x, inherited_id)

    walk(obj)
    return results


@dataclass
class Response:
    status: int
    url: str
    json: Optional[Any]
    text: str
    raw: bytes
    headers: Dict[str, str]

    @property
    def ok(self) -> bool:
        if self.json and isinstance(self.json, dict):
            return self.json.get("code", 0) == 0
        return 200 <= self.status < 300 and len(self.raw) > 0


class FqnovelClient:
    def __init__(self,
                 device: Optional[DeviceProfile] = None,
                 signer: Optional[Signer] = None,
                 host: str = config.API_HOST,
                 timeout: float = 20.0,
                 session: Optional[requests.Session] = None):
        self.device = device or DeviceProfile.random()
        self.signer = signer if signer is not None else default_signer()
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT.format(
            vc=config.VERSION_CODE, os_ver=self.device.os_version,
            model=self.device.device_model)

    # -- low level ---------------------------------------------------------
    @staticmethod
    def _decompress(raw: bytes, headers: Dict[str, str]) -> bytes:
        enc = (headers.get("Content-Encoding") or headers.get("content-encoding") or "").lower()
        if "gzip" in enc or raw[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(raw)
            except OSError:
                return raw
        if "deflate" in enc:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return raw
        return raw

    def request(self, path: str,
                params: Optional[Dict[str, Any]] = None,
                method: str = "GET",
                with_common: bool = True,
                extra_common: Optional[Dict[str, str]] = None) -> Response:
        merged: Dict[str, str] = {}
        if with_common:
            merged.update(build_common_params(self.device, extra_common))
        if params:
            merged.update({k: str(v) for k, v in params.items() if v is not None})
        url = self.host + path
        if method.upper() == "GET":
            url = url + ("&" if "?" in url else "?") + urlencode(merged)

        sign_headers = self.signer.sign(method, url, dict(self.session.headers), b"")
        headers = dict(sign_headers)

        resp = self.session.request(method, url, headers=headers,
                                    data=None if method.upper() == "GET" else merged,
                                    timeout=self.timeout, allow_redirects=True)
        raw = self._decompress(resp.content, dict(resp.headers))
        text = raw.decode("utf-8", "replace")
        js = None
        try:
            import json
            js = json.loads(text)
        except Exception:
            js = None
        return Response(resp.status_code, url, js, text, raw, dict(resp.headers))

    # -- book list ---------------------------------------------------------
    def book_list_store_home(self) -> Response:
        """GET /reading/bookapi/bookstore/homepage/v1/  (open, no signature)."""
        return self.request(endpoints.BOOK_LIST["store_home"])

    def book_list_tab(self, tab_index: int = 0, tab_type: int = 0,
                      offset: int = 0, stream_count: int = 10,
                      **fields: Any) -> Response:
        """GET /reading/bookapi/bookmall/tab/v1/  (open, no signature)."""
        params = {
            "tab_index": tab_index,
            "tab_type": tab_type,
            "offset": offset,
            "stream_count": stream_count,
        }
        params.update({k: v for k, v in fields.items() if v is not None})
        return self.request(endpoints.BOOK_LIST["mall_tab"], params)

    def book_list_category(self, category_id: Optional[int] = None,
                           offset: int = 0, count: int = 10, **fields: Any) -> Response:
        """GET /reading/bookapi/category/booklist/v1/ (open)."""
        params: Dict[str, Any] = {"offset": offset, "count": count}
        if category_id is not None:
            params["category_id"] = category_id
        params.update(fields)
        return self.request(endpoints.BOOK_LIST["category_booklist"], params)

    # -- search ------------------------------------------------------------
    def search_page(self, query: str, offset: int = 0, count: int = 10,
                    tab_type: int = 0, **fields: Any) -> Response:
        """GET /reading/bookapi/search/page/v1/  (gateway-gated)."""
        params = endpoints.demo_search_params(query)
        params.update({"offset": offset, "count": count, "tab_type": tab_type})
        params.update({k: v for k, v in fields.items() if v is not None})
        return self.request(endpoints.BOOK_SEARCH["search_page"], params)

    def search(self, query: str, offset: int = 0, count: int = 10, **fields: Any) -> Response:
        params = {"query": query, "offset": offset, "count": count}
        params.update({k: v for k, v in fields.items() if v is not None})
        return self.request(endpoints.BOOK_SEARCH["search"], params)

    def suggest(self, query: str, **fields: Any) -> Response:
        params = {"query": query}
        params.update({k: v for k, v in fields.items() if v is not None})
        return self.request(endpoints.BOOK_SEARCH["suggest"], params)

    # -- content / download ------------------------------------------------
    def reader_full(self, book_id: str, item_id: str, req_type: int = 0,
                    novel_text_type: int = 0, unlock_mode: int = 0,
                    key_register_ts: int = 0) -> Response:
        """GET /reading/reader/full/v1/  (gateway-gated)."""
        params = {
            "book_id": book_id, "item_id": item_id, "req_type": req_type,
            "novel_text_type": novel_text_type, "unlock_mode": unlock_mode,
            "key_register_ts": key_register_ts,
        }
        return self.request(endpoints.DOWNLOAD["reader_full"], params)

    def reader_batch_full(self, book_id: str, item_ids, req_type: int = 0,
                          novel_text_type: int = 0, key_register_ts: int = 0) -> Response:
        """GET /reading/reader/batch_full/v1/  (gateway-gated, offline download)."""
        if isinstance(item_ids, (list, tuple)):
            item_ids = ",".join(str(i) for i in item_ids)
        params = {
            "book_id": book_id, "item_ids": item_ids, "req_type": req_type,
            "novel_text_type": novel_text_type, "key_register_ts": key_register_ts,
        }
        return self.request(endpoints.DOWNLOAD["reader_batch_full"], params)

    # -- helpers -----------------------------------------------------------
    def book_detail(self, book_id: str, **fields: Any) -> Response:
        params = {"book_id": book_id}
        params.update(fields)
        return self.request(endpoints.MISC["book_detail"], params)

    def directory_all_items(self, book_id: str, **fields: Any) -> Response:
        params = {"book_id": book_id}
        params.update(fields)
        return self.request(endpoints.MISC["directory_all_items"], params)

    # -- full book -> txt --------------------------------------------------
    def download_book_to_txt(self,
                             book_id: str,
                             out_path: str,
                             max_chapters: int = 0,
                             batch_size: int = 20,
                             progress=None) -> Dict[str, Any]:
        """Download all chapters of a book and write a UTF-8 .txt.

        Requires a working signer (see README 'Signing'); the directory and
        reader endpoints are gateway-gated and return empty without one.
        Raises ``GatedError`` when the gateway blocks the request.
        """
        log = progress or (lambda *a: None)

        r = self.directory_all_items(book_id)
        if not r.raw:
            raise GatedError("directory/all_items returned empty (gateway gated); attach a signer")
        item_ids = extract_item_ids(r.json)
        if not item_ids:
            raise GatedError("no item ids in directory response (gated or empty)")
        if max_chapters:
            item_ids = item_ids[:max_chapters]
        log(f"[download] book {book_id}: {len(item_ids)} chapters")

        chapters: Dict[str, str] = {}
        # Batch first (offline download endpoint), fall back to single.
        for start in range(0, len(item_ids), batch_size):
            chunk = item_ids[start:start + batch_size]
            rb = self.reader_batch_full(book_id, chunk)
            texts = extract_contents(rb.json)
            if texts:
                chapters.update(texts)
                log(f"[download] batch {start}-{start+len(chunk)} ok")
                continue
            for iid in chunk:
                rf = self.reader_full(book_id, iid)
                texts = extract_contents(rf.json)
                if texts:
                    chapters.update(texts)

        if not chapters:
            raise GatedError(
                "no chapter content returned by reader/batch_full|full "
                "(gateway gated); attach a signer"
            )

        title = (r.json or {}).get("data", {}).get("book_name") if isinstance(r.json, dict) else None
        parts = [f"# {title or book_id}\n"]
        for iid in item_ids:
            content = chapters.get(str(iid)) or chapters.get(iid)
            if not content:
                continue
            parts.append(f"\n\n===== {iid} =====\n\n{content}")
        text = "".join(parts)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"[download] wrote {len(text)} chars -> {out_path}")
        return {"book_id": book_id, "chapters": len(chapters), "out": out_path} 
