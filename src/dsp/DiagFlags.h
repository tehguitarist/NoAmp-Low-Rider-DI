#pragma once
#include <cstdlib>

// Diagnostic-only environment flags. All default OFF and have ZERO effect on shipped/DAW audio.
// They exist so capture-free measurement probes can reach conditions the normal signal path cannot
// express (mirrors V1LPhaseCorrectionPrototype's NALR_ALLPASS_HZ pattern).

namespace nalr
{
// NALR_NODRY: force the BLEND dry leg to zero. At blend=1.0 the BLEND pot's "off" (dry) leg is never
// truly infinite, so it LEAKS the dry signal into the mix -- that leak is precisely the
// destructive-interference mechanism under study in the V1L bass-hump investigation (see
// V1LPhaseCorrectionPrototype.h). To measure the PURE wet-path transfer/phase, that leak must be
// removed; blend=1.0 alone does not do it. Set NALR_NODRY to any value to null the dry tap.
inline bool noDryDiag() noexcept
{
    static const bool v = std::getenv("NALR_NODRY") != nullptr;
    return v;
}
} // namespace nalr
