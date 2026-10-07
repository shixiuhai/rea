"""Smoke tests.

Run all:
    python -m pytest -q            (or: python -m unittest -v tests.test_smoke)
Offline (skip network):
    FQNOVEL_OFFLINE=1 python -m unittest -v tests.test_smoke

Network tests hit the live fqnovel gateway.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fqnovel import FqnovelClient, DeviceProfile, build_common_params, endpoints  # noqa: E402
from fqnovel.client import extract_book_ids, extract_contents, extract_item_ids  # noqa: E402
from fqnovel.signer import NullSigner  # noqa: E402

OFFLINE = os.environ.get("FQNOVEL_OFFLINE") == "1"


class TestCommonParams(unittest.TestCase):
    def test_required_keys_present(self):
        p = build_common_params(DeviceProfile.random(seed=1))
        for key in ("aid", "app_name", "version_code", "manifest_version_code",
                    "update_version_code", "device_platform", "os", "device_id",
                    "iid", "openudid", "cdid", "channel", "resolution", "dpi",
                    "language", "region", "_rticket", "ts", "ssmix"):
            self.assertIn(key, p, key)
        self.assertEqual(p["aid"], "1967")
        self.assertEqual(p["device_platform"], "android")

    def test_timestamps_regenerate(self):
        p1 = build_common_params(DeviceProfile.random(seed=1))
        self.assertEqual(p1["_rticket"], p1["ts"])


class TestEndpoints(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(endpoints.BOOK_LIST["store_home"], "/reading/bookapi/bookstore/homepage/v1/")
        self.assertEqual(endpoints.BOOK_LIST["mall_tab"], "/reading/bookapi/bookmall/tab/v1/")
        self.assertEqual(endpoints.BOOK_SEARCH["search_page"], "/reading/bookapi/search/page/v1/")
        self.assertEqual(endpoints.DOWNLOAD["reader_full"], "/reading/reader/full/v1/")
        self.assertEqual(endpoints.DOWNLOAD["reader_batch_full"], "/reading/reader/batch_full/v1/")


class TestParsers(unittest.TestCase):
    def test_extract_item_ids_and_contents(self):
        payload = {"data": {"item_data_list": [
            {"item_id": "101", "content": "第一章 hello"},
            {"item_id": "102", "content": "第二章 world"},
        ]}}
        self.assertEqual(extract_item_ids(payload), ["101", "102"])
        got = extract_contents(payload)
        self.assertEqual(got.get("101"), "第一章 hello")
        self.assertEqual(got.get("102"), "第二章 world")

    def test_extract_book_ids(self):
        payload = {"cell_data": [{"book_id": "7221013548120411151"}, {"book_id": "1"}]}
        self.assertEqual(extract_book_ids(payload), ["7221013548120411151"])


@unittest.skipIf(OFFLINE, "offline mode")
class TestLiveOpenEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = FqnovelClient(signer=NullSigner())

    def test_store_home_works(self):
        r = self.client.book_list_store_home()
        self.assertEqual(r.status, 200)
        self.assertIsInstance(r.json, dict)
        self.assertEqual(r.json.get("code"), 0)
        self.assertTrue(len(r.raw) > 1000)

    def test_mall_tab_works(self):
        r = self.client.book_list_tab(stream_count=5)
        self.assertEqual(r.status, 200)
        self.assertEqual((r.json or {}).get("code"), 0)

    def test_search_is_gateway_gated(self):
        # Without a Metasec signature the gateway answers PARAM_INVALID.
        r = self.client.search_page("斗罗大陆")
        self.assertEqual(r.status, 200)
        self.assertIsInstance(r.json, dict)
        self.assertIn("code", r.json)


if __name__ == "__main__":
    unittest.main(verbosity=2)
