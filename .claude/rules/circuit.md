# Circuit Reference — <PEDAL NAME>  (TEMPLATE — fill in from the schematic)

> This file is the **source of truth** for component values and topology. Fill every `<...>`
> placeholder by reading the schematic directly. Do NOT approximate or copy values from a build
> kit / forum trace without confirming against the primary schematic.

## Schematics

List every image in `schematics/` and its role (which is authoritative for what):

| File | Role |
|------|------|
| `<primary>.png` | Primary source of truth for values + topology |
| `<switch_ref>.jpg` | Authoritative for switch/diode network |
| `<older>.png` | Cross-reference only — values may differ |

---

## ⚠ Schematic-reading gotchas (these caused real bugs)

- **Resistor value notation:** `2m2` / `2M2` means **2.2 MΩ**, `2k2` = 2.2 kΩ, `2R2` = 2.2 Ω. The
  letter is the decimal point AND the multiplier. Misreading `2m2` as 2.2 Ω (or 2.2 mΩ) is an easy
  ~6-orders-of-magnitude error. Double-check every R against its neighbours' magnitudes.
- **Series vs pulldown:** a large resistor (e.g. 2.2 MΩ) at the input is usually a **pulldown to
  ground** (bias/pop suppression), not a series element. A 2.2 MΩ *series* resistor would attenuate
  ~14 dB and roll off treble hard — if your model does that, you've mis-traced the topology.
- **Pot wiring:** confirm pin1/pin3/wiper → node mapping for every pot. "Rheostat" (wiper jumpered
  to an end, no ground leg) behaves very differently from a "divider". Trace it; don't assume.
- **Taper:** note the designation (A = audio/log, B = linear). Kits sometimes substitute — follow
  the schematic, not the kit.
- **Op-amp inverting vs non-inverting:** verify which input the signal enters. Confirm output
  polarity later with a DC-step test per stage.
- **Power section parts in the signal columns:** supply-filter R/C (and any series Schottky) can be
  mislabelled as signal-path parts. Exclude VREF-divider and supply-filter components from the DSP
  model.
- **Same component VALUES ≠ same TOPOLOGY across schematic sources.** Two traces of "the same"
  pedal (an early-revision trace vs a later kit/clone) can share every R/C value designator-for-
  designator while wiring one network completely differently (e.g. two independent series R+C
  branches to ground vs one shared branch-then-shared-cap-to-ground). Identical values are NOT
  evidence the topology matches — redraw the actual node connections from each source before
  concluding they agree, especially for any network feeding a feedback node.
- **If the pedal has more than one full gain stage in series ("channels"/"sides"), verify the
  ACTUAL signal order from the real unit (continuity trace, or an unambiguous schematic signal-flow
  arrow) — never assume it from the physical/UI layout.** Left-to-right, top-to-bottom, or numbered
  ("1/2", "A/B") layout is a UI/PCB-placement convention and is **not** guaranteed to match which
  stage the input actually reaches first. Getting this backwards still produces a plausible-sounding
  result (both stages are real circuits, so it "works"), which is exactly why it's easy to ship
  before catching it — confirm the order explicitly, early, rather than inferring it.

---

## Signal path summary

```
IN → <input/bias> → <stage 1 ...> → <clip?> → <tone?> → <recovery> → <volume> → OUT
```
VREF = VCC/2 virtual ground; model bipolar (VREF = 0 V signal ground). Note the supply (e.g. single
9 V, no charge pump) since it sets op-amp output headroom — see calibration doc §6.

## Component values (from `<primary>` — do not approximate)

### <Stage / network name>
| Ref | Value | Function |
|-----|-------|----------|
| `<R?>` | `<value>` | `<role>` |
| `<C?>` | `<value>` | `<role>` |
| `<pot>` | `<A/B + value>` | `<taper + role>` |

(Repeat a table per network: input, each gain stage, clipping/diode network, tone, recovery,
output volume.)

### Nonlinear devices
- Diode/transistor type: `<e.g. 1N4148>`. **Use exact datasheet/Shockley params** (Is, Vt, n, Rs).
  `nDiodes` in chowdsp = ideality factor n, NOT a count.

## Topology — node graphs

Describe each stage's connections at the node level (use these directly to build the WDF tree).
Mark each stage **Linear** or **Nonlinear**, and which adaptor type it needs (series/parallel tree
vs R-type for feedback). For switched sub-circuits, list each position as a distinct topology →
precomputed scattering matrix.

## Op-amp model

- Part + supply; not rail-to-rail → model asymmetric output saturation (calibration doc §6).
- Ideal op-amp for the gain/feedback solve; rails as a separate output clamp.

## Interactive / coupled controls

List any controls that share a network and MUST be modelled coupled (not independent), e.g. a tone
control inside a feedback web. Note `ScopedDeferImpedancePropagation` when updating them together.

## Multi-stage / multi-channel series pedals

If the unit is actually two (or more) complete, otherwise-independent gain circuits in series —
each with its own controls and its own bypass — model each as its own instance of the same
per-channel DSP class, instantiated once per stage, NOT as a single wider circuit. Each instance
needs its own independent bypass/crossfade so the hardware's independent footswitches are honoured.

A fixed factory/kit modification present on only ONE of the otherwise-identical stages (not a
runtime-switchable mode) belongs at **construction time**, not as an APVTS parameter — see
`dsp.md` "Fixed (non-runtime) circuit variants".

Document the verified real processing order explicitly here (see the gotcha above) and keep it
separate from whatever names/labels the UI uses for each stage — naming and signal order are
independent facts and don't have to agree (see `architecture.md` / `ui.md` if the two diverge).

## Validation notes

Record anything that differs between schematic versions, any component absent from some traces, and
any value you had to resolve by measurement/judgement (with the reasoning).
