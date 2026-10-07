"""Static configuration discovered by reverse engineering the APK.

All values are evidence-backed (see ../README.md):
  * package_name / version_* -- AndroidManifest.xml + package info of the APK
  * APP_ID 1967             -- app deep-link scheme "dragon1967://" found in dex strings
  * API_HOST                -- full URLs embedded in dex, e.g.
        https://api5-normal-sinfonlinea.fqnovel.com/reading/bookapi/widgets/book/
"""

APP_ID = 1967
APP_NAME = "novelapp"
PACKAGE_NAME = "com.dragon.read"

VERSION_NAME = "7.3.9.32"
VERSION_CODE = 73932
MANIFEST_VERSION_CODE = 73932
UPDATE_VERSION_CODE = 73932

DEVICE_PLATFORM = "android"
OS = "android"

# Primary API host for /reading/bookapi/* and /reading/reader/*
API_HOST = "https://api5-normal-sinfonlinea.fqnovel.com"
# Fallback / legacy host observed in dex strings.
LEGACY_HOST = "https://reading.snssdk.com"

# Device register endpoint observed in dex strings.
DEVICE_REGISTER_URL = "https://log.snssdk.com/service/2/device_register/"

# Path version segment used to replace the ":version" placeholder in
# $GET /reading/.../v:version/  (substituted by multi.rpc proxy at runtime).
API_VERSION = "1"

# UA is not signature-relevant for the open endpoints but should look realistic.
USER_AGENT = (
    "com.dragon.read/{vc} (Linux; U; Android {os_ver}; zh_CN; {model}; "
    "Build/QQ3A.200805.001; Cronet/TTNetVersion:9f3a3a61 2023-01-01)"
)
