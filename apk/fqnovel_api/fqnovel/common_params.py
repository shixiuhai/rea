"""ByteDance/TTNet common request parameters.

The parameter name set below is the one assembled by
``com.bytedance.frameworks.baselib.network.http.NetworkParams`` together with
the Cronet app-provider (``org.chromium.CronetAppProviderManager``) and the
app hook ``zg3.a`` (``NetworkParams$ApiProcessHook``).  Literal ``&name=``
fragments for these names are present in the APK dex files.

Only the parameters required by the *open* endpoints are mandatory; the rest
are copied to look like a real client.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from . import config


@dataclass
class DeviceProfile:
    """A pseudo device identity used to build common params."""

    device_id: str = ""
    iid: str = ""            # install_id
    openudid: str = ""
    cdid: str = ""
    clientudid: str = ""
    device_model: str = "MI 8"
    device_brand: str = "Xiaomi"
    device_type: str = "MI 8"
    os_api: str = "29"
    os_version: str = "10"
    resolution: str = "1080*2340"
    dpi: str = "440"
    language: str = "zh"
    region: str = "CN"
    carrier_region: str = "CN"
    channel: str = "toutiao_android"
    ac: str = "wifi"
    # Optional; list endpoints work without it.
    sig_hash: str = ""

    @classmethod
    def random(cls, seed: Optional[int] = None) -> "DeviceProfile":
        rng = random.Random(seed)
        # 19-digit numeric id, matching the shape of real device/install ids.
        did = "".join(str(rng.randint(0, 9)) for _ in range(19))
        iid = "".join(str(rng.randint(0, 9)) for _ in range(19))
        return cls(
            device_id=did,
            iid=iid,
            openudid="".join(rng.choice("0123456789abcdef") for _ in range(16)),
            cdid=str(uuid.uuid4()),
            clientudid=str(uuid.uuid4()),
        )


def build_common_params(device: Optional[DeviceProfile] = None,
                        extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return the common query parameters for a request.

    ``_rticket``/``ts`` are millisecond timestamps and must be regenerated per
    request (a fresh call is cheap).
    """
    device = device or DeviceProfile.random()
    ts = str(int(time.time() * 1000))
    params: Dict[str, str] = {
        "aid": str(config.APP_ID),
        "app_name": config.APP_NAME,
        "version_code": str(config.VERSION_CODE),
        "version_name": config.VERSION_NAME,
        "manifest_version_code": str(config.MANIFEST_VERSION_CODE),
        "update_version_code": str(config.UPDATE_VERSION_CODE),
        "device_platform": config.DEVICE_PLATFORM,
        "os": config.OS,
        "os_api": device.os_api,
        "os_version": device.os_version,
        "device_model": device.device_model,
        "device_brand": device.device_brand,
        "device_type": device.device_type,
        "device_id": device.device_id,
        "iid": device.iid,
        "openudid": device.openudid,
        "cdid": device.cdid,
        "clientudid": device.clientudid,
        "channel": device.channel,
        "ac": device.ac,
        "resolution": device.resolution,
        "dpi": device.dpi,
        "language": device.language,
        "region": device.region,
        "carrier_region": device.carrier_region,
        "_rticket": ts,
        "ts": ts,
        "ssmix": "a",
    }
    if device.sig_hash:
        params["sig_hash"] = device.sig_hash
    if extra:
        params.update({k: str(v) for k, v in extra.items() if v is not None})
    return params
