! Test calls whose targets are defined nowhere in the parsed set (D3:
! `unresolved`, first-class).
!
! `ext_sub` / `ext_fun` are declared EXTERNAL, so sema accepts the calls but its
! unparse simply echoes the names: the frontend must classify both edges as
! `unresolved` and intern the targets as defined=False entities (a subroutine
! and a function respectively). The `helper_sub` call goes through an explicit
! only-list to a module defined in this same file, so it stays `resolved` —
! pinning that an unresolved neighbor doesn't degrade the resolvable edges.
!
! (A *scope-qualified* unresolved target — the only-list pointing at a module
! outside the parsed set — cannot be fixtured self-contained, since sema needs
! the .mod to accept the USE; that path is unit-tested against a hand-built
! registry in tests/frontend/test_flang_dump.py.)
module ext_provider_mod
  implicit none
contains
  subroutine helper_sub(x)
    real, intent(inout) :: x
  end subroutine
end module

module ext_caller_mod
  use ext_provider_mod, only: helper_sub
  implicit none
contains
  subroutine test_external_calls()
    external :: ext_sub
    real, external :: ext_fun
    real :: r
    r = 1.0
    call ext_sub(r)
    r = ext_fun(r)
    call helper_sub(r)
  end subroutine
end module
