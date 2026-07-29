! Test optional arguments and argument count matching.
!
! The 'init' generic has two module procedures whose FIRST argument differs in
! type.  That is what makes them distinguishable to the compiler, which the
! with-sema dump requires: an ambiguous generic is a semantic error and flang
! then emits no dump at all.
!   init_simple(x, n)                real    first arg; 2 required args
!   init_advanced(k, n, tol, debug)  integer first arg; 2 required + 2 optional
!
! flinspect's (pre-Phase-2) heuristic resolver treats real and integer as
! mutually compatible, so a 2-argument call still fans out to both specifics;
! the 3-/4-argument and keyword calls exercise argument-count matching and
! keyword matching against the optional dummies.

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

  subroutine init_advanced(k, n, tol, debug)
    integer, intent(out) :: k
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
    integer :: idx

    ! 2 args, real first - resolves to init_simple
    call init(val, 10)

    ! 3 args - init_advanced (optional tol supplied); too many args for init_simple
    call init(idx, 10, 1.0e-6)

    ! 4 args - init_advanced (both optionals supplied)
    call init(idx, 10, 1.0e-6, .true.)

    ! keyword optional arg - init_advanced, matched by dummy name
    call init(idx, 10, debug=.true.)

  end subroutine

end module
