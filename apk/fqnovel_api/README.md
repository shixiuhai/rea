# fqnovel_api

Tools to call the **番茄小说 / com.dragon.read** HTTP API, reverse engineered from

`../novelapp_43536163a_v1327_73932_73932_9e6c_1790564338.apk` (v7.3.9.32, versionCode 73932).

It provides:

- book **list** endpoints (work anonymously, verified end-to-end),
- book **search** endpoints (gateway-gated),
- chapter **content / offline download** endpoints (gateway-gated),
- the **common parameter** builder and the request pipeline,
- the **native signer** extraction + a loader harness, plus Frida hooks to
  capture/produce real Metasec signatures on a device.

> **设计与逆向逻辑总账见 [DESIGN.md](DESIGN.md)**（分层架构、请求计算过程、
> 原生签名/解密链路、环境约束、“基于原 App 封装接口”的三种方案与路线图）。

> **设备要求**：开放列表接口纯 Python 即可用；搜索/正文等**门控接口需要一台
> 能运行该 App 的 Android 设备**（真机或模拟器 + `frida-server`）来产生 Metasec
> 签名。本仓库的开发机（x86_64 Linux）**没有** adb/frida/模拟器，且该 APK 只含
> `armeabi-v7a`，因此无法在本机启动 App——这是环境缺失，非代码问题。详见
> [DESIGN.md §7](DESIGN.md)。

---

## 1. Quick start

```bash
cd rea/apk/fqnovel_api
./run.sh selftest                      # runs every endpoint and prints a summary
./run.sh list --tab store --json       # 书城首页
./run.sh list --tab mall --count 10    # 书城 Tab 信息流
./run.sh search --query "斗罗大陆"      # 搜索 (see gating note)
./run.sh download --book-id 7221013548120411151 --item-ids 1,2,3 --batch
./run.sh download-book --out out/book.txt  # whole book -> txt (needs signer)
python examples/export_open_books.py       # open book list -> out/books.txt (no signer)
python -m unittest -v tests.test_smoke # unit + live tests
```

> **Signing is required for content.** `download-book` runs the whole
> list → directory → chapter → `.txt` pipeline and stops with a clear `GATED`
> message when no signer is attached. Plug in a signer (section 5) and the same
> command produces the chapter text.

Or use it as a library:

```python
from fqnovel import FqnovelClient
c = FqnovelClient()
r = c.book_list_tab(stream_count=10)
print(r.json["data"]["tab_item"][0]["cell_data"][:2])
```

---

## 2. Discovered endpoints

Endpoints come from `@RpcOperation` annotations on `com.dragon.read.rpc.rpc.c$a`
(BookApiService) and `com.dragon.read.rpc.rpc.g6$a` (ReaderApiService), plus the
KMP proxy `com.dragon.read.kmprpc.reader.saas.rpc.n`.

### Book list (open, no signature)

| key                 | URL                                           | request model                           |
| ------------------- | --------------------------------------------- | --------------------------------------- |
| `store_home`        | `GET /reading/bookapi/bookstore/homepage/v1/` | `GetBookMallMainRequest` (no fields)    |
| `mall_tab`          | `GET /reading/bookapi/bookmall/tab/v1/`       | `BookstoreTabRequest` (83 fields)       |
| `category_booklist` | `GET /reading/bookapi/category/booklist/v1/`  | `ReadingBookapiCategoryBooklistRequest` |
| `book_extra`        | `GET /reading/bookapi/book_extra/v1/`         | `BookExtraRequest`                      |

### Book search (gateway-gated)

| key           | URL                                       | request model                      |
| ------------- | ----------------------------------------- | ---------------------------------- |
| `search_page` | `GET /reading/bookapi/search/page/v1/`    | `GetSearchPageRequest` (50 fields) |
| `search`      | `GET /reading/bookapi/search/search/v1/`  | `SearchRequest`                    |
| `suggest`     | `GET /reading/bookapi/search/suggest/v1/` | `SuggestRequest`                   |

### Content / download (gateway-gated)

| key                 | URL                                  | request model      |
| ------------------- | ------------------------------------ | ------------------ |
| `reader_full`       | `GET /reading/reader/full/v1/`       | `FullRequest`      |
| `reader_batch_full` | `GET /reading/reader/batch_full/v1/` | `BatchFullRequest` |
| `reader_newfull`    | `GET /reading/reader/newfull/v1/`    | `FullRequest`      |

Host: `https://api5-normal-sinfonlinea.fqnovel.com` (evidence: full URLs inside
dex, e.g. `.../reading/bookapi/widgets/book/`). Legacy `reading.snssdk.com` is a
fallback. The `v:version` path placeholder resolves to a service version
(`v1` here).

### Request field names

Full lists live in `fqnovel/endpoints.py` (from each model's
kotlinx.serialization descriptor):

- `BookstoreTabRequest`: `tab_index, tab_type, offset, session_id, current_name,
  stream_count, client_req_type, ...` (83)
- `GetSearchPageRequest`: `query, offset, search_id, passback, use_correct,
  tab_type, search_source, user_is_login, count, ...` (50)
- `FullRequest`: `item_id, novel_text_type, comic_resolution, unlock_mode,
  req_type, book_id, key_register_ts`
- `BatchFullRequest`: `item_ids, book_id, req_type, novel_text_type,
  key_register_ts`
- `BookDetailRequest`: `book_id, category_name, source, vs_id_type,
  video_series_id, without_video, book_name, show_character_module, from_same_ip`

---

## 3. Request computation pipeline

1. **URL** — `com.bytedance.multi.rpc.core.proxy.a.f(...)` builds
   `"https://" + host(serviceName) + path`, then substitutes `:placeholders`
   (e.g. `:version`).
2. **Business params** — the request object is serialized with
   kotlinx.serialization to a `JsonObject`, then flattened to `key=value` query
   pairs (snake_case keys above).
3. **Common params** — appended by TTNet `NetworkParams.addCommonParams` using
   `org.chromium.CronetAppProviderManager` + the app hook `zg3.a`
   (`NetworkParams$ApiProcessHook`). See `fqnovel/common_params.py`:
   `aid, app_name, version_code, version_name, manifest_version_code,
   update_version_code, device_platform, os, os_api, os_version, device_model,
   device_brand, device_type, device_id, iid, openudid, cdid, clientudid,
   channel, ac, resolution, dpi, language, region, carrier_region, _rticket, ts,
   ssmix` (+ optional `sig_hash`).
4. **Signature** — `NetworkParams.tryAddSecurityFactor(url, headers)` casts the
   registered callback to `ms.bd.c.g5` and calls `ms.bd.c.k3.a(...)`, i.e. the
   **native Metasec** library `libmetasec_ml.so`. It returns a `Map<header,
   value>` (names decrypted at runtime). OkHttp uses
   `OkHttp3SecurityFactorInterceptor`, Cronet uses
   `AbsCronetDependAdapter.onCallToAddSecurityFactor`.

---

## 4. Verification results (live gateway, 2026-10)

| endpoint                                | without signer                        | note                      |
| --------------------------------------- | ------------------------------------- | ------------------------- |
| `bookstore/homepage/v1/`                | **HTTP 200, code 0**, ~82 KB          | full JSON list ✅         |
| `bookmall/tab/v1/`                      | **HTTP 200, code 0**, ~77 KB          | full JSON feed ✅         |
| `category/booklist/v1/`                 | **HTTP 200, code 0**                  | `{"data":{"data":[]}}` ✅ |
| `book_extra/v1/`                        | **HTTP 200, code 0**                  | ✅                        |
| `search/page/v1/`                       | 200 `{"code":100103,"PARAM_INVALID"}` | gated ❌                  |
| `detail/v1/`, `directory/all_items/v1/` | 200 empty body                        | gated ❌                  |
| `reader/full/v1/`, `batch_full/v1/`     | 200 empty body                        | gated ❌                  |

**Conclusion:** the book-list APIs need no signature and are fully usable
anonymously. Search / detail / content endpoints are rejected by the API
gateway (`X-Agw-Info` present) unless a valid Metasec signature is attached.

`python -m unittest -v tests.test_smoke` asserts exactly this.

---

## 5. Signing (native)

The signer is native and cannot be exercised on a plain x86_64 Linux host:

- `libmetasec_ml.so` is an **armeabi-v7a Android (bionic)** JNI library.
- It needs an ARM runtime, `JNI_OnLoad` with a live `JavaVM`, an Android
  `Context`, and device state.

Three supported ways to attach a signer (all pluggable in `fqnovel/signer.py`):

1. **Capture headers once** on a device:
   ```bash
   frida -U -f com.dragon.read -l hooks/frida_metasec.js
   adb pull /data/local/tmp/fqnovel_headers.json
   ./run.sh --sign-headers ./fqnovel_headers.json search --query "斗罗大陆"
   ```
2. **Live bridge** (fresh headers per request):
   ```bash
   pip install frida frida-tools
   python hooks/signer_bridge.py         # http://127.0.0.1:8686/sign
   FQNOVEL_SIGN_SERVER=http://127.0.0.1:8686/sign ./run.sh search --query "斗罗大陆"
   ```
   The bridge calls the app's own `NetworkParams.tryAddSecurityFactor(url, Map)`,
   which is the real Metasec algorithm.
3. **Extract + probe the .so**:
   ```bash
   ./run.sh extract-so        # writes fqnovel/native/libs/*.so + sha256
   ./run.sh probe-native      # reports ELF arch and why dlopen cannot run here
   ```

`fqnovel/signer.py` exposes `NullSigner`, `HeaderFileSigner`, `RemoteSigner`,
`NativeSigner`; the client picks one from `FQNOVEL_SIGN_HEADERS` /
`FQNOVEL_SIGN_SERVER` / `FQNOVEL_NATIVE_LIB`.

---

## 6. Layout

```
fqnovel_api/
├── README.md                  # usage guide (this file)
├── DESIGN.md                  # design + reverse-engineering logic
├── cli.py                     # one-stop CLI
├── run.sh                     # one-command runner
├── requirements.txt
├── fqnovel/
│   ├── config.py              # appid/version/host/UA
│   ├── common_params.py       # common parameter builder
│   ├── endpoints.py           # paths + serialized field names
│   ├── signer.py              # signing abstractions
│   ├── client.py              # FqnovelClient
│   └── native/
│       ├── extract_so.py      # pull .so out of the APK
│       └── load_metasec.py    # ctypes loader + diagnostics
├── hooks/
│   ├── frida_metasec.js       # capture / RPC sign()
│   └── signer_bridge.py       # HTTP signer bridge over frida
├── examples/export_open_books.py  # open book list -> txt
└── tests/test_smoke.py
```

## 7. Evidence map

| claim         | source                                                                                 |
| ------------- | -------------------------------------------------------------------------------------- |
| endpoints     | `c$a` / `g6$a` @RpcOperation annotations; `kmprpc.reader.saas.rpc.n`                   |
| field names   | `*$a` kotlinx descriptors (`addElement`)                                               |
| host          | `api5-normal-sinfonlinea.fqnovel.com` URLs in dex                                      |
| appid 1967    | `dragon1967://` scheme in dex                                                          |
| common params | `NetworkParams`, `CronetAppProviderManager`, hook `zg3.a`                              |
| signature     | `tryAddSecurityFactor` -> `ms.bd.c.k3.a`; `AbsCronetDependAdapter`; `libmetasec_ml.so` |
