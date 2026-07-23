# HQ/Eco + 2-Halley omega — implementation plan (work order)

> Authored 2026-07-23 from a CPU-optimisation pass. This is a **work order for a fresh session** —
> follow it top to bottom. It is self-contained; every file/line reference was traced live against
> `main` at authoring time (line numbers may drift a little — grep for the quoted anchor text).
> Delete this file once the work lands (or move it under `docs/history/`).

## Goal — two coupled changes

1. **Make the default zener omega solve cheaper, for free.** Drop `nalr::AccurateOmega` from 3 Halley
   steps to **2**. Measured: 27% off the `ZenerFeedbackClipper` cost, and **−123 dB waveform
   deviation from the current 3-step sound even at hard clip** (i.e. inaudible / indistinguishable).
   This becomes the new **HQ-on (default)** path.
2. **Add an HQ/Eco toggle** whose OFF (Eco) path swaps the zener omega solve to chowdsp's **omega4**.
   Measured: 62% off the clipper (2.65×), at the cost of ~0.75% RMS waveform deviation **at hard
   clip only** (−42 dB; inaudible at normal levels, near the audible edge only when driven hard).
   Default is **HQ on**. omega4 is *only ever* reached via the explicit Eco opt-in — the shipped
   default never uses it, so dsp.md's "do NOT use the default omega" standing rule is **not
   violated** (the rule governs the default path; Eco is a labelled lower-quality mode, exactly the
   dsp.md "HQ / Eco mode" pattern).

### Why this is the right shape (don't re-derive — it's measured)
- FeatureProfile's original "omega4 is accuracy-equivalent" conclusion was measured **only up to
  0.05 V in (barely onto the knee)**. Pushing into the hard-clip regime (0.5–1.5 V in) shows omega4
  *does* deviate (~−42 dB). So the two modes are genuinely different → a toggle is justified, not a
  no-op. 2-Halley, by contrast, is indistinguishable from today at every level → safe as the default.
- The lever is **V1L/V2 only** (the zener revisions). **V1E has no zener** — its only nonlinearity is
  the rail clip (already ADAA, a free win). So the HQ button is **inert on V1 Early** by design. Keep
  the toggle always visible/enabled anyway (simplest; it's live on the two revisions people reach for
  drive on). Do NOT try to gray it out per-revision.

### Reproduce the measurements (optional sanity check before starting)
`/private/tmp/.../scratchpad/omega_compare.cpp` from the authoring session is gone with that session;
if you want the numbers again, the method is: instantiate `nalr::ZenerFeedbackClipper<Prov>` with
`setParams(10e3, 220e3, 220e-12)`, render 997 Hz at input amps {0.05, 0.5, 1.5} V, and compare the
output waveform RMS-error (in dB) of a 2-Halley provider and `chowdsp::Omega::Omega` against the
`nalr::AccurateOmega` (3-step) reference. CPU: time `.process()` over ~4M samples per provider.

---

## Change 1 — 2-Halley (do this first, it's a one-liner + comment fix)

**File: `src/dsp/AccurateOmega.h`**
- Line ~45: `for (int i = 0; i < 3; ++i)` → `for (int i = 0; i < 2; ++i)`.
- Fix the now-stale doc so it matches: the loop comment (lines ~40–44) currently says three steps are
  needed for double precision "from the simple seed"; update it to state 2 steps are used (residual
  ~1e-4 near x=1), which is **>1000× more accurate than omega4 and far below audible** — that
  headroom is why 2 is safe here. Also the header block (line ~16) still says "two Halley iterations"
  — that becomes correct again, but reword it to explain the deliberate 2-step choice + the Eco lever.

That is the entire HQ-on quality change. `AccurateOmega` is the default template arg on
`ZenerPairT`/`ZenerFeedbackClipper`, so this flows to production with no other edit.

**Gate for Change 1:** in `tests/ZenerClipTest.cpp` (already exercises the clipper + DC transfer vs an
independent exact-Newton solve), add/confirm an assertion that the WDF DC transfer still matches the
exact solver to well within the existing spec (was 1.4e-5 below knee / 1e-7 through it — 2-Halley
will not move these meaningfully). This proves 2-Halley didn't regress the solve.

---

## Change 2 — runtime HQ/Eco branch + plumbing

### 2a. The runtime branch — `src/dsp/ZenerPairT.h`
`chowdsp::Omega::Omega::omega(x)` (→ omega4) is already reachable (`#include <chowdsp_wdf/chowdsp_wdf.h>`
at line 65; API confirmed in `libs/chowdsp_wdf/include/chowdsp_wdf/math/omega.h`).

In `ZenerPairT` (class starting ~line 78):
- Add a member: `bool highQ = true;`
- Add a setter: `void setHighQuality(bool b) noexcept { highQ = b; }`
- In `reflected()` (line ~137), replace the single `OmegaProvider::omega(...)` call (line ~141) with a
  runtime branch. Extract the argument first for clarity:
  ```cpp
  const T arg = lrio + lambda * wdf.a * ovt + rio;
  const T om  = highQ ? OmegaProvider::omega(arg)                 // HQ: the template provider (2-Halley AccurateOmega in production)
                      : (T) chowdsp::Omega::Omega::omega((double) arg); // Eco: omega4
  wdf.b = wdf.a + (T) 2 * lambda * (R_Is - vt * om);
  ```
- **Keep the `OmegaProvider` template param** (don't hardcode AccurateOmega) — FeatureProfile's
  compile-time A/B (`<nalr::AccurateOmega>` vs `<chowdsp::Omega::Omega>`) must keep working, and the
  guard in 2e relies on it. The branch predicts perfectly (highQ is block-invariant) → effectively
  free, per dsp.md.

### 2b. Forward `setHighQuality` up the existing chain (mirror `setADAA` exactly)
Each of these already has a `setADAA`/similar one-line forwarder — add `setHighQuality` right beside it:
- **`src/dsp/ZenerPairT.h` → `ZenerFeedbackClipper`** (class ~line 175): 
  `void setHighQuality(bool b) noexcept { zener.setHighQuality(b); }`
- **`src/dsp/ZenerDriveModule.h`** (has `clipB`, and `setADAA` at ~line 185):
  `void setHighQuality(bool b) noexcept { clipB.setHighQuality(b); }`
- **`src/dsp/ZenerDriveClipRecovery.h`** (`drive` member; `setADAA` forwarder at ~line 71):
  `void setHighQuality(bool b) noexcept { drive.setHighQuality(b); }`
- **`src/dsp/V1LateDSP.h`** and **`src/dsp/V2DSP.h`** (both have `driveRegion` + a `setADAA` forwarder):
  `void setHighQuality(bool b) noexcept { driveRegion.setHighQuality(b); }`
- **`src/dsp/V1EarlyDSP.h`**: add a **no-op** so the processor can call it uniformly across revisions:
  `void setHighQuality(bool) noexcept {}  // V1 Early has no zener; HQ is inert here`

### 2c. APVTS parameter — `src/PluginProcessor.{h,cpp}`
- **Header** (`src/PluginProcessor.h`): add id constant next to the others (~line 79):
  `static constexpr const char* idHQ = "hq";` and a cached pointer next to `pBypass` (~line 105):
  `std::atomic<float>* pHQ = nullptr;`
- **`createParameterLayout()`** (`src/PluginProcessor.cpp`, the `params.push_back(...)` block ~line 57):
  **append** (don't reorder existing params — APVTS recalls by string ID, and existing saved
  sessions/presets lack `hq` and will correctly default to true):
  ```cpp
  params.push_back(std::make_unique<juce::AudioParameterBool>(juce::ParameterID{idHQ, 1}, "HQ", true));
  ```
- Cache the pointer wherever the others are fetched (grep `pBypass =`): `pHQ = ...getRawParameterValue(idHQ);`
- **In `processBlock`**, in each of the three dsp loops (`dspEarly`/`dspLate`/`dspV2`, ~lines 213–224,
  right where `d.setOversamplingFactor(wantFactor)` is called), add:
  `d.setHighQuality(pHQ->load() > 0.5f);`
  (V1E's is the no-op — harmless, keeps the loop bodies uniform.)

### 2d. UI toggle — `src/PluginEditor.{h,cpp}` (per `ui.md` "bottom strip")
`ui.md` specifies exactly: place it **with the OS selectors**, "a lit-on / dim-off toggle button
immediately after the RENDER box… with a brief hover tooltip… keep it visually distinct from the
scale/menu buttons."
- **Header**: add `juce::TextButton hqButton{"HQ"};` near `scaleButton` (~line 101) and
  `std::unique_ptr<juce::ButtonParameterAttachment> hqAttach;` near `bypassAttach` (~line 109).
- **`.cpp` constructor** (near the `osRenderAttach` / `scaleButton` setup, ~line 273–318): configure
  `hqButton` as a toggle (`setClickingTogglesState(true)`), give it a distinct `setComponentID` (e.g.
  `"hq"`; only add a matching LookAndFeel branch if the default toggle look is wrong — otherwise reuse
  existing styling), `setTooltip("High-quality drive solver. Off = Eco: lighter CPU, subtly coarser at high drive.")`,
  `addAndMakeVisible`, and bind `hqAttach = std::make_unique<juce::ButtonParameterAttachment>(*apvts.getParameter(Proc::idHQ), hqButton);`.
- **`resized()`** (~lines 491–509, the OS strip layout): allocate a small slot for `hqButton` in the
  strip between the RENDER combo (`osRenderBox`) and the right-hand `scaleButton` group. Match the
  scaled-metric style used for the neighbours (`* sc`, `boxVPad`).
- If a `TooltipWindow` isn't already instantiated in the editor, add one (grep `TooltipWindow`) so the
  tooltip actually shows.

### 2e. FeatureProfile guard — `tests/FeatureProfile.cpp`
dsp.md: "Add a FeatureProfile guard asserting HQ-off is bit-identical to the omega4 chain, so the
button can't silently become a no-op." Add a small section that:
- Renders the **production-typed** clipper `nalr::ZenerFeedbackClipper<nalr::AccurateOmega>` with
  `setHighQuality(false)` (the Eco runtime branch), and
- Renders `nalr::ZenerFeedbackClipper<chowdsp::Omega::Omega>` with `setHighQuality(true)` (omega4 via
  template),
- over an identical driven signal, and **asserts the two outputs are bit-identical** (exact `==` per
  sample, or max-abs-diff == 0.0). If they diverge, the Eco branch isn't actually reaching omega4 →
  fail. Keep the existing Feature 1 (now: "2-Halley HQ default vs omega4 Eco") + Feature 2 blocks;
  update Feature 1's prose so it reports the 2-Halley-vs-omega4 CPU ratio and states the toggle
  decision was made (HQ default on).

---

## Validation checklist (run before declaring done)
- [ ] `cmake --build build` — clean, **zero warnings** (project standard).
- [ ] `ctest` — all green. Specifically confirm these still pass and cover the change:
  - `ZenerClipTest` (2-Halley solve accuracy — Change 1 gate)
  - `FeatureProfile` (the new HQ-off==omega4 bit-identity guard — Change 2e gate)
  - `StateRoundTrip` (the new `hq` param round-trips through save/restore)
  - `FactoryPresetsTest` (36 presets still load; they predate `hq` → default true; **check this test
    doesn't assert an exact parameter count** — if it does, update the count, don't regenerate presets)
  - `RevisionSwitchTest` / `FullSweepTest` (HQ plumbing didn't break revision switching or sweeps)
  - `UIRenderProbe` (the OS strip still lays out at all 3 UI scales with the new button — eyeball the
    PNGs; send to the user for the visual sign-off `build.md`/`build-plan.md` Phase 8 requires — do
    NOT self-approve UI).
- [ ] `PerfBenchmark` — record fresh numbers. Expect HQ-on (2-Halley) V1L/V2 slightly cheaper than the
  current README table; add an Eco (HQ-off) row or note. Update the README "Performance" section
  (2026-07-23 table) with the new HQ-on defaults + the Eco delta.
- [ ] `auval -v aufx NALR LPrc` still **PASSES** (new param must not break AU validation).
- [ ] Bump the plugin VERSION (forces Logic AU rescan; also this is a user-facing feature addition).
- [ ] Update docs: `CLAUDE.md` "Current step" (one line: HQ/Eco added, 2-Halley default) and the
  `dsp.md` "HQ / Eco mode" section (it currently says the profile found *no* real lever and no toggle
  was added — that conclusion is now superseded: the hard-clip regime FeatureProfile hadn't probed
  makes omega4 a genuine Eco lever; record the reversal + the measurement that drove it).

## Risks / notes for the implementer
- **Preset compatibility is fine** (APVTS keys by string ID; `hq` appended, defaults true). The only
  trap is a test that hardcodes a parameter *count* — see FactoryPresetsTest checkbox above.
- **Don't reorder** existing APVTS params or member declarations that back them (architecture.md:
  breaks saved-session recall silently). Append only.
- **Keep the omega template param** on the zener classes (2a) — removing it breaks FeatureProfile's
  compile-time A/B and the 2e guard.
- **UI is user-validated**, not self-reviewed — send `UIRenderProbe` PNGs to the user for the layout
  sign-off before considering the UI done.
