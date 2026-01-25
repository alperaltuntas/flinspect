! Test optional arguments and argument count matching.
! The 'init' interface has two module procedures:
!   init_simple(x, n)                - 2 required args
!   init_advanced(x, n, tol, debug)  - 2 required + 2 optional args
! Calls with only required args should match both on type alone,
! but calls with 3 or 4 args should match only init_advanced.

module optional_args_mod
  implicit none

  interface init
    module procedure init_simple, init_advanced
  end interface

contains

  subroutine init_simple(x, n)
    real, intent(out) :: x
    integer, intent(in) :: n
  end subroutine

  subroutine init_advanced(x, n, tol, debug)
    real, intent(out) :: x
    integer, intent(in) :: n
    real, optional, intent(in) :: tol
    logical, optional, intent(in) :: debug
  end subroutine

end module

module caller_optional_mod
  use optional_args_mod
  implicit none
contains

  subroutine test_optional_calls()
    real :: val

    ! 2 args - matches both init_simple and init_advanced
    call init(val, 10)

    ! 3 args - only matches init_advanced
    call init(val, 10, 1.0e-6)

    ! 4 args - only matches init_advanced
    call init(val, 10, 1.0e-6, .true.)

    ! keyword optional arg - only matches init_advanced
    call init(val, 10, debug=.true.)

  end subroutine

end module
