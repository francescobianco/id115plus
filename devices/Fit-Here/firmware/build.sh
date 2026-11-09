#!/bin/sh
# Build the dumper with e-lab's PHY6222 SDK, pinned, in its Docker image.
# Output: dumper/_build/fh_dumper.hex
#
# The XIP code is linked at 0x1101f000, the last 4 KB sector of the app bank. With
# `phy_flash.py --bank-offset 0xB000` the whole image stays in 0x1c000-0x1ffff.
set -e
cd "$(dirname "$0")"

REPO=https://github.com/e-labInnovations/FitPro-LP715-PHY6222
REV=4824924daa7f89d42f6cc1510d8250cd8e19e57d
IMAGE=ghcr.io/e-labinnovations/phy6222-sdk@sha256:b4b4a7047cb7f66a5ff5d8b847d8fde1f0f6040f65f20415f46118cf06882fd7
VENDOR=vendor/FitPro-LP715-PHY6222

if [ ! -d "$VENDOR/.git" ]; then
    mkdir -p "$VENDOR"
    git -C "$VENDOR" init -q
    git -C "$VENDOR" fetch -q --depth 1 "$REPO" "$REV"
    git -C "$VENDOR" checkout -q FETCH_HEAD
fi

rm -rf _core
mkdir _core
cp "$VENDOR"/lib/core/* _core/
cp dumper/core/* _core/
sed 's/ORIGIN = 0x11010100, LENGTH = 0x1ff00/ORIGIN = 0x1101f000, LENGTH = 0x1000/' \
    "$VENDOR/sdk/phy6222/misc/phy6222.ld" > _core/dumper.ld
grep -q 'ORIGIN = 0x1101f000' _core/dumper.ld

rm -rf dumper/_build
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/w -w /w/dumper "$IMAGE" \
    make -j8 "MK=/w/$VENDOR/sdk/phy6222.mk" CORE=/w/_core LDSCRIPT=/w/_core/dumper.ld
