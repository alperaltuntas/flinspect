! Test array element access via FunctionReference pattern.
! When flang -no-sema parses an undeclared name with subscripts like fields(i),
! it generates FunctionReference -> Call -> ProcedureDesignator -> Name = 'fields'
! rather than ArrayElement, since it can't determine if it's an array or function.
!
! flinspect must detect this pattern and look up the variable type from 'fields'
! (if declared) rather than treating it as a function call.

module func_ref_mod
  implicit none

  interface send_data
    module procedure send_data_2d, send_data_3d
  end interface

contains

  subroutine send_data_2d(field, time)
    real, intent(in) :: field(:,:)
    integer, intent(in) :: time
  end subroutine

  subroutine send_data_3d(field, time)
    real, intent(in) :: field(:,:,:)
    integer, intent(in) :: time
  end subroutine

end module

module caller_func_ref_mod
  use func_ref_mod
  implicit none
contains

  subroutine test_func_ref_calls(fields, nfields)
    real, intent(in) :: fields(:,:,:)
    integer, intent(in) :: nfields
    integer :: i

    ! Direct 3d array - should resolve to send_data_3d
    call send_data(fields, 2)

    ! fields(i,:,:) - ArrayElement subscripting reduces rank by 1 (rank 3 -> rank 2)
    ! Should resolve to send_data_2d
    call send_data(fields(i,:,:), 1)

  end subroutine

end module
