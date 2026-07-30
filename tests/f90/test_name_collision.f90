! Test that identically-named routines in different modules stay distinct
! entities (W5, design principle #7: identity is scope-qualified, never a bare
! name).
!
! Three modules each define a subroutine `apply_bc` with the *same* signature, so
! the name is the only thing they share and a name-keyed consumer would silently
! merge all three into one node. The caller reaches each of them through a
! different USE form, which is also what makes the file legal Fortran (three
! wildcard USEs would make the bare name ambiguous):
!
!   * `collide_a_mod` — wildcard USE with a rename (`bc_a => apply_bc`); the
!     rename also *removes* access to the original name, so no ambiguity;
!   * `collide_b_mod` — only-list, bare name;
!   * `collide_c_mod` — only-list with a rename.
!
! That closes the "USE renames" gap in MANIFEST.md as a side effect: both rename
! forms (bare and only-list) had no fixture before.
module collide_a_mod
  implicit none
contains
  subroutine apply_bc(x)
    real, intent(inout) :: x
    x = x + 1.0
  end subroutine
end module

module collide_b_mod
  implicit none
contains
  subroutine apply_bc(x)
    real, intent(inout) :: x
    x = x + 2.0
  end subroutine
end module

module collide_c_mod
  implicit none
contains
  subroutine apply_bc(x)
    real, intent(inout) :: x
    x = x + 3.0
  end subroutine
end module

module collide_caller_mod
  use collide_a_mod, bc_a => apply_bc
  use collide_b_mod, only: apply_bc
  use collide_c_mod, only: bc_c => apply_bc
  implicit none
contains

  subroutine drive()
    real :: r
    r = 0.0
    call bc_a(r)       ! -> collide_a_mod::apply_bc
    call apply_bc(r)   ! -> collide_b_mod::apply_bc
    call bc_c(r)       ! -> collide_c_mod::apply_bc
  end subroutine

end module
