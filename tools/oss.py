#!/usr/bin/env python3
"""Minimal Aliyun OSS v1 client to list and fetch the band's official firmware.

Read-only use (list / get) for retrieving our own device's firmware image from the
vendor's OTA bucket. Credentials are NOT stored here: they are the ones hard-coded in
the Yoho Sports APK (update/Aliyun.java) and must be supplied at runtime via env vars
(OSS_AK, OSS_SK) or a local, untracked file `tools/oss.env` of the form:

    OSS_AK=...
    OSS_SK=...

Usage:
  tools/oss.py list [prefix]            # list objects (default whole bucket, max-keys=500)
  tools/oss.py get <objectKey> <dest>   # download one object
Env overrides: OSS_AK, OSS_SK, OSS_ENDPOINT, OSS_BUCKET.
"""
import base64
import hashlib
import hmac
import os
import sys
import time
import urllib.parse
import urllib.request
from email.utils import formatdate

_envfile = os.path.join(os.path.dirname(__file__), "oss.env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.split("#", 1)[0].strip()
        if "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

ENDPOINT = os.environ.get("OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
BUCKET = os.environ.get("OSS_BUCKET", "mcube-ota")
try:
    AK = os.environ["OSS_AK"]
    SK = os.environ["OSS_SK"]
except KeyError:
    sys.exit("set OSS_AK and OSS_SK (env or tools/oss.env); see this file's docstring")


SIGV = os.environ.get("OSS_SIGV", "4")  # Aliyun is disabling V1; default to V4
REGION = os.environ.get("OSS_REGION") or ENDPOINT.split(".")[0].replace("oss-", "")


def _auth_v1(method, key, query, headers):
    date = formatdate(usegmt=True)
    headers["Date"] = date
    sts = f"{method}\n\n\n{date}\n/{BUCKET}/{key}"
    sig = base64.b64encode(hmac.new(SK.encode(), sts.encode(), hashlib.sha1).digest()).decode()
    headers["Authorization"] = f"OSS {AK}:{sig}"


def _auth_v4(method, key, query, headers):
    now = time.gmtime()
    iso, day = time.strftime("%Y%m%dT%H%M%SZ", now), time.strftime("%Y%m%d", now)
    headers["x-oss-date"] = iso
    headers["x-oss-content-sha256"] = "UNSIGNED-PAYLOAD"
    canon_uri = "/" + BUCKET + "/" + urllib.parse.quote(key, safe="/")
    qs = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(query))) if query else ""
    signed = {k.lower(): v for k, v in headers.items()
              if k.lower().startswith("x-oss-") or k.lower() in ("content-type", "content-md5")}
    canon_headers = "".join(f"{k}:{signed[k].strip()}\n" for k in sorted(signed))
    canon_req = f"{method}\n{canon_uri}\n{qs}\n{canon_headers}\n\nUNSIGNED-PAYLOAD"
    scope = f"{day}/{REGION}/oss/aliyun_v4_request"
    sts = f"OSS4-HMAC-SHA256\n{iso}\n{scope}\n{hashlib.sha256(canon_req.encode()).hexdigest()}"
    k_date = hmac.new(("aliyun_v4" + SK).encode(), day.encode(), hashlib.sha256).digest()
    k_region = hmac.new(k_date, REGION.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"oss", hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aliyun_v4_request", hashlib.sha256).digest()
    sig = hmac.new(k_signing, sts.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"OSS4-HMAC-SHA256 Credential={AK}/{scope},Signature={sig}")


def request(method, key="", query="", dest=None):
    headers = {}
    (_auth_v4 if SIGV == "4" else _auth_v1)(method, key, query, headers)
    url = f"https://{BUCKET}.{ENDPOINT}/" + urllib.parse.quote(key, safe="/")
    if query:
        url += "?" + query
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} {e.reason}\n{body}")
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
        return dest, len(data)
    return data


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "list":
        prefix = sys.argv[2] if len(sys.argv) > 2 else ""
        q = "max-keys=500" + (f"&prefix={prefix}" if prefix else "")
        xml = request("GET", query=q).decode("utf-8", "replace")
        import re
        for m in re.finditer(r"<Key>(.*?)</Key>.*?<Size>(.*?)</Size>", xml, re.S):
            print(f"{int(m.group(2)):>10}  {m.group(1)}")
    elif cmd == "get":
        key, dest = sys.argv[2], sys.argv[3]
        path, n = request("GET", key=key, dest=dest)
        print(f"saved {n} bytes -> {path}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
