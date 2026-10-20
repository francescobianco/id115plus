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


def request(method, key="", query="", dest=None):
    date = formatdate(usegmt=True)
    resource = f"/{BUCKET}/{key}"
    string_to_sign = f"{method}\n\n\n{date}\n{resource}"
    sig = base64.b64encode(
        hmac.new(SK.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    url = f"https://{BUCKET}.{ENDPOINT}/{key}"
    if query:
        url += "?" + query
    req = urllib.request.Request(url, method=method)
    req.add_header("Date", date)
    req.add_header("Authorization", f"OSS {AK}:{sig}")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
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
