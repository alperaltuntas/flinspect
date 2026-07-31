! Track B conformance fixture: inline-loop addressing (extraction rule B).
! Two loop nests in one subroutine — nest #1 a do concurrent inside the THEN
! branch, nest #2 a plain do inside the ELSE branch — each extracted on its own
! by source-order ordinal (the flang dump carries no line numbers, so ordinals
! are the deterministic address; both do-concurrent and plain-DO nests count).
! The subroutine as a whole is NOT a kernel: its body is an IfConstruct, which
! the unchanged whole-subroutine mode keeps refusing.

module kernel_inline_mod
  implicit none
contains

  subroutine two_nests(a, b, c, q, n)
    integer,            intent(in)  :: n
    real,               intent(in)  :: q
    real, dimension(n), intent(in)  :: a
    real, dimension(n), intent(out) :: b
    real, dimension(n), intent(out) :: c
    integer :: i

    if (q > 0.0) then
      do concurrent (i=1:n)
        b(i) = q*a(i)
      enddo
    else
      do i = 1, n
        c(i) = a(i) - q
      enddo
    endif

  end subroutine two_nests

end module kernel_inline_mod
