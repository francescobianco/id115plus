#!/usr/bin/env bash
# Fetch the Macrogiga MS1793 SDK (MM32F031 + BLE radio lib) at a pinned commit.
# We do NOT vendor the SDK into this repo: it ships a binary radio library and the
# MindMotion HAL under their own terms. The build links against this clone.
set -euo pipefail

REPO="https://github.com/macrogiga/MS1793-SDK.git"
COMMIT="0ec8fc31d36591d3eb13a682253a67f9c8e52929"
DIR="$(cd "$(dirname "$0")" && pwd)/MS1793-SDK"

if [ -d "$DIR/.git" ]; then
  echo "SDK already present at $DIR"
else
  echo "Cloning $REPO ..."
  git clone --quiet "$REPO" "$DIR"
fi
git -C "$DIR" fetch --quiet origin "$COMMIT" 2>/dev/null || true
git -C "$DIR" checkout --quiet "$COMMIT"
echo "SDK ready at $DIR (commit $COMMIT)"
echo "Radio lib: $DIR/software/Src/lib/mg_BLE_lib_m0.lib"
