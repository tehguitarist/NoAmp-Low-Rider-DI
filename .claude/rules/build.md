# Build Rules (generic pedal plugin)

## Toolchain

- **CMake only** (no Projucer). `cmake_minimum_required(VERSION 3.15)` on line 1.
- C++17. Target macOS 10.13+ for AU.
- JUCE 8+ and `chowdsp_wdf` (header-only) as submodules under `libs/`.
- Optional but recommended: **xsimd** (accelerates R-type adaptor matrix multiplies). Add it
  before chowdsp_wdf and `#include <xsimd/xsimd.hpp>` before `<chowdsp_wdf/chowdsp_wdf.h>`.
- `-Wall -Wextra` on GCC/Clang. **MSVC's `cl.exe` misparses `-Wextra`** (error D8021: `/W` with a
  non-numeric arg), so gate the flags — `/W4` on MSVC, `-Wall -Wextra` otherwise — via a
  `PEDAL_WARNING_FLAGS` variable (see `CMakeLists.txt.template`). A hardcoded `-Wextra` breaks the
  Windows CI build.
- **Mark third-party headers (chowdsp_wdf, etc.) as SYSTEM includes.** `juce_recommended_warning_flags`
  enables `-Wshadow-field-in-constructor`, which fires harmlessly on chowdsp_wdf's header-only
  constructors (param/field name reuse — not a bug). Don't silence it globally (you'd blind yourself
  to real shadowing). Instead, after `add_subdirectory(libs/chowdsp_wdf)`, re-declare its includes as
  SYSTEM so its noise vanishes while your code stays fully warned (CMake 3.15-compatible):
  ```cmake
  get_target_property(_chowdsp_inc chowdsp_wdf INTERFACE_INCLUDE_DIRECTORIES)
  set_target_properties(chowdsp_wdf PROPERTIES INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_chowdsp_inc}")
  ```

## Submodule setup

```bash
git submodule add https://github.com/juce-framework/JUCE libs/JUCE
git submodule add https://github.com/Chowdhury-DSP/chowdsp_wdf libs/chowdsp_wdf
git submodule add https://github.com/xtensor-stack/xsimd libs/xsimd   # optional
git submodule update --init --recursive
```

## Build commands

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target <Pedal>_AU      # AU (primary)
cmake --build build                          # everything (incl. test exes)
```
`COPY_PLUGIN_AFTER_BUILD TRUE` installs the AU to `~/Library/Audio/Plug-Ins/Components/` on build.
Logic caches AU components — **bump the project VERSION** to force a rescan after changes, or
remove/re-add the plugin.

## Project layout

```
<pedal>/
├── CMakeLists.txt
├── CLAUDE.md
├── .claude/rules/{build,architecture,dsp,ui,circuit}.md
├── .claude/agents/{schematic-checker,dsp-validator}.md
├── docs/{calibration-and-gain-staging,ui-peripheral-spec,validation-and-capture}.md
├── analysis/                   # gen_test_signal.py + analyze.py (A/B harness) + offline_render.cpp
├── schematics/                 # the source-of-truth images
├── src/
│   ├── PluginProcessor.{h,cpp}
│   ├── PluginEditor.{h,cpp}
│   ├── dsp/                     # one header per stage + a top-level wrapper
│   ├── ui/                      # PedalLookAndFeel, VUMeter, ThreePositionSwitch, LEDIndicator
│   └── utils/TaperUtils.h
├── libs/ {JUCE, chowdsp_wdf, xsimd}
└── tests/                       # per-stage validation exes
```

## Testing pattern (validate every stage before moving on)

- Linear stages: pure chowdsp_wdf console exes (no JUCE) — verify frequency response vs the
  expected transfer function (e.g. RC −3 dB point within 1%).
- Nonlinear stage: sine-in clipping checks; aliasing measurement (needs JUCE for
  `juce::dsp::Oversampling` + FFT — use `juce_add_console_app`).
- Full chain: integration test across all modes × OS factors; assert finite, bounded output.
- Throwaway measurement probes (gain, rail levels) are fine standalone:
  `c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/Probe.cpp -o build/Probe` (works for
  headers that only pull chowdsp_wdf, not JUCE).
- **UI changes: render the actual editor headlessly to an image, don't eyeball-only.** A small
  console exe that constructs the real `AudioProcessorEditor` off-screen, paints it into a
  `juce::Image`, and writes a PNG lets you verify layout/colour/scale changes (including at
  different UI-scale factors) with no DAW and no physical display attached — useful in CI or over
  SSH. Cheap to add (`juce_add_console_app`) and catches layout regressions a build-success check
  alone won't.

### Performance & fidelity probes (CPU/quality optimisation pass)

Three `juce_add_console_app` probes that render the real chain and measure — register them with
`add_test()` as **finite-only** probes (assert no NaN/Inf; do NOT gate on absolute CPU %, CI speed
varies). They produce the data for the HQ/Eco decision (see `dsp.md` "HQ / Eco mode"):
- **`PerfBenchmark`** — CPU % of realtime + `getLatencySamples()` per OS factor × clip mode. Times a
  fixed-length render (wall-clock vs audio duration). → a README "Performance" table.
- **`FeatureProfile`** — per performance-affecting feature, measures CPU cost AND accuracy delta
  TOGETHER (toggle it, null/THD/aliasing the result) so each is classed "free win" (keep always-on)
  vs "real CPU/accuracy lever" (HQ candidate). Needs the DSP stages templated on the omega provider
  (defaulted, production-unchanged) to A/B accurate-omega vs `omega4`.
- **`OSFidelity`** — how close 1×/2×/4× are to 8× (FR + harmonic-vs-aliasing), the common DAW
  low-OS case. Separates the wanted distortion (faithful at low OS) from aliasing + top-octave droop
  (the OS-only fixes). Drove the low-OS top-octave restore (`dsp.md`).

## Code style

`.clang-format` (LLVM base, IndentWidth 4, ColumnLimit 120, BreakBeforeBraces Attach,
AllowShortFunctionsOnASingleLine Inline, SortIncludes false) and a `.clang-tidy`
(`clang-diagnostic-*,clang-analyzer-*,modernize-*,readability-*,-readability-magic-numbers`) are
included in the template root.

## CI / release (GitHub Actions)

`.github/workflows/ci.yml` and `release.yml` are included as templates (replace `<Pedal>`/`<Cod1>`/
`<Mfr1>`). They're inert inside the template folder — GitHub only reads `.github` at a repo root, so
they activate once you copy the template out.

- **ci.yml** — builds + runs `ctest` on macOS/Windows/Linux on every push/PR. Register each pass/fail
  test exe with `add_test()` (see `CMakeLists.txt.template`) so the whole suite runs as one gate.
- **release.yml** — `workflow_dispatch` ONLY (no push trigger, so a release is never cut by accident):
  builds VST3 (+ AU on macOS) on all three OSes, packages a per-platform installer (see below)
  alongside a raw zip, publishes a draft GitHub Release. macOS signing/notarization steps are
  wired in but gated on secrets that don't exist until you add them (see "macOS signing" below) —
  delete those steps if you don't want signed releases yet; without them, Gatekeeper just warns on
  first launch and the plugin still works.
- **auval on CI gotcha:** a freshly-copied `.component` isn't registered with the
  `AudioComponentRegistrar` on a clean runner, so `auval` fails with "didn't find the component" /
  `-50`. Bounce the registrar (`killall -9 AudioComponentRegistrar`) and retry — the ci.yml step
  already does this. If headless `auval` stays flaky, switch to **pluginval** (validates the built
  bundle directly, no OS registration, cross-platform so it covers the VST3 too).

### macOS signing + notarization

Requires an active Apple Developer Program membership ($99/yr; Developer ID certs aren't available
on a free account). Nine GitHub Actions secrets, all referenced by `release.yml`'s `macos` job —
six for signing the AU/VST3 bundles, three more for signing the `.pkg` installer itself (a
**separate cert type** — "Developer ID Installer", not "Application"; `codesign` and `productsign`
each only accept their own cert type):

| Secret | What it is |
|---|---|
| `APPLE_CERT_P12_BASE64` | `base64 -i DeveloperIDApplication.p12` of your exported Developer ID Application cert |
| `APPLE_CERT_PASSWORD` | the password the `.p12` was exported with |
| `APPLE_SIGNING_IDENTITY` | e.g. `Developer ID Application: Name (TEAMID)` — copy exactly from `security find-identity -v -p codesigning` |
| `APPLE_TEAM_ID` | your 10-character Apple Developer Team ID |
| `APPLE_ID` | the Apple ID email used for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | an app-specific password for that Apple ID (generate at appleid.apple.com → Sign-In and Security, NOT your main password) |
| `APPLE_INSTALLER_CERT_P12_BASE64` | `base64 -i DeveloperIDInstaller.p12` of your exported **Developer ID Installer** cert |
| `APPLE_INSTALLER_CERT_PASSWORD` | the password that `.p12` was exported with |
| `APPLE_INSTALLER_SIGNING_IDENTITY` | e.g. `Developer ID Installer: Name (TEAMID)` — copy exactly from `security find-identity -v -p basic` (Installer certs don't show under `-p codesigning`) |

To get the Application cert: developer.apple.com/account/resources/certificates → **+** →
**Developer ID Application** → upload a CSR generated via Keychain Access (Certificate Assistant →
Request a Certificate from a CA → Saved to disk) → download and double-click the `.cer` to install
it → export it + its private key from Keychain Access as a `.p12` (this is what gets base64'd).
Repeat the same flow choosing **Developer ID Installer** for the second cert — both certs can share
one CSR/private key, or use separate ones; either works.

Set secrets via `gh secret set <NAME>` (reads from stdin/`--body`; omit the value to get a
non-echoing interactive prompt) — re-set a cert + its password **together** if either ever needs
changing, to avoid a stale-pairing mismatch (`SecKeychainItemImport: MAC verification failed`,
i.e. "wrong password" — almost always means the `.p12` and password secrets don't actually match).

### Installers

`installer/macos/`, `installer/windows/`, `installer/linux/` hold basic per-platform installer
scripts/configs, wired into `release.yml`'s "Build installer" step in each platform job:

- **macOS** (`build_installer.sh` + `Distribution.xml`) — a `.pkg` built via `pkgbuild` +
  `productbuild`, with a **choice screen for AU vs VST3** (both selected by default — this is the
  one platform with two formats, so it's the only one that needs a choice screen at all; AU and
  VST3 sit at the top level of `<choices-outline>` with no wrapping parent `<line>` — adding one
  creates an unnamed parent group in the customize screen). Wraps whatever bundles are on disk.
  With the three `APPLE_INSTALLER_*` secrets configured (see above), `release.yml`'s "Sign +
  notarize installer" step also `productsign`s, notarizes, and staples the `.pkg` itself, so it
  shows no Gatekeeper warning on double-click either. Without those secrets, delete that step —
  the `.pkg` still builds and wraps signed/notarized bundles fine, just unsigned itself.
- **Windows** (`Pedal.nsi`, NSIS) — VST3 only (no AU on Windows). `makensis` ships on
  `windows-latest` runners but is **not on PATH** — locate it via `Get-Command` / common install
  paths first, falling back to `choco install nsis` (see the release.yml step for the exact logic;
  don't assume a bare `makensis` call works).
- **Linux** (`build_deb.sh` + `control`) — VST3 only (no AU on Linux), a `.deb` via `dpkg-deb`
  (preinstalled on `ubuntu-latest`).

All three scripts take `<version> [artefacts-dir] [output-dir]` and expect the relevant build
targets already built. Rename `<Pedal>` placeholders throughout (including inside `Pedal.nsi`'s
filename and `installer/linux/control`'s package name/maintainer) when copying the template out.

## Validation gates (do not skip ahead)

- Both plugin formats build + scan/load in a DAW; CI is green on all three platforms.
- Each linear stage's frequency response verified before the next stage.
- Each switch position verified independently.
- Nonlinear aliasing acceptable at the shipped OS default.
- Reference validation vs real-pedal captures (FR / THD-by-band / null) — see
  `docs/validation-and-capture.md`.
- Final: full control sweep — no instability, clicks, or NaN/Inf.
