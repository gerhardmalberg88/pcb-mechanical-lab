! PCB Mechanical Lab, Copyright 2026 Gerhard Malberg, Apache-2.0.
! Uses Elmer's public DefUtils API; no upstream source incorporated here.
SUBROUTINE MechanicalExport(Model, Solver, dt, Transient)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Model_t) :: Model
  TYPE(Solver_t), TARGET :: Solver
  REAL(KIND=dp) :: dt
  LOGICAL :: Transient
  TYPE(Variable_t), POINTER :: V
  INTEGER :: u, n, k, p, d, j
  CHARACTER(LEN=12) :: names(3) = [CHARACTER(LEN=12) :: 'Displacement', 'Stress', 'Strain']
  CHARACTER(LEN=12) :: files(3) = [CHARACTER(LEN=12) :: 'modes.bin', 'stress.bin', 'strain.bin']
  DO j=1,3
    V => VariableGet(Model % Mesh % Variables, TRIM(names(j)))
    IF (.NOT. ASSOCIATED(V)) CYCLE
    IF (.NOT. ASSOCIATED(V % EigenVectors)) CYCLE
    k = SIZE(V % EigenVectors,1)
    n = SIZE(V % EigenVectors,2)
    p = SIZE(V % Perm)
    d = V % DOFs
    OPEN(NEWUNIT=u,FILE=TRIM(files(j)),ACCESS='stream',FORM='unformatted',STATUS='replace')
    WRITE(u) n,k,p,d
    WRITE(u) V % Perm
    WRITE(u) REAL(V % EigenValues,KIND=dp)
    WRITE(u) REAL(V % EigenVectors,KIND=dp)
    CLOSE(u)
  END DO
END SUBROUTINE

SUBROUTINE MechanicalReadModes(Solver)
  USE DefUtils
  IMPLICIT NONE
  TYPE(Solver_t), TARGET :: Solver
  INTEGER :: u,n,k,i
  REAL(KIND=dp), ALLOCATABLE :: values(:,:)
  OPEN(NEWUNIT=u,FILE='prescribed.bin',ACCESS='stream',FORM='unformatted',STATUS='old')
  READ(u) n,k
  IF(n /= SIZE(Solver % Variable % Values)) CALL Fatal('MechanicalReadModes','DOF count mismatch')
  ALLOCATE(values(k,n))
  READ(u) values
  CLOSE(u)
  IF (ASSOCIATED(Solver % Variable % EigenVectors)) DEALLOCATE(Solver % Variable % EigenVectors)
  IF (ASSOCIATED(Solver % Variable % EigenValues)) DEALLOCATE(Solver % Variable % EigenValues)
  ALLOCATE(Solver % Variable % EigenVectors(k,n),Solver % Variable % EigenValues(k))
  Solver % Variable % EigenVectors = CMPLX(values,0.0_dp,KIND=dp)
  Solver % Variable % EigenValues = [(CMPLX(REAL(i,dp),0.0_dp,KIND=dp),i=1,k)]
  Solver % NOFEigenValues = k
  DEALLOCATE(values)
END SUBROUTINE
