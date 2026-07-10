#!/usr/bin/env bash
# TEMPLATE: replace <Pedal> below with your plugin's product name (must match juce_add_plugin's
# PRODUCT_NAME / the *_artefacts directory name CMake produces). Inert until copied to a repo root.
#
# Builds a macOS .pkg installer for <Pedal> from already-built Release artefacts, with a
# choose-your-format screen (AU / VST3, both selected by default — see Distribution.xml).
#
# Usage:
#   installer/macos/build_installer.sh <version> [artefacts-dir] [output-dir]
#
#   <version>        e.g. 0.1.0 — matches CMakeLists.txt's project() version
#   [artefacts-dir]  defaults to build/<Pedal>_artefacts/Release (repo-root relative)
#   [output-dir]     defaults to the current directory
#
# Requires the AU and VST3 targets to already be built (<Pedal>_AU, <Pedal>_VST3).
# The resulting .pkg is unsigned — sign it separately with productsign if distributing outside
# this machine. (Signing the AU/VST3 bundles themselves, separately, before packaging — see
# release.yml's codesign/notarytool steps — still applies and is independent of this.)

set -euo pipefail

VERSION="${1:?Usage: build_installer.sh <version> [artefacts-dir] [output-dir]}"
ARTEFACTS="${2:-build/<Pedal>_artefacts/Release}"
OUTDIR="${3:-.}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

AU_SRC="$ARTEFACTS/AU/<Pedal>.component"
VST3_SRC="$ARTEFACTS/VST3/<Pedal>.vst3"

[ -d "$AU_SRC" ] || { echo "error: $AU_SRC not found — build <Pedal>_AU first" >&2; exit 1; }
[ -d "$VST3_SRC" ] || { echo "error: $VST3_SRC not found — build <Pedal>_VST3 first" >&2; exit 1; }

AU_ROOT="$WORK/au-root"
VST3_ROOT="$WORK/vst3-root"
mkdir -p "$AU_ROOT" "$VST3_ROOT"
cp -R "$AU_SRC" "$AU_ROOT/"
cp -R "$VST3_SRC" "$VST3_ROOT/"

pkgbuild --root "$AU_ROOT" \
    --identifier com.<you>.<pedal>.au \
    --version "$VERSION" \
    --install-location "/Library/Audio/Plug-Ins/Components" \
    "$WORK/au.pkg"

pkgbuild --root "$VST3_ROOT" \
    --identifier com.<you>.<pedal>.vst3 \
    --version "$VERSION" \
    --install-location "/Library/Audio/Plug-Ins/VST3" \
    "$WORK/vst3.pkg"

sed "s/__VERSION__/$VERSION/g" "$SCRIPT_DIR/Distribution.xml" > "$WORK/Distribution.xml"

mkdir -p "$OUTDIR"
OUT_PKG="$OUTDIR/<Pedal>-macOS-v${VERSION}-Installer.pkg"

productbuild --distribution "$WORK/Distribution.xml" \
    --package-path "$WORK" \
    "$OUT_PKG"

echo "Built $OUT_PKG"
