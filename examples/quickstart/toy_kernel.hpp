#pragma once

// Quickstart toy kernel — the C++ point-function twin of
// toy_kernel.f90's scale_clip_acc, in the supported kernel subset.
//
// Deliberately STANDALONE: its own `using Real = double;`, plain reference
// parameters, no AMReX or MPI includes — extracting it needs nothing beyond
// `clang++` on PATH (the frontend's intent mapping keys on the qualType
// spellings `Real &` / `const Real`, not on where the alias comes from).

using Real = double;

// Scale a by s, clip to lo from below, accumulate into b.
inline void scale_clip_acc_point(Real& b, Real const a, Real const s, Real const lo)
{
  Real const w = s * a;
  if (w < lo)
  {
    b = b + lo;
  }
  else
  {
    b = b + w;
  }
}
