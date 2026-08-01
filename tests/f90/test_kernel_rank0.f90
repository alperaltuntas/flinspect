! Rank-0 (loop-free scalar) point kernel: already per-point as written, so
! it extracts with NO pointize license — and `pointize = true` on it refuses
! (the option is only meaningful on a loop nest). The loop/point boundary's
! fixture pair is this file vs the loop fixtures (test_kernel_doconcurrent,
! test_kernel_plaindo).
module test_kernel_rank0
  implicit none
contains

  subroutine clip_shift(x, y, lo)
    real(8), intent(in) :: x, lo
    real(8), intent(inout) :: y
    real(8) :: w
    w = 2.0 * x
    if (w < lo) then
      y = y + lo
    else
      y = y + w
    end if
  end subroutine clip_shift

end module test_kernel_rank0
