! The quickstart kernel written as a loop over a column — the way it would
! appear inside a real model. Used by the quickstart's closing section: a
! loop is not a point function, so pairing this with the C++ port takes an
! explicit `pointize = true` license on its manifest entry.
module toy_kernel_loop_mod
  implicit none
contains

  subroutine scale_clip_acc_loop(a, b, s, lo, n)
    integer, intent(in) :: n
    real, intent(in) :: a(n)
    real, intent(inout) :: b(n)
    real, intent(in) :: s, lo
    real :: w
    integer :: i
    do concurrent (i = 1:n)
      w = s * a(i)
      if (w < lo) then
        b(i) = b(i) + lo
      else
        b(i) = b(i) + w
      end if
    end do
  end subroutine scale_clip_acc_loop

end module toy_kernel_loop_mod
