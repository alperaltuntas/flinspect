! Test derived-type EXTENDS, same-module and cross-module (D7 gap closure).
!
! Three facts pinned here:
!   * a SAME-module extension (tagged_shape_t extends shape_t inside
!     shape_base_mod) must NOT put a self-loop in the module dependency graph —
!     the real-corpus case that motivated this fixture is MOM_io_file, whose
!     MOM_infra_file/MOM_netcdf_file extend MOM_file in the same module;
!   * a CROSS-module extension (circle_t extends shape_t) contributes the
!     module-dependency edge shape_ext_mod -> shape_base_mod;
!   * an INHERITED binding call: `describe` is bound on the parent type only.
!     With a non-polymorphic receiver (use_circle) sema resolves it statically;
!     with a polymorphic receiver (describe_any) dispatch is dynamic and the
!     frontend's EXTENDS ancestor walk supplies the declared-type impl as an
!     `assumed` edge.
module shape_base_mod
  implicit none
  type :: shape_t
     integer :: id = 0
  contains
    procedure :: describe => describe_shape
  end type

  ! same-module extension: no module self-loop may result
  type, extends(shape_t) :: tagged_shape_t
     integer :: tag = 0
  end type
contains
  subroutine describe_shape(self)
    class(shape_t), intent(in) :: self
  end subroutine
end module

module shape_ext_mod
  use shape_base_mod
  implicit none
  ! cross-module extension: shape_ext_mod depends on shape_base_mod
  type, extends(shape_t) :: circle_t
     real :: radius = 1.0
  end type
contains
  subroutine use_circle()
    type(circle_t) :: c
    call c%describe()      ! static dispatch: resolved via sema
  end subroutine
  subroutine describe_any(c)
    class(circle_t), intent(in) :: c
    call c%describe()      ! dynamic dispatch: assumed via the ancestor walk
  end subroutine
end module
