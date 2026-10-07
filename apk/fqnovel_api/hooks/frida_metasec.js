/*
 * frida_metasec.js -- capture the exact Metasec signature headers produced by
 * the real app on a device/emulator.
 *
 * Usage (device with frida-server, app installed):
 *     frida -U -f com.dragon.read -l hooks/frida_metasec.js --no-pause
 *
 * It hooks the app entry that computes the security factor:
 *     com.bytedance.frameworks.baselib.network.http.NetworkParams.tryAddSecurityFactor
 * and dumps {url -> headers}. The dumped JSON can be consumed by the Python
 * client via --sign-headers (HeaderFileSigner), or you can drive the RPC
 * export from a bridge for fresh signatures (see hooks/signer_bridge.py).
 */

"use strict";

function jmapToObject(jmap) {
  const out = {};
  if (!jmap) return out;
  try {
    const it = jmap.keySet().iterator();
    while (it.hasNext()) {
      const k = it.next();
      const v = jmap.get(k);
      out[String(k)] = String(v);
    }
  } catch (e) {
    out["_error"] = String(e);
  }
  return out;
}

function hookTryAddSecurityFactor() {
  const NetworkParams = Java.use(
    "com.bytedance.frameworks.baselib.network.http.NetworkParams",
  );
  NetworkParams.tryAddSecurityFactor.overload(
    "java.lang.String",
    "java.util.Map",
  ).implementation = function (url, headers) {
    const result = this.tryAddSecurityFactor(url, headers);
    try {
      const obj = jmapToObject(result);
      if (Object.keys(obj).length) {
        console.log("[metasec] " + url);
        console.log("[metasec] headers = " + JSON.stringify(obj));
        try {
          const f = new File("/data/local/tmp/fqnovel_headers.json", "w");
          f.write(
            JSON.stringify({
              url: url,
              headers: obj,
              captured_at: Date.now() / 1000,
            }),
          );
          f.flush();
          f.close();
        } catch (e) {
          /* ignore */
        }
      }
    } catch (e) {
      console.log("[metasec] parse error: " + e);
    }
    return result;
  };
  console.log("[metasec] hooked NetworkParams.tryAddSecurityFactor");
}

/* Optional: hook the Cronet depend adapter (the entry used by Cronet stack). */
function hookCronetAdapter() {
  try {
    const Adapter = Java.use(
      "com.bytedance.ttnet.cronet.AbsCronetDependAdapter",
    );
    Adapter.onCallToAddSecurityFactor.implementation = function (url, headers) {
      const r = this.onCallToAddSecurityFactor(url, headers);
      console.log(
        "[cronet] onCallToAddSecurityFactor " +
          url +
          " -> " +
          JSON.stringify(jmapToObject(r)),
      );
      return r;
    };
  } catch (e) {
    /* class may differ across versions */
  }
}

/*
 * RPC exports. `sign(url, headersJson)` calls the app's own
 * NetworkParams.tryAddSecurityFactor(url, Map) which runs the real Metasec
 * native signer and returns fresh headers. Drive it from hooks/signer_bridge.py
 * (RemoteSigner bridge).
 */
rpc.exports = {
  lastheaders: function () {
    try {
      const f = new File("/data/local/tmp/fqnovel_headers.json", "r");
      const s = f.readAll();
      f.close();
      return s;
    } catch (e) {
      return "{}";
    }
  },
  sign: function (url, headersJson) {
    const HashMap = Java.use("java.util.HashMap");
    const NetworkParams = Java.use(
      "com.bytedance.frameworks.baselib.network.http.NetworkParams",
    );
    const map = HashMap.$new();
    try {
      const h = headersJson ? JSON.parse(headersJson) : {};
      Object.keys(h).forEach(function (k) {
        const ArrayList = Java.use("java.util.ArrayList");
        const list = ArrayList.$new();
        list.add(String(h[k]));
        map.put(String(k), list);
      });
    } catch (e) {
      /* ignore malformed */
    }
    const out = NetworkParams.tryAddSecurityFactor(url, map);
    return JSON.stringify(jmapToObject(out));
  },
};

Java.perform(function () {
  hookTryAddSecurityFactor();
  hookCronetAdapter();
});
