#pragma once

#include <cstring>

// Exact-equality change detection for the "skip stage recompute if the pot didn't move" gate used
// throughout the DSP graphs (V1EarlyDSP/V1LateDSP/V2DSP setParams()). Exact equality is the correct
// semantic here (recompute only when the value genuinely changed, not "changed by more than some
// epsilon") — this just expresses that comparison without tripping -Wfloat-equal, via a bit-pattern
// compare instead of `!=` (bit-identical to `!=` for the finite, non-NaN pot values these gates see).
namespace nalr
{
[[nodiscard]] inline bool changed(double a, double b) noexcept
{
    return std::memcmp(&a, &b, sizeof(double)) != 0;
}
} // namespace nalr
