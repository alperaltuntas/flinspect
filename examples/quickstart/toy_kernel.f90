! The quickstart kernel, Fortran side: scale a by s, clip to lo from below,
! accumulate into b. One grid point — the same shape as its C++ twin in
! toy_kernel.cpp. Extracting it needs only `flang` on PATH: groundline runs
! flang on this file and reads the parse-tree dump directly.
module toy_kernel_mod
  implicit none
contains

  subroutine scale_clip_acc(a, b, s, lo)
    real, intent(in) :: a
    real, intent(inout) :: b
    real, intent(in) :: s, lo
    real :: w
    w = s * a
    if (w < lo) then
      b = b + lo
    else
      b = b + w
    end if
  end subroutine scale_clip_acc

end module toy_kernel_mod
