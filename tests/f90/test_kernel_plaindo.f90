! Conformance fixture: a PLAIN, perfectly nested do nest as a point
! kernel (extraction rule A). Unlike do concurrent, a plain do asserts nothing
! about iteration independence — pointize admits it only because every array
! reference in the body is indexed exactly by the loop indices (the Python
! gate), and the Lean side carries the semantic license: the schema lemma
! foldSeq f enum = pointwise f (Groundline/SeqSchema.lean) proves the sequential
! fold of any such point body equals the pointwise map.

module kernel_plaindo_mod
  implicit none
contains

  subroutine scale_clip(a, b, s, n, m)
    integer,              intent(in)    :: n, m
    real, dimension(n,m), intent(in)    :: a
    real, dimension(n,m), intent(inout) :: b
    real,                 intent(in)    :: s
    real :: w
    integer :: i, j

    do j = 1, m
      do i = 1, n
        w = s*a(i,j)
        if (w > b(i,j)) then
          b(i,j) = w
        endif
      enddo
    enddo

  end subroutine scale_clip

end module kernel_plaindo_mod
