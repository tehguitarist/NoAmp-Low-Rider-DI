#!/usr/bin/env bash
# TEMPLATE: replace <Pedal> below with your plugin's product name. Inert until copied to a repo
# root. Also edit installer/linux/control (package name, maintainer, description) before using.
#
# Builds a .deb installer for <Pedal>'s VST3 from an already-built Release artefact.
# Linux has no AU format, so there's no plugin-type choice here — VST3 only.
#
# Usage:
#   installer/linux/build_deb.sh <version> [artefacts-dir] [output-dir]
#
#   <version>        e.g. 0.1.0 — matches CMakeLists.txt's project() version
#   [artefacts-dir]  defaults to build/<Pedal>_artefacts/Release (repo-root relative)
#   [output-dir]     defaults to the current directory
#
# Requires the <Pedal>_VST3 target to already be built, and dpkg-deb installed.

set -euo pipefail

VERSION="${1:?Usage: build_deb.sh <version> [artefacts-dir] [output-dir]}"
ARTEFACTS="${2:-build/<Pedal>_artefacts/Release}"
OUTDIR="${3:-.}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VST3_SRC="$ARTEFACTS/VST3/<Pedal>.vst3"
[ -d "$VST3_SRC" ] || { echo "error: $VST3_SRC not found — build <Pedal>_VST3 first" >&2; exit 1; }

ROOT="$WORK/pedal"
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/lib/vst3"
cp -R "$VST3_SRC" "$ROOT/usr/lib/vst3/"

sed "s/__VERSION__/$VERSION/" "$SCRIPT_DIR/control" > "$ROOT/DEBIAN/control"

find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +

mkdir -p "$OUTDIR"
OUT_DEB="$OUTDIR/<Pedal>-Linux-v${VERSION}-Installer.deb"

dpkg-deb --build --root-owner-group "$ROOT" "$OUT_DEB"

echo "Built $OUT_DEB"
