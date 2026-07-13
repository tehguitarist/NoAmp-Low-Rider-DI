#pragma once

// Numeric R-type scattering-matrix helper (NoAmp Low Rider DI).
//
// Several linear stages in this pedal are NOT series-parallel decomposable — the PRESENCE input
// notch, the recovery bridged-T, and the Baxandall/peaking tone stacks are all bridge topologies.
// chowdsp_wdf models those with an R-type adaptor driven by a scattering matrix S (b = S a). Rather
// than hand-transcribe a symbolic S per stage (chowdsp's own Baxandall example is a ~2000-char
// expression per entry — one typo = a silent wrong notch), we compute S *numerically* from the
// adaptor's internal topology + the live port impedances, inside the adaptor's ImpedanceCalculator.
//
// Derivation (voltage-wave convention, matching chowdsp: v=(a+b)/2, i=(a-b)/2R, i into the adaptor):
//   Treat each of the N ports as a resistor R_k (port resistance) between two internal nodes, with
//   the incident wave a_k acting as a Norton source G_k*a_k. Nodal solve gives port voltages
//   v = A^T (A Gd A^T)^{-1} A Gd a, where A is the node×port incidence matrix and Gd=diag(1/R_k).
//   Since b = 2v - a, the scattering matrix is
//       S = 2 A^T (A Gd A^T)^{-1} A Gd - I.
//   The adapted "up" port's resistance must equal the driving-point resistance seen there with all
//   other ports terminated in their port resistances (this makes S[up][up] == 0, as chowdsp
//   requires); drivingPointResistance() computes it. Validated against a frequency-domain nodal
//   reference in the per-stage tests.
//
// Node indexing: internal nodes are 0..numNodes-1; the datum (ground / VCOM signal ref) is kDatum.
// Port k connects node np[k] (+) to node nm[k] (-); its port voltage is V[np]-V[nm].

#include <array>
#include <cmath>

namespace nalr
{
namespace rtype
{
constexpr int kDatum = -1;   // ground / VCOM reference node
constexpr int kMaxNodes = 8; // max internal (non-datum) nodes across all stages here
constexpr int kMaxPorts = 12;

// In-place Gauss-Jordan inverse of an n x n row-major matrix `A` into `out`. Returns false if
// singular. n <= kMaxNodes.
inline bool invertDense(const double* A, int n, double* out) noexcept
{
    double m[kMaxNodes][2 * kMaxNodes] = {};
    for (int i = 0; i < n; ++i)
    {
        for (int j = 0; j < n; ++j)
            m[i][j] = A[i * n + j];
        m[i][n + i] = 1.0;
    }

    for (int col = 0; col < n; ++col)
    {
        int piv = col;
        double best = std::abs(m[col][col]);
        for (int r = col + 1; r < n; ++r)
        {
            const double v = std::abs(m[r][col]);
            if (v > best)
            {
                best = v;
                piv = r;
            }
        }
        if (best < 1e-300)
            return false;

        if (piv != col)
            for (int j = 0; j < 2 * n; ++j)
            {
                const double t = m[col][j];
                m[col][j] = m[piv][j];
                m[piv][j] = t;
            }

        const double d = m[col][col];
        for (int j = 0; j < 2 * n; ++j)
            m[col][j] /= d;

        for (int r = 0; r < n; ++r)
        {
            if (r == col)
                continue;
            const double f = m[r][col];
            if (f != 0.0)
                for (int j = 0; j < 2 * n; ++j)
                    m[r][j] -= f * m[col][j];
        }
    }

    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j)
            out[i * n + j] = m[i][n + j];
    return true;
}

// Stamp conductance g of a port between nodes p and m into reduced nodal matrix G (n x n).
inline void stamp(double* G, int n, int p, int mm, double g) noexcept
{
    if (p != kDatum)
        G[p * n + p] += g;
    if (mm != kDatum)
        G[mm * n + mm] += g;
    if (p != kDatum && mm != kDatum)
    {
        G[p * n + mm] -= g;
        G[mm * n + p] -= g;
    }
}

// Driving-point resistance seen at port `upIndex` with every OTHER port terminated in its port
// resistance portR[k]. portR[upIndex] is ignored. This is the value the adaptor's calcImpedance
// must return (the adapted up-port resistance).
inline double drivingPointResistance(int numPorts, int numNodes, const int* np, const int* nm, const double* portR,
                                     int upIndex) noexcept
{
    double G[kMaxNodes * kMaxNodes] = {};
    for (int k = 0; k < numPorts; ++k)
    {
        if (k == upIndex)
            continue;
        stamp(G, numNodes, np[k], nm[k], 1.0 / portR[k]);
    }

    double Ginv[kMaxNodes * kMaxNodes] = {};
    if (!invertDense(G, numNodes, Ginv))
        return 1.0e12; // effectively open

    auto gi = [&](int a, int b) -> double { return (a == kDatum || b == kDatum) ? 0.0 : Ginv[a * numNodes + b]; };
    const int p = np[upIndex], mm = nm[upIndex];
    return gi(p, p) - gi(p, mm) - gi(mm, p) + gi(mm, mm);
}

// Full scattering matrix S (numPorts x numPorts, row-major, b = S a) from all port resistances
// (including the up-port). Writes into outS.
inline void scatteringMatrix(int numPorts, int numNodes, const int* np, const int* nm, const double* portR,
                             double* outS) noexcept
{
    double Gd[kMaxPorts] = {};
    double G[kMaxNodes * kMaxNodes] = {};
    for (int k = 0; k < numPorts; ++k)
    {
        Gd[k] = 1.0 / portR[k];
        stamp(G, numNodes, np[k], nm[k], Gd[k]);
    }

    double Ginv[kMaxNodes * kMaxNodes] = {};
    invertDense(G, numNodes, Ginv);

    auto gi = [&](int a, int b) -> double { return (a == kDatum || b == kDatum) ? 0.0 : Ginv[a * numNodes + b]; };

    // W = A^T Ginv A Gd ; W[i][j] = Gd[j] * (gi(np_i,np_j) - gi(np_i,nm_j) - gi(nm_i,np_j) + gi(nm_i,nm_j))
    for (int i = 0; i < numPorts; ++i)
        for (int j = 0; j < numPorts; ++j)
        {
            const double w = Gd[j] * (gi(np[i], np[j]) - gi(np[i], nm[j]) - gi(nm[i], np[j]) + gi(nm[i], nm[j]));
            outS[i * numPorts + j] = 2.0 * w - (i == j ? 1.0 : 0.0);
        }
}
} // namespace rtype
} // namespace nalr
