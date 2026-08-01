! The quickstart kernel, Fortran side: scale a by s, clip to lo from below,
! accumulate into b.
!
! `scale_clip_acc` computes one grid point — the same shape as its C++ twin
! in toy_kernel.cpp. `scale_clip_acc_loop` applies the same update over a
! whole column, the way the kernel would appear inside a real model loop.
!
! The committed flang dump next to this file (toy_kernel_ptree, see
! PROVENANCE) covers both subroutines. To regenerate it:
!     flang -fc1 -fdebug-dump-parse-tree toy_kernel.f90 > toy_kernel_ptree
module toy_kernel_mod
  implicit none
contains

  ! One grid point.
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

  ! The same update, as a loop over a column.
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

end module toy_kernel_mod
