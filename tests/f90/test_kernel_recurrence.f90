! Track B REFUSAL fixture (extraction rule A): a cross-iteration recurrence,
! distilled from find_dz_for_eta's hydrostatic pressure accumulation
! (MOM6/src/core/MOM_interface_heights.F90):
!
!     p(i,j,K+1) = p(i,j,K) + GV%g_Earth*GV%H_to_RZ*h(i,j,k)
!
! Iteration k+1 reads what iteration k wrote — the loop is NOT point-local and
! must never pointize: the K+1 subscript fails the "indexed exactly by the
! loop indices" gate. The capital-K spelling is deliberate: Fortran is
! case-insensitive and the dump lowercases every name, so K and k are the SAME
! index — the refusal must fire on the +1 OFFSET, not on a spurious
! case-sensitive name mismatch.

module kernel_recurrence_mod
  implicit none
contains

  subroutine accumulate(p, h, g, n, nz)
    integer,                 intent(in)    :: n, nz
    real, dimension(n,nz),   intent(in)    :: h
    real, dimension(n,nz+1), intent(inout) :: p
    real,                    intent(in)    :: g
    integer :: i, k

    do k = 1, nz
      do i = 1, n
        p(i,K+1) = p(i,K) + g*h(i,k)
      enddo
    enddo

  end subroutine accumulate

end module kernel_recurrence_mod
