#!/usr/bin/env python3
"""Version-checked real serial ARPACK/AMGX dispatch and setup reuse.
Modified Elmer sources retain their original upstream license notices.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]);p=root/'fem/src/EigenSolve.F90';s=p.read_text()
start=s.index('     SUBROUTINE ArpackEigenSolve(');end=s.index('     END SUBROUTINE ArpackEigenSolve',start)
a=s[start:end]
needle="      CHARACTER(*), PARAMETER :: Caller = 'EigenSolve'"
assert a.count(needle)==1
interface='''
      INTERFACE
        SUBROUTINE MechanicalAMGX(A,x,b,Solver)
          USE Types
          TYPE(Matrix_t), POINTER :: A
          TYPE(Solver_t), TARGET :: Solver
          REAL(KIND=dp) :: x(:),b(:)
        END SUBROUTINE
      END INTERFACE
'''
a=a.replace(needle,needle+interface)
needle="              CASE ('direct')\n                CALL DirectSolver( A, x, b, Solver )"
assert a.count(needle)==1
a=a.replace(needle,"              CASE('amgx')\n                x = 0.0_dp\n                CALL MechanicalAMGX(A,x,b,Solver)\n"+needle)
p.write_text(s[:start]+a+s[end:])
p=root/'fem/src/SolverUtils.F90';s=p.read_text()
s+='''
! PCB Mechanical Lab bridge; this derived source retains Elmer's license.
SUBROUTINE MechanicalAMGX(A,x,b,Solver)
  USE SolverUtils, ONLY: AMGXSolver
  USE Lists, ONLY: ListAddLogical
  USE Types
  IMPLICIT NONE
  TYPE(Matrix_t), POINTER :: A
  TYPE(Solver_t), TARGET :: Solver
  REAL(KIND=dp) :: x(:),b(:)
  INTEGER, PARAMETER :: accurate=SELECTED_REAL_KIND(18)
  REAL(KIND=accurate) :: accumulated
  REAL(KIND=dp), ALLOCATABLE :: values(:),rhs(:),diagonal(:),result(:),correction(:),residual(:)
  INTEGER :: i,j,n
  ! ArpackEigenSolve bypasses SolveLinearSystem's normal diagonal scaling.
  ! Scale only the inner solve: (D K D)y = D b; x = D y.
  ! Restore K and b before ARPACK next uses the physical operators.
  n = A % NumberOfRows
  ALLOCATE(values(SIZE(A % Values)),rhs(n),diagonal(n),result(n),correction(n),residual(n))
  values = A % Values
  rhs = b
  DO i=1,n
    diagonal(i) = 1.0_dp / SQRT(ABS(values(A % Diag(i))))
  END DO
  DO i=1,n
    DO j=A % Rows(i),A % Rows(i+1)-1
      A % Values(j) = values(j)*diagonal(i)*diagonal(A % Cols(j))
    END DO
  END DO
  b = rhs*diagonal
  x = 0.0_dp
  CALL AMGXSolver(A,x,b,Solver)
  result = x*diagonal
  ! One iterative-refinement correction uses the ORIGINAL physical operator.
  ! Extended precision is used only to accumulate the cancellation-prone residual;
  ! matrices, GPU solves, eigenvectors and PSD data remain double precision.
  DO i=1,n
    accumulated = REAL(rhs(i),KIND=accurate)
    DO j=A % Rows(i),A % Rows(i+1)-1
      accumulated = accumulated - REAL(values(j),KIND=accurate) * &
        REAL(result(A % Cols(j)),KIND=accurate)
    END DO
    residual(i) = REAL(accumulated,KIND=dp)*diagonal(i)
  END DO
  correction = 0.0_dp
  IF (SUM(ABS(residual))>TINY(1.0_dp)) THEN
    CALL ListAddLogical(Solver % Values,'Linear System Refactorize',.FALSE.)
    CALL AMGXSolver(A,correction,residual,Solver)
    result = result + correction*diagonal
  END IF
  x = result
  b = rhs
  A % Values = values
  DEALLOCATE(values,rhs,diagonal,result,correction,residual)
END SUBROUTINE
'''
p.write_text(s)
p=root/'fem/src/amgx.c';s=p.read_text();start=s.index('void AMGXSolve(',s.index('*/',s.index('void AMGXSolve('))+2)
a=s[start:]
needle='    ptr = (ElmerAMGX *)*a_in;';assert a.count(needle)==1
a=a.replace(needle,needle+'\n    int needs_setup = !ptr || *nonlin_update;')
needle='AMGX_solver_setup(ptr->solver, ptr->A)'
assert a.count(needle)==2
# Existing CUDA patch wraps API calls in AMGX_SAFE_CALL.
a=a.replace('AMGX_SAFE_CALL('+needle+');','if (needs_setup) AMGX_SAFE_CALL('+needle+');')
p.write_text(s[:start]+a)
print('Patched real serial ARPACK dispatch to AMGX and retained matrix setup')
