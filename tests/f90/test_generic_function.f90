! Test a generic FUNCTION reference used inside an expression.
!
! Every other fixture calls generics with CALL statements (subroutines); this one
! exercises the FunctionReference path: 'area' is a generic function resolved by
! the type of its single argument, and both references appear in one assignment.
module area_mod
  implicit none

  interface area
    module procedure area_r, area_i
  end interface

contains

  real function area_r(y)
    real, intent(in) :: y
    area_r = y * y
  end function

  real function area_i(k)
    integer, intent(in) :: k
    area_i = real(k * k)
  end function

end module

module caller_area_mod
  use area_mod
  implicit none
contains

  subroutine test_generic_function_calls()
    real :: a, y
    integer :: k

    y = 2.0
    k = 3

    a = area(y) + area(k)

  end subroutine

end module
