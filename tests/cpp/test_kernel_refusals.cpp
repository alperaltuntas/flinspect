// Conformance fixture (C++ side): refusals. Each function holds one
// construct outside the supported kernel subset; the extractor must raise
// UnsupportedConstruct for every one of them (trusted base: refuse, never
// guess). Extracted one at a time via -ast-dump-filter on the function name.

using Real = double;
constexpr Real operator""_rt(long double v) { return static_cast<Real>(v); }

// Compound assignment (clang: CompoundAssignOperator, opcode +=).
void refuse_plus_equal(Real& a, Real const b) noexcept
{
    a += b;
}

// A loop statement (clang: ForStmt).
void refuse_for_loop(Real& a, Real const b) noexcept
{
    for (int i = 0; i < 3; ++i) {
        a = a + b;
    }
}

// A non-Real parameter (int by value).
void refuse_int_param(Real& a, int const n) noexcept
{
    a = a + 1.0_rt;
}

// An int literal in a Real expression: clang inserts an IntegralToFloating
// implicit cast, which is value-changing and NOT on the allowlist — the
// refusal that pins the cast allowlist itself.
void refuse_int_literal(Real& a, Real const b) noexcept
{
    a = b + 1;
}
