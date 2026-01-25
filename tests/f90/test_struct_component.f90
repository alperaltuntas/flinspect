! Test StructureComponent type inference.
! When a call argument is a derived-type component access like CS%field,
! flinspect should return unknown type (since component types are not resolved).
! This means the interface should fall back or match conservatively.

module struct_comp_mod
  implicit none

  type :: data_container
    real :: scalar_val
    real, allocatable :: array_1d(:)
    integer :: count
  end type

  type :: control_struct
    type(data_container) :: data
    integer :: mode
  end type

  interface update
    module procedure update_real, update_int
  end interface

contains

  subroutine update_real(val, n)
    real, intent(inout) :: val
    integer, intent(in) :: n
  end subroutine

  subroutine update_int(val, n)
    integer, intent(inout) :: val
    integer, intent(in) :: n
  end subroutine

end module

module caller_struct_mod
  use struct_comp_mod
  implicit none
contains

  subroutine test_struct_calls(CS)
    type(control_struct), intent(inout) :: CS

    ! CS%data%scalar_val is a StructureComponent - type unknown to flinspect
    ! Should fall back to all procedures
    call update(CS%data%scalar_val, 1)

    ! CS%mode is a StructureComponent - type unknown to flinspect
    call update(CS%mode, 2)

  end subroutine

end module
