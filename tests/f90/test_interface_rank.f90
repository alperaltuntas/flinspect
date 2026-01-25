! Test interface resolution by rank.
! The 'process' interface has three module procedures distinguished by rank:
!   process_1d(arr, n)  - real rank-1 array
!   process_2d(arr, n)  - real rank-2 array
!   process_3d(arr, n)  - real rank-3 array

module interface_rank_mod
  implicit none

  interface process
    module procedure process_1d, process_2d, process_3d
  end interface

contains

  subroutine process_1d(arr, n)
    real, intent(inout) :: arr(:)
    integer, intent(in) :: n
  end subroutine

  subroutine process_2d(arr, n)
    real, intent(inout) :: arr(:,:)
    integer, intent(in) :: n
  end subroutine

  subroutine process_3d(arr, n)
    real, intent(inout) :: arr(:,:,:)
    integer, intent(in) :: n
  end subroutine

end module

module caller_rank_mod
  use interface_rank_mod
  implicit none
contains

  subroutine test_rank_calls()
    real :: vec(10)
    real :: mat(5,5)
    real :: cube(3,3,3)

    ! Should resolve to process_1d
    call process(vec, 10)

    ! Should resolve to process_2d
    call process(mat, 5)

    ! Should resolve to process_3d
    call process(cube, 3)

  end subroutine

end module
