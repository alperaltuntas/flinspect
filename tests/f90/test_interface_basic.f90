! Test basic interface resolution by type and rank.
! The 'compute' interface has three module procedures distinguished by type:
!   compute_real(x_real, n)       - real scalar + integer
!   compute_int(x_int, n)         - integer scalar + integer
!   compute_logical(x_log, flag)  - logical + logical

module interface_basic_mod
  implicit none

  interface compute
    module procedure compute_real, compute_int, compute_logical
  end interface

contains

  subroutine compute_real(x, n)
    real, intent(inout) :: x
    integer, intent(in) :: n
  end subroutine

  subroutine compute_int(x, n)
    integer, intent(inout) :: x
    integer, intent(in) :: n
  end subroutine

  subroutine compute_logical(x, flag)
    logical, intent(inout) :: x
    logical, intent(in) :: flag
  end subroutine

end module

module caller_basic_mod
  use interface_basic_mod
  implicit none
contains

  subroutine test_calls()
    real :: r
    integer :: i
    logical :: flag

    ! Should resolve to compute_real
    call compute(r, 1)

    ! Should resolve to compute_int
    call compute(i, 2)

    ! Should resolve to compute_logical
    call compute(flag, .true.)

  end subroutine

end module
