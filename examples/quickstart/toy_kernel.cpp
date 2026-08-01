// The quickstart kernel, C++ side: the point-function port of
// toy_kernel.f90's scale_clip_acc. Extracting it needs only `clang++` on
// PATH.

// One grid point: scale a by s, clip to lo from below, accumulate into b.
void scale_clip_acc_point(double& b, double const a, double const s, double const lo)
{
  double const w = s * a;
  if (w < lo)
  {
    b = b + lo;
  }
  else
  {
    b = b + w;
  }
}
