! Test keyword argument matching.
! The 'transform' interface has two module procedures:
!   transform_scale(arr, scale, offset) - real, real, real
!   transform_index(arr, idx, count)    - real, integer, integer
! Calls using keyword arguments must match by name, not position.

module interface_keyword_mod
  implicit none

  interface transform
    module procedure transform_scale, transform_index
  end interface

contains

  subroutine transform_scale(arr, scale, offset)
    real, intent(inout) :: arr(:)
    real, intent(in) :: scale
    real, intent(in) :: offset
  end subroutine

  subroutine transform_index(arr, idx, count)
    real, intent(inout) :: arr(:)
    integer, intent(in) :: idx
    integer, intent(in) :: count
  end subroutine

end module

module caller_keyword_mod
  use interface_keyword_mod
  implicit none
contains

  subroutine test_keyword_calls()
    real :: data(100)

    ! Positional call - should resolve to transform_scale
    call transform(data, 2.0, 1.0)

    ! Positional call - should resolve to transform_index
    call transform(data, 5, 10)

    ! Keyword call (reordered) - should resolve to transform_scale
    call transform(data, offset=1.0, scale=2.0)

    ! Keyword call (reordered) - should resolve to transform_index
    call transform(data, count=10, idx=5)

  end subroutine

end module
