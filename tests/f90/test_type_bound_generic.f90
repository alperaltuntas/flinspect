! Test type-bound procedure calls, generic and specific (Phase 2 / DESIGN Q2).
!
! Sema resolves *static* type-bound dispatch in the unparse annotation by
! hoisting the object into the argument list and printing the specific:
!     call obj%go(1.0)      ->  'CALL go_r(obj,1._4)'
!     call obj%reset()      ->  'CALL reset_bounds(obj)'   (renamed binding)
! so the frontend classifies these edges as `resolved` — including the generic
! binding resolved by argument type, and a `=> renamed` binding whose
! implementation name differs from the binding name.
module tbp_mod
  implicit none
  type :: gadget_t
     integer :: state = 0
  contains
    procedure :: go_r
    procedure :: go_i
    generic :: go => go_r, go_i
    procedure :: reset => reset_state
  end type
contains
  subroutine go_r(self, x)
    class(gadget_t), intent(inout) :: self
    real, intent(in) :: x
  end subroutine
  subroutine go_i(self, k)
    class(gadget_t), intent(inout) :: self
    integer, intent(in) :: k
  end subroutine
  subroutine reset_state(self)
    class(gadget_t), intent(inout) :: self
  end subroutine
end module

module tbp_caller_mod
  use tbp_mod
  implicit none
contains
  subroutine test_type_bound_calls()
    type(gadget_t) :: obj
    call obj%go(1.0)
    call obj%go(2)
    call obj%reset()
  end subroutine
end module
