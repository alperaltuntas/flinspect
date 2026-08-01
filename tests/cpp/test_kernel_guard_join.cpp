// Conformance fixture (C++ side): the sequential guarded control-flow
// join — the point-function mirror of tests/f90/test_kernel_ifstmt_join. The
// body ends with two guarded assignments to Real& state; the second guard's
// RHS reads b, which the first if may have just updated. functionalize must
// thread the merged (post-first-if) value of b, not its input — the exact
// shape of ppm_limit_cw84_point's trailing pair.

using Real = double;
constexpr Real operator""_rt(long double v) { return static_cast<Real>(v); }

void guard_pair_point(Real& b, Real& c, Real const a) noexcept
{
    Real const t = 2.0_rt * a;
    if (t > b) b = t - 1.0_rt;
    if (t < c) c = b + t;
}
