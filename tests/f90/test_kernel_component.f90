! Track B conformance fixture: derived-type component reads (extraction
! rule B). A loop-invariant scalar component (cfg%fac) and a component array
! indexed exactly by the loop indices (cfg%w(i)) become synthesized scalar
! in-parameters of the pointized kernel — named after the component, appended
! after the real parameters in first-use order. The second subroutine pins the
! naming-collision refusal: the synthesized name for cfg%fac collides with the
! dummy argument fac, and the extraction must refuse rather than rename.

module kernel_component_mod
  implicit none

  type :: cfg_t
    real :: fac
    real :: w(8)
  end type cfg_t

contains

  subroutine apply_cfg(cfg, a, b, n)
    type(cfg_t),        intent(in)    :: cfg
    integer,            intent(in)    :: n
    real, dimension(n), intent(in)    :: a
    real, dimension(n), intent(inout) :: b
    integer :: i

    do i = 1, n
      b(i) = cfg%fac*a(i) + cfg%w(i)
    enddo

  end subroutine apply_cfg

  subroutine collide(cfg, fac, b, n)
    type(cfg_t),        intent(in)    :: cfg
    integer,            intent(in)    :: n
    real,               intent(in)    :: fac
    real, dimension(n), intent(inout) :: b
    integer :: i

    do i = 1, n
      b(i) = cfg%fac*fac + b(i)
    enddo

  end subroutine collide

end module kernel_component_mod
