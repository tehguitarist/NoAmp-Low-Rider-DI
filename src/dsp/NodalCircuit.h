#pragma once

// Bilinear-companion nodal (MNA) linear-circuit engine (NoAmp Low Rider DI).
//
// Used for op-amp-embedded LINEAR stages where the op-amp output feeds back into its own input
// network (active Sallen-Key filters, inverting tone/gain stages) — cases the ideal-op-amp
// feedback-leg decomposition (OpAmpStage.h) can't express. For a linear circuit this is
// mathematically identical to a WDF realisation (same trapezoidal/bilinear cap discretisation, same
// warp, same accuracy); MNA just handles ideal op-amps + arbitrary topology directly. Passive
// bridges still use the WDF numeric R-type (RtypeNumeric.h); the Phase-4 nonlinear zener stays
// wave-domain WDF. Every stage validated against an independent frequency-domain nodal reference.
//
// Model: resistors and (trapezoidal-companion) capacitors between nodes; ideal op-amps as nullors
// (V+ == V-, output sources arbitrary current). One scalar input voltage drives the circuit through
// whatever elements connect to kInput. The system matrix is assembled + inverted at prepare() (and
// on any resistance change via rebuild()); per sample only the RHS changes.
//
// Node ids: 0..N-1 are internal unknowns; kDatum(-1) = VCOM signal ground; kInput(-2) = the driven
// input node (known voltage = the process() argument).

#include <array>
#include <cmath>
#include <cstddef>
#include <vector>

namespace nalr
{
class NodalCircuit
{
public:
    static constexpr int kDatum = -1;
    static constexpr int kInput = -2;  // first driven input; further inputs are -3, -4, ...
    static constexpr int kInput2 = -3;
    static constexpr int kMaxInputs = 4;
    static constexpr int kMaxDim = 16; // internal nodes + op-amp current unknowns

    static bool isInput(int node) noexcept { return node <= kInput; }
    static int inputIndex(int node) noexcept { return kInput - node; } // -2->0, -3->1, ...

    void setNumNodes(int n) noexcept { numNodes = n; }

    // Returns the resistor's index, for later setResistorValue() (e.g. pots). Call rebuild() after.
    int addResistor(int a, int b, double R)
    {
        resistors.push_back({ a, b, 1.0 / R });
        return (int) resistors.size() - 1;
    }
    void setResistorValue(int idx, double R) noexcept { resistors[(size_t) idx].g = 1.0 / R; }
    void addCapacitor(int a, int b, double C) { caps.push_back({ a, b, C, 0.0, 0.0 }); }
    // Ideal op-amp: forces V(p) == V(nn); its output node sources whatever current is needed.
    void addOpAmp(int pNode, int nNode, int outNode) { opamps.push_back({ pNode, nNode, outNode }); }
    void addUnityBuffer(int inNode, int outNode) { addOpAmp(inNode, outNode, outNode); }
    void setOutputNode(int node) noexcept { outputNode = node; }

    void prepare(double fs)
    {
        for (auto& c : caps)
        {
            c.Gc = 2.0 * c.C * fs;
            c.Ieq = 0.0;
        }
        rebuild();
    }

    void reset() noexcept
    {
        for (auto& c : caps)
            c.Ieq = 0.0;
    }

    // Rebuild + invert the system matrix (call after any resistance change). Uses current cap Gc.
    void rebuild()
    {
        dim = numNodes + (int) opamps.size();
        double M[kMaxDim * kMaxDim] = {};

        auto stampG = [&](int a, int b, double g) {
            if (a >= 0) M[a * dim + a] += g;
            if (b >= 0) M[b * dim + b] += g;
            if (a >= 0 && b >= 0) { M[a * dim + b] -= g; M[b * dim + a] -= g; }
        };
        for (const auto& r : resistors) stampG(r.a, r.b, r.g);
        for (const auto& c : caps) stampG(c.a, c.b, c.Gc);

        for (int j = 0; j < (int) opamps.size(); ++j)
        {
            const int row = numNodes + j; // current-unknown / constraint index
            const auto& o = opamps[(size_t) j];
            if (o.out >= 0) M[o.out * dim + row] += 1.0;         // output current enters KCL of out node
            if (o.p >= 0) M[row * dim + o.p] += 1.0;             // constraint: V(p) - V(n) = 0
            if (o.n >= 0) M[row * dim + o.n] -= 1.0;
        }

        invert(M, dim, Minv);
    }

    inline double process(double vin) noexcept
    {
        const double vins[kMaxInputs] = { vin, 0.0, 0.0, 0.0 };
        return solve(vins);
    }

    // Two-input form (e.g. BLEND: dry on kInput, wet on kInput2).
    inline double process(double vin0, double vin1) noexcept
    {
        const double vins[kMaxInputs] = { vin0, vin1, 0.0, 0.0 };
        return solve(vins);
    }

private:
    inline double solve(const double* vins) noexcept
    {
        double rhs[kMaxDim] = {};

        auto vinOf = [&](int node) -> double { return vins[inputIndex(node)]; };

        // Input-coupled resistors: a conductance g to a known input node injects g*vin into the far
        // internal node.
        for (const auto& r : resistors)
        {
            if (isInput(r.a) && r.b >= 0) rhs[r.b] += r.g * vinOf(r.a);
            else if (isInput(r.b) && r.a >= 0) rhs[r.a] += r.g * vinOf(r.b);
        }
        // Capacitors: Norton history source (+Ieq into a, -Ieq out of b) plus, for an input-coupled
        // cap, the companion conductance term Gc*vin into the far internal node (same as a resistor).
        for (const auto& c : caps)
        {
            if (c.a >= 0) rhs[c.a] += c.Ieq;
            if (c.b >= 0) rhs[c.b] -= c.Ieq;
            if (isInput(c.a) && c.b >= 0) rhs[c.b] += c.Gc * vinOf(c.a);
            else if (isInput(c.b) && c.a >= 0) rhs[c.a] += c.Gc * vinOf(c.b);
        }

        double x[kMaxDim] = {};
        for (int i = 0; i < dim; ++i)
        {
            double s = 0.0;
            for (int j = 0; j < dim; ++j)
                s += Minv[i * dim + j] * rhs[j];
            x[i] = s;
        }

        auto V = [&](int node) -> double {
            return node == kDatum ? 0.0 : isInput(node) ? vinOf(node) : x[node];
        };

        for (auto& c : caps) // trapezoidal cap state update: Ieq_next = 2*Gc*v - Ieq.
        {
            const double v = V(c.a) - V(c.b);
            c.Ieq = 2.0 * c.Gc * v - c.Ieq;
        }

        return V(outputNode);
    }

    struct Resistor { int a, b; double g; };
    struct Cap { int a, b; double C, Gc, Ieq; };
    struct OpAmp { int p, n, out; };

    static bool invert(const double* A, int n, double* out) noexcept
    {
        double m[kMaxDim][2 * kMaxDim] = {};
        for (int i = 0; i < n; ++i) { for (int j = 0; j < n; ++j) m[i][j] = A[i * n + j]; m[i][n + i] = 1.0; }
        for (int col = 0; col < n; ++col)
        {
            int piv = col; double best = std::abs(m[col][col]);
            for (int r = col + 1; r < n; ++r) { const double v = std::abs(m[r][col]); if (v > best) { best = v; piv = r; } }
            if (best < 1e-300) return false;
            if (piv != col) for (int j = 0; j < 2 * n; ++j) { const double t = m[col][j]; m[col][j] = m[piv][j]; m[piv][j] = t; }
            const double d = m[col][col];
            for (int j = 0; j < 2 * n; ++j) m[col][j] /= d;
            for (int r = 0; r < n; ++r) { if (r == col) continue; const double f = m[r][col]; if (f != 0.0) for (int j = 0; j < 2 * n; ++j) m[r][j] -= f * m[col][j]; }
        }
        for (int i = 0; i < n; ++i) for (int j = 0; j < n; ++j) out[i * n + j] = m[i][n + j];
        return true;
    }

    std::vector<Resistor> resistors;
    std::vector<Cap> caps;
    std::vector<OpAmp> opamps;
    int numNodes = 0, dim = 0, outputNode = kDatum;
    double Minv[kMaxDim * kMaxDim] = {};
};
} // namespace nalr
