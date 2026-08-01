! Conformance fixture: logical IF statements (R1139) and the sequential
! guarded join. The loop body ends with two guarded assignments to inout state;
! the second guard's RHS reads b(i), which the first IF may have just updated —
! functionalize must thread the merged (post-first-if) value of b, not its input.

module kernel_ifstmt_mod
  implicit none
contains

  subroutine guard_pair(a, b, c, n)
    integer,            intent(in)    :: n
    real, dimension(n), intent(in)    :: a
    real, dimension(n), intent(inout) :: b
    real, dimension(n), intent(inout) :: c
    real :: t
    integer :: i

    do concurrent (i=1:n)
      t = 2.0*a(i)
      if (t > b(i)) b(i) = t - 1.0
      if (t < c(i)) c(i) = b(i) + t
    enddo

  end subroutine guard_pair

end module kernel_ifstmt_mod
