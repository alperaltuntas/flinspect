! Quickstart toy kernel — a `do concurrent` point kernel inside the supported
! kernel subset. Its with-sema flang dump (toy_kernel_ptree) is COMMITTED
! next to this file (see PROVENANCE), so the Fortran side of the quickstart
! works with a plain `pip install` — no flang needed. Regenerate the dump with
!     flang -fc1 -fdebug-dump-parse-tree toy_kernel.f90 > toy_kernel_ptree
module toy_kernel_mod
  implicit none
contains

  ! Scale a by s, clip to lo from below, accumulate into b.
  subroutine scale_clip_acc(a, b, s, lo, n)
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
  end subroutine scale_clip_acc

end module toy_kernel_mod
