! Test a public generic whose specifics are PRIVATE (Phase 2 / DESIGN Q1+Q2).
!
! Because only the generic is accessible in the caller's scope, sema's unparse
! prints the resolved specific in flang's mangled, fully qualified form:
!     call compute(1.0)  ->  'CALL priv_mod$priv_mod$compute_r(1._4)'
! (imported-via module, defining module, specific). The frontend must demangle
! this to the entity `priv_mod::compute_r` and classify the edge as `resolved`.
! The fixture also exercises W4 visibility: `compute_r` is private, so a
! name-only lookup from the caller must NOT see it — only the demangled sema
! answer may reach it.
module priv_mod
  implicit none
  private
  public :: compute
  interface compute
    module procedure compute_r, compute_i
  end interface
contains
  subroutine compute_r(x)
    real, intent(in) :: x
  end subroutine
  subroutine compute_i(k)
    integer, intent(in) :: k
  end subroutine
end module

module priv_caller_mod
  use priv_mod, only: compute
  implicit none
contains
  subroutine test_private_calls()
    call compute(1.0)
    call compute(2)
  end subroutine
end module
