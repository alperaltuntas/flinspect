! Track B conformance fixture: the kernel-IR subset in miniature.
! A do-concurrent point kernel over inout arrays, exercising every construct
! the kernel frontend supports: assignment, if/elseif/else, do concurrent,
! literals, +,-,*,/,**, comparisons, abs, array refs at the loop indices,
! and a local scalar.

module kernel_dc_mod
  implicit none
contains

  subroutine clamp_scale(x_in, x_out, lo, n)
    integer,                intent(in)    :: n
    real, dimension(n),     intent(in)    :: x_in
    real, dimension(n),     intent(inout) :: x_out
    real,                   intent(in)    :: lo
    real :: w
    integer :: i

    do concurrent (i=1:n)
      w = 2.0*x_in(i) - x_out(i)
      if (abs(w) < lo) then
        x_out(i) = lo
      elseif (w**2 > 4.0*lo) then
        x_out(i) = x_in(i) + w/2.0
      else
        x_out(i) = (w + lo)*0.5
      endif
    enddo

  end subroutine clamp_scale

end module kernel_dc_mod
