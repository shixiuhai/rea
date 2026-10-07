# fqnovel_api — 设计说明与逆向逻辑汇总

本文汇总 **番茄小说 `com.dragon.read`** 的接口逆向结论、请求计算过程、
原生签名/解密链路、当前环境约束，以及“基于原 App 封装接口”的可行方案。
代码与本文一一对应；`README.md` 是使用手册，本文是**逻辑/证据**总账。

- 目标 APK：`../novelapp_43536163a_v1327_73932_73932_9e6c_1790564338.apk`
- 包名 `com.dragon.read`，versionName `7.3.9.32`，versionCode `73932`
- 交付物：纯 Python 客户端 `fqnovel/` + 设备侧签名桥 `hooks/`

---

## 1. TL;DR（关键结论）

1. **接口分两类**：
   - **开放接口**（书城/榜单/分类）→ 无需签名，纯 Python 匿名可用，已端到端验证。
   - **门控接口**（搜索主接口、详情、目录、正文）→ 需要 **Metasec 签名**，无签名被网关拒绝
     （`code=100103 PARAM_INVALID` 或空 body）。
2. **签名是原生的**：`NetworkParams.tryAddSecurityFactor` → `ms.bd.c.k3.a(...)` →
   `libmetasec_ml.so`（armeabi-v7a / Android bionic / JNI），
   头名与算法**运行时解密**，无法静态读取，也无法在 x86_64 上 dlopen。
3. **正文是加密的**：内容项带 `crypt_status / key_version / content / novel_data`，
   解密入口（疑似 `libdragon_crypt.so`）**尚未定位**，但处理方式与签名一致——
   应在真机 App 进程内调用其解密函数，而非自己逆算法。
4. **正确形态是“混合封装”**：纯 Python 协议层（已具备）+ 真机 App-backed 原生层
   （签名/解密插件）。**不要**把整个 APK 包成一个 API。
5. **本机无法启动 App**（无 adb/frida/模拟器；APK 仅 armeabi-v7a）——
   这是**环境缺失**，不是设计缺陷。设备侧代码已就位，插上设备即可用。

---

## 2. 分层架构

```
   CLI / 调用方
        │
        ▼
 ┌────────────────────────────────────────────┐
 │ 协议层（纯 Python，无设备）                 │
 │  fqnovel/client.py    组 URL + 发请求/解压  │
 │  fqnovel/common_params.py  公共参数         │
 │  fqnovel/endpoints.py  端点 + 业务字段名    │
 └───────┬───────────────────────────┬────────┘
         │ 开放请求                   │ 门控/正文
         ▼                            ▼
   requests 直发          ┌──────────────────────────────┐
         │                │ 原生层插件（fqnovel/signer.py）│
         │                │  NullSigner / HeaderFileSigner │
         │                │  RemoteSigner ──► 设备桥        │
         │                │  NativeSigner（占位，非ARM必失败）│
         │                └───────────────┬────────────────┘
         │                                ▼
         │                       hooks/signer_bridge.py
         │                                ▼
         │                       Frida 注入 App 进程
         │                       NetworkParams.tryAddSecurityFactor
         │                                ▼
         │                       libmetasec_ml.so（真算法）
         ▼
      网关 api5-normal-sinfonlinea.fqnovel.com
```

设计原则：**难点下沉到真机，协议留在本地**。开放接口不走设备（省并发/延迟）；只有
门控请求和正文解密才打到设备桥。

---

## 3. 端点清单与门控矩阵

来源：Retrofit 接口上的 `@RpcOperation` 注解
（`com.dragon.read.rpc.rpc.c$a` = BookApiService、`...g6$a` = ReaderApiService）
与 KMP 代理 `com.dragon.read.kmprpc.reader.saas.rpc.n`。

| 分类 | key                   | 路径                                       | 请求模型                                | 匿名可用 |
| ---- | --------------------- | ------------------------------------------ | --------------------------------------- | -------- |
| 书城 | `store_home`          | `/reading/bookapi/bookstore/homepage/v1/`  | `GetBookMallMainRequest`（0 字段）      | ✅       |
| 书城 | `mall_tab`            | `/reading/bookapi/bookmall/tab/v1/`        | `BookstoreTabRequest`（83 字段）        | ✅       |
| 书城 | `category_booklist`   | `/reading/bookapi/category/booklist/v1/`   | `ReadingBookapiCategoryBooklistRequest` | ✅       |
| 书城 | `book_extra`          | `/reading/bookapi/book_extra/v1/`          | `BookExtraRequest`                      | ✅       |
| 搜索 | `search_page`         | `/reading/bookapi/search/page/v1/`         | `GetSearchPageRequest`（50 字段）       | ❌ 门控  |
| 搜索 | `search`              | `/reading/bookapi/search/search/v1/`       | `SearchRequest`                         | ❌ 门控  |
| 搜索 | `suggest`             | `/reading/bookapi/search/suggest/v1/`      | `SuggestRequest`                        | ❌ 门控  |
| 正文 | `reader_full`         | `/reading/reader/full/v1/`                 | `FullRequest`                           | ❌ 门控  |
| 正文 | `reader_batch_full`   | `/reading/reader/batch_full/v1/`           | `BatchFullRequest`                      | ❌ 门控  |
| 正文 | `reader_newfull`      | `/reading/reader/newfull/v1/`              | `FullRequest`                           | ❌ 门控  |
| 其它 | `book_detail`         | `/reading/bookapi/detail/v1/`              | `BookDetailRequest`                     | ❌ 门控  |
| 其它 | `directory_all_items` | `/reading/bookapi/directory/all_items/v1/` | —                                       | ❌ 门控  |

> 另有若干**开放**搜索辅助端点（`search/hot-search`、`search/cue`、`search/rank_list`），
> 未纳入当前 `endpoints.py`，需要时可补。
>
> 路径占位符 `v:version` 由 multi-rpc 代理替换为服务版本，本构建解析为 `v1`
> （`endpoints._v`，`config.API_VERSION = "1"`）。

字段名来自各请求模型的 kotlinx.serialization 描述符（`*$a.addElement`），
完整列表见 `fqnovel/endpoints.py`（`MALL_TAB_FIELDS` / `SEARCH_PAGE_FIELDS` /
`FULL_FIELDS` / `BATCH_FULL_FIELDS` / `DETAIL_FIELDS`）。

---

## 4. 请求计算过程

实现在 `fqnovel/client.py` 的 `FqnovelClient.request()`（`client.py:147`）。

1. **URL 组装**
   `host + path`，`host` 来自 `config.API_HOST`；`:version` 已由 `endpoints._v` 展开。
2. **业务参数**
   请求对象被 kotlinx.serialization 序列化为 JSON 再展平为 `key=value` 查询串
   （字段名即上表 snake_case）。
3. **公共参数**（`common_params.build_common_params`，`common_params.py:63`）
   由 `com.bytedance.frameworks.baselib.network.http.NetworkParams`、
   Cronet 侧 `org.chromium.CronetAppProviderManager` 与应用 hook `zg3.a`
   （`NetworkParams$ApiProcessHook`）共同拼装。已复刻集合：
   `aid, app_name, version_code, version_name, manifest_version_code,
   update_version_code, device_platform, os, os_api, os_version, device_model,
   device_brand, device_type, device_id, iid, openudid, cdid, clientudid,
   channel, ac, resolution, dpi, language, region, carrier_region, _rticket, ts,
   ssmix`（可选 `sig_hash`）。
   `_rticket`/`ts` 为毫秒时间戳，**每次请求重新生成**（`common_params.py:70`）。
4. **签名**（`fqnovel/signer.py`，见 §5）
   `signer.sign(method, url, headers, body)` 返回需追加的请求头；
   `NullSigner` 返回空（故只对开放接口有效）。
5. **发送与解压**
   `requests` 发出 → `client._decompress` 处理 gzip/deflate（`client.py:132`）
   → JSON 解析。响应封装为 `Response`，`Response.ok` 同时看 `http 2xx` 与 `code==0`
   （`client.py:108`）。

设备指纹（`DeviceProfile`，`common_params.py:24`）可随机生成
（19 位数字 `device_id/iid`）。开放接口不校验其真实性。

---

## 5. 原生签名链路（Metasec）

调用链（静态逆向结论，证据见 §11）：

```
NetworkParams.tryAddSecurityFactor(url, headers)      // Java 入口
  → callback cast to ms.bd.c.g5
  → ms.bd.c.k3.a(...)                                  // 进入 native
  → libmetasec_ml.so                                   // 真算法
  → Map<headerName, headerValue>                       // 头名运行时解密
```

- Java 壳：`com.bytedance.mobsec.metasec.ml.MS extends ms.bd.c.q2`。
- 两个注入点：OkHttp 的 `OkHttp3SecurityFactorInterceptor`；
  Cronet 的 `AbsCronetDependAdapter.onCallToAddSecurityFactor`。
- 产物头示例：`X-Gorgon`、`X-Argus` 等（名称运行时解密，静态不可读）。

`libmetasec_ml.so` 事实：**armeabi-v7a / Android bionic / JNI**，
sha256 `127b052e70a81607b37580c4942c775d88907fc2cc3be105814b453ea77dd43f`，
3306768 字节。调用它需要 ARM 运行时 + `JNI_OnLoad`（live `JavaVM`）+
Android `Context` + 大量设备状态。

**为什么不能直接 `ctypes.CDLL`**（`fqnovel/native/load_metasec.py:52`、
`fqnovel/signer.py:119`）：

1. CPU 架构不匹配（x86_64 进程无法 dlopen ARM 代码）；
2. ABI 不匹配（链接 bionic 而非 glibc）；
3. 缺少初始化环境（JavaVM/Context/设备指纹）。
   因此 `NativeSigner` 是**占位实现**：`_load()` 仅做架构探测并**主动拒绝**，
   `sign()` 抛 `SignerError`。提取出的 `.so` 只落盘、_从不执行_。

`fqnovel/signer.py` 暴露四种可互换签名器：
`NullSigner`（无签名）、`HeaderFileSigner`（复用一次性抓到的头）、
`RemoteSigner`（每请求向设备桥取新头）、`NativeSigner`（占位）。
`default_signer()`（`signer.py:162`）按环境变量
`FQNOVEL_SIGN_HEADERS` / `FQNOVEL_SIGN_SERVER` / `FQNOVEL_NATIVE_LIB` 选择。

---

## 6. 正文加密与解密（未完成）

门控正文响应中的内容项（逆向所得模型 `a86.x$a`）字段：

```
content, origin_content, novel_data, crypt_status, key_version,
title, code, author_speak, block_data, ...
```

- `crypt_status != 0` 时 `content`/`novel_data` 为密文，需按 `key_version` 解出明文。
- 解密入口**尚未定位**；候选原生库：`libdragon_crypt.so`（75324 B）、
  `libencrypt.so`（18084 B）、`libEncryptor.so`（79640 B），均由
  `run.sh extract-so` 从 APK 提取。
- **处理原则与签名一致**：不自己复刻算法，改为在真机 App 进程内调用其解密函数，
  或让设备桥**直接返回明文**，Python 侧只拿 `title/text`。
- 客户端已预留解析入口：`client.extract_contents()`（`client.py:68`）
  会从任意响应中按 `_CONTENT_KEYS` 递归取最长内容串，映射 `item_id → content`。

### 6.1 直接执行 `.so`（离线仿真）实测

因为本机是 x86_64、`.so` 是 armeabi-v7a/bionic，`ctypes` 无法加载；但可以用
**Unicorn CPU 仿真**直接执行 ARM 代码（见 `fqnovel/native/emulate_so.py`）。
实测结论（真值，非推断）：

| 库                   | 可否离线执行       | 结果                                                                       |
| -------------------- | ------------------ | -------------------------------------------------------------------------- |
| `libencrypt.so`      | ✅ **可以**        | 导出若干**无 JNIEnv 的普通函数**；直接调用得到硬编码常量（见下）           |
| `libEncryptor.so`    | ⚠️ 仅 `JNI_OnLoad` | 算法经 `RegisterNatives` 动态注册，需完整 JNI 环境                         |
| `libdragon_crypt.so` | ⚠️ 仅 `JNI_OnLoad` | 同上                                                                       |
| `libmetasec_ml.so`   | ❌ 不可行          | 149 个 undefined 依赖（含 `libandroid.so`）、混淆、反调试；离开 App 无法跑 |

`libencrypt.so` 通过仿真直接调用得到的真实常量：

```
get_aes_token()       = "B5SE5K0FPA3VZZ4WHJWKBSQKX2MFGDUR"   (32)
get_dh_aes_token()    = "ac25c67ddd8f38c1b37a2348828e222e"   (32)
get_dh_gv()           = "2"                                   (DH 生成元 g)
get_dh_pv()           = "FFFFFFFF...C90FDAA2...7FFFFFFF"      (1536-bit MODP Group-5 素数 p)
set_aes_token()/_set_aes_context() = no-op（纯 bx lr）
```

**重要澄清**：`libencrypt.so` 只是**静态常量/令牌容器**（getter 返回全局指针），
其中**没有请求签名算法**；请求签名在 `libmetasec_ml.so`，而后者无法离线执行。
所以“直接跑 so 生成请求签名”这条路不成立——但“直接跑 so 提取内嵌常量/纯函数”
成立，本工具已证明可行。

复现：

```bash
pip install unicorn capstone
./run.sh emulate --lib fqnovel/native/libs/libencrypt.so --list
python -m fqnovel.native.emulate_so fqnovel/native/libs/libencrypt.so _Z8get_dh_pv --str
```

**下一步待办**：

1. 继续补全 JNI 仿真（实现 `FindClass`/`RegisterNatives`/异常查询），
   枚举 `libdragon_crypt.so` / `libEncryptor.so` 注册的 native 方法，
   直接调用其解密函数（有望离线解正文）。
2. 从 `content`/`crypt_status` 的 Java getter 追到解密调用 → JNI/`.so`，锁定入口。
3. 签名仍必须走真机桥（方案 A）。

---

## 7. 当前环境约束（为什么本机起不了 App）

实测（2026-10，本机 Ubuntu 22.04 / x86_64）：

| 检查                                                        | 结果                          |
| ----------------------------------------------------------- | ----------------------------- |
| `adb` / `frida` / `emulator` / `qemu-system-*` / `dalvikvm` | **全部缺失**                  |
| `frida` Python 模块                                         | 未安装（import 失败）         |
| 已连接设备                                                  | 无                            |
| Android SDK 环境                                            | 无 `ANDROID_*`                |
| APK 原生 ABI                                                | **仅 `lib/armeabi-v7a/`**     |
| 宿主可用资源                                                | `/dev/kvm` 存在、4 核、外网通 |

结论：**方案 A 依赖的 `frida-server` + 运行中的 `com.dragon.read` 进程在本机不存在，
且本机无法“点开”App**。即便装模拟器，APK 只有 armeabi-v7a，x86_64 模拟器也跑不了它的原生库。
设备注册实测亦无效：`POST https://log.snssdk.com/service/2/device_register/`
返回 `{"device_id":0,"install_id":0}`。

因此边界明确：**除“真机执行”外的全链路都可在本机完成并验证**（开放接口已通过；
bridge/hook/插件代码已写好）；只差一台能跑该 App 的设备。

---

## 8. “基于原程序封装接口”的三种方案

| 方案                                        | 原理                                                                             | 优点                                     | 代价                                              | 建议         |
| ------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------- | ------------ |
| **A. Frida RPC/HTTP 桥**（已实现 `hooks/`） | 注入运行中的 App，暴露 `POST /sign`，内部调 `NetworkParams.tryAddSecurityFactor` | 不改包、最灵活、可顺带解密、每请求新签名 | 需 root/模拟器 + frida-server；进程常驻；吞吐一般 | **先用它**   |
| **B. LSPosed/Xposed 模块内嵌 server**       | 模块 hook 进 App，进程内起本地 HTTP                                              | 常驻稳定                                 | 需 root + LSPosed，版本适配                       | 量大后替换 A |
| **C. 重打包 APK 注入服务**                  | 反编译 smali 加代码再签名                                                        | 单包自足                                 | 加固/签名校验/更新困难，最脆                      | 不推荐       |

**推荐形态：混合封装**——见 §2。`signer.py` 的插件位已经为此设计好；
只需再补一个对称的 `Decryptor` 插件（门控链路自动经过设备桥）。

### 落地顺序

1. 打通方案 A 最小闭环：真机 → `frida -U -f com.dragon.read -l hooks/frida_metasec.js`
   → `python hooks/signer_bridge.py` → `./run.sh search`，验证签名能解门控。
2. 在 bridge 内加解密能力（先定位入口，§6）。
3. Python 侧加 `Decryptor` 插件接口（对称于 `Signer`）。
4. 稳定后再考虑收敛成方案 B 常驻服务。

---

## 9. Frida 签名桥数据流（已实现）

```
Python 客户端                     设备（真机/模拟器）
─────────────                    ──────────────────────
RemoteSigner.sign()  ──HTTP──►   hooks/signer_bridge.py  (127.0.0.1:8686)
  POST /sign {method,url,headers}     │ frida RPC: script.exports_sync.sign(url, headersJson)
                                      ▼
                                 hooks/frida_metasec.js  (rpc.exports.sign)
                                      │ Java.use('...NetworkParams')
                                      │ .tryAddSecurityFactor(url, HashMap)
                                      ▼
                                 libmetasec_ml.so  → 真实签名头
  ◄── {"headers": {"x-gorgon": ...}} ┘
```

- Hook 点：`hooks/frida_metasec.js:35` `NetworkParams.tryAddSecurityFactor`
  的 `(String, Map)` 重载；另 hook `:60` `AbsCronetDependAdapter`。
- 也可只抓一次头写入 `/data/local/tmp/fqnovel_headers.json`
  （`frida_metasec.js:44`），再用 `HeaderFileSigner`（`--sign-headers`）复用。
- 桥是**主机无关**的：设备侧起 `http://<host>:8686/sign`，
  客户端设 `FQNOVEL_SIGN_SERVER=http://<host>:8686/sign` 即可。
- 依赖：`pip install frida frida-tools` + 设备上的 `frida-server`；
  `signer_bridge.py` 仅在运行时 import frida（可选依赖）。

---

## 10. 验证结果（live 网关，2026-10）

| 端点                                    | 无签名                                          | 说明              |
| --------------------------------------- | ----------------------------------------------- | ----------------- |
| `bookstore/homepage/v1/`                | **HTTP 200, code 0**, ~82 KB                    | 完整 JSON 列表 ✅ |
| `bookmall/tab/v1/`                      | **HTTP 200, code 0**, ~77 KB                    | 完整信息流 ✅     |
| `category/booklist/v1/`                 | **HTTP 200, code 0**                            | ✅                |
| `book_extra/v1/`                        | **HTTP 200, code 0**                            | ✅                |
| `search/page/v1/`                       | 200 `{"code":100103,"message":"PARAM_INVALID"}` | 门控 ❌           |
| `detail/v1/`、`directory/all_items/v1/` | 200 空 body                                     | 门控 ❌           |
| `reader/full/v1/`、`batch_full/v1/`     | 200 空 body                                     | 门控 ❌           |

`python -m unittest -v tests.test_smoke`（8 用例）断言以上行为，全绿。
`examples/export_open_books.py` 已导出真实书单 `out/books.txt`（56 本，
`title\tauthor\tbook_id`）。

---

## 11. 现状与路线图

**已完成**

- 纯 Python 协议层：端点、字段、公共参数、请求/解压、CLI、测试。
- 开放接口端到端可用；门控链路已实现到 `GATED` 明确报错。
- `download-book`：list → directory → 章节 → `.txt` 全流程（无签名时提示接桥）。
- `.so` 提取（`extract-so`）与架构探测（`probe-native`）。
- 设备侧签名桥（`frida_metasec.js` + `signer_bridge.py`）与四种 signer 插件。

**待办（阻塞点）**

- [ ] 定位并封装**正文解密**入口（§6）→ 加 `Decryptor` 插件。
- [ ] 真机打通方案 A 的 `search` / `reader/full`（本机无设备）。
- [ ] 评估门控接口是否叠加**用户态**（cookie/token），同样从桥获取。

**需要的外部条件**：一台能跑该 App 的 Android 设备（真机最省事）+
`frida-server` + 本机 `frida` 客户端；或一个可达的 `adb connect` 端点。

---

## 12. 合规声明

本项目仅用于**个人学习与技术研究**（协议逆向、原生分析、代理桥接），
不得用于批量抓取、内容再分发或任何商业用途；请遵守目标服务条款与当地法律。

---

## 13. 证据索引

| 结论       | 来源                                                                                  |
| ---------- | ------------------------------------------------------------------------------------- |
| 端点路径   | `c$a` / `g6$a` 的 `@RpcOperation`；`kmprpc.reader.saas.rpc.n`                         |
| 业务字段名 | `*$a` kotlinx 描述符（`addElement`）                                                  |
| host       | dex 内完整 URL `api5-normal-sinfonlinea.fqnovel.com`                                  |
| appid 1967 | dex 字符串 `dragon1967://` scheme                                                     |
| 公共参数   | `NetworkParams` + `CronetAppProviderManager` + hook `zg3.a`                           |
| 签名链路   | `tryAddSecurityFactor` → `ms.bd.c.k3.a`；`AbsCronetDependAdapter`；`libmetasec_ml.so` |
| 原生库事实 | `run.sh extract-so` / `probe-native` 输出（sha256、ELF machine）                      |
| 门控矩阵   | live 网关实测（2026-10），见 §10                                                      |
