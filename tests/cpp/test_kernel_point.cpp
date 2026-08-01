// Conformance fixture (C++ side): the clang-kernel subset in
// miniature — the point-function mirror of tests/f90/test_kernel_doconcurrent.
// A per-point scalar kernel exercising: Real&/Real const intent mapping, a
// local decl-with-init, if / else if / else, _rt literals, + - * /,
// comparisons, an abs call, parameter mutation, and a skipped declaration
// attribute. The prelude mirrors amrex::Real / amrex::literals / amrex::Math
// so the fixture is self-contained (no includes; clang++ alone suffices).

using Real = double;
constexpr Real operator""_rt(long double v) { return static_cast<Real>(v); }
namespace Math {
inline Real abs(Real x) { return x < 0 ? -x : x; }
}

__attribute__((always_inline))
void clamp_scale_point(Real& x_out, Real const x_in, Real const lo) noexcept
{
    Real const w = 2.0_rt * x_in - x_out;
    if (Math::abs(w) < lo) {
        x_out = lo;
    } else if (w * w > 4.0_rt * lo) {
        x_out = x_in + w / 2.0_rt;
    } else {
        x_out = (w + lo) * 0.5_rt;
    }
}
