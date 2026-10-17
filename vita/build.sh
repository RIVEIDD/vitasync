#!/usr/bin/env bash
# Compile l'appli Vita sous WSL. Usage : wsl -d Ubuntu-24.04 -- bash vita/build.sh
set -euo pipefail
export VITASDK="${VITASDK:-$HOME/vitasdk}"
export PATH="$VITASDK/bin:$PATH"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HOME/vitasync-vita-build"
mkdir -p "$BUILD"
cmake -S "$SRC" -B "$BUILD" > "$BUILD/cmake.log"
make -C "$BUILD" -j"$(nproc)" > "$BUILD/make.log" 2>&1 || { grep -E "error" "$BUILD/make.log"; exit 1; }
mkdir -p "$SRC/build"
cp "$BUILD/savemgr.vpk" "$SRC/build/vitasync.vpk"
echo "OK $SRC/build/vitasync.vpk"
