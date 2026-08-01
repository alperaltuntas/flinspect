! REFUSAL fixtures: integer VALUES in a modeled kernel body. Integer
! arithmetic truncates (2/3 is 0 in Fortran) and the model over ℝ does not,
! so admitting either shape would produce a plausible-but-wrong model — the
! printer refuses instead. Integers as ADDRESSES (loop indices, bounds,
! subscripts) are unaffected: pointize consumes and drops them.
! Faithful integer semantics is roadmap (manual: Limits page).
module test_kernel_intarith
  implicit none
contains

  ! Fortran evaluates 2/3 in integer arithmetic: b is unchanged. Over ℝ the
  ! printed expression would add two thirds of a. Refuses at print.
  subroutine int_div_literals(a, b)
    real(8), intent(in) :: a
    real(8), intent(inout) :: b
    b = b + a * (2/3)
  end subroutine int_div_literals

  ! An integer local read in the body: modeling it as a real would hide any
  ! truncation its assignments perform. Refuses at print.
  subroutine int_local(a, b)
    real(8), intent(in) :: a
    real(8), intent(inout) :: b
    integer :: k
    k = 2
    b = b + a * k
  end subroutine int_local

end module test_kernel_intarith
