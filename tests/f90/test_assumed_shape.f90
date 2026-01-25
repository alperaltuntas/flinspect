! Test AssumedShapeSpec with explicit lower bounds.
! Fortran allows: real, dimension(lo:, lo:) which creates an assumed-shape array
! with explicit lower bounds. flang represents this as AssumedShapeSpec with a
! SpecificationExpr. flinspect must count these correctly to determine rank.

module assumed_shape_mod
  implicit none

  type :: index_type
    integer :: isd, jsd
  end type

  interface fill_data
    module procedure fill_data_1d, fill_data_2d, fill_data_3d
  end interface

contains

  subroutine fill_data_1d(arr, val)
    real, intent(out) :: arr(:)
    real, intent(in) :: val
  end subroutine

  subroutine fill_data_2d(arr, val)
    real, intent(out) :: arr(:,:)
    real, intent(in) :: val
  end subroutine

  subroutine fill_data_3d(arr, val)
    real, intent(out) :: arr(:,:,:)
    real, intent(in) :: val
  end subroutine

end module

module caller_assumed_mod
  use assumed_shape_mod
  implicit none
contains

  subroutine test_assumed_calls(HI, data2d, data1d)
    type(index_type), intent(in) :: HI
    real, dimension(HI%isd:,HI%jsd:), intent(inout) :: data2d
    real, dimension(HI%isd:), intent(inout) :: data1d

    ! data1d has rank 1 (assumed shape with explicit lower bound)
    ! Should resolve to fill_data_1d
    call fill_data(data1d, 0.0)

    ! data2d has rank 2 (assumed shape with explicit lower bounds)
    ! Should resolve to fill_data_2d
    call fill_data(data2d, 1.0)

  end subroutine

end module
