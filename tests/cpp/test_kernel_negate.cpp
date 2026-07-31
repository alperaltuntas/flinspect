// Track B conformance fixture (C++ side): unary minus — the mirror of
// tests/f90/test_kernel_negate, with one deliberate asymmetry it exists to
// pin: C++ unary minus binds TIGHTER than `*`, so `-2.0_rt * x` parses as
// `(-2.0_rt) * x` (Neg on the literal), unlike Fortran's R1008 where
// `-2.0*x(i)` negates the whole term. Also covers the bare leaf (-y) and
// negation of a source-parenthesized sum (-(x + y)).

using Real = double;
constexpr Real operator""_rt(long double v) { return static_cast<Real>(v); }

void neg_clip_point(Real& y, Real const x) noexcept
{
    if (x < -y) {
        y = -2.0_rt * x;
    } else {
        y = -(x + y);
    }
}
