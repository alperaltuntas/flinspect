! Track B conformance fixture: unary minus (flang `Negate`). Covers the bare
! leaf form (-y), a compound operand needing printer parentheses (-2.0*x(i) —
! Fortran parses this as the negation of the whole term, R1008), and negation
! of a source-parenthesized expression (-(x + y)).

module kernel_negate_mod
  implicit none
contains

  subroutine neg_clip(x, y, n)
    integer,            intent(in)    :: n
    real, dimension(n), intent(in)    :: x
    real, dimension(n), intent(inout) :: y
    integer :: i

    do concurrent (i=1:n)
      if (x(i) < -y(i)) then
        y(i) = -2.0*x(i)
      else
        y(i) = -(x(i) + y(i))
      endif
    enddo

  end subroutine neg_clip

end module kernel_negate_mod
