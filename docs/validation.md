# Validation evidence

Measured on 2026-11-02: Intel i7-9750H, 16 GB RAM, NVIDIA RTX 2060 (6 GB),
Elmer 26.1, CUDA 12.9.1, AMGX 2.5.0 and CuPy 13.6.0. Numerical stages ran
uncached with installed images. Image builds are excluded; other desktop work
was running, so these measurements are observations rather than an isolated
hardware benchmark.

## Standalone cantilever

| Backend | 3 mm modal + PSD + reporting | 2 mm modal + PSD + reporting | Largest eigenpair residual |
|---|---:|---:|---:|
| CPU / CHOLMOD | 31.35 s | 41.99 s | 1.25e-7 |
| CUDA / AMGX + CuPy | 199.43 s | 282.97 s | 8.86e-8 |

The analytical first bending frequency is 91.5124 Hz. Computed frequencies are
91.6934 Hz and 91.6786 Hz: errors of 0.198% and 0.182%, below the 2% target.
Mass orthogonality errors are below 5e-15. The largest PSD integration change is
0.0161%; the largest modal truncation change is 0.636%, below the 1% and 5%
limits respectively.

The identical-mesh CPU/CUDA comparison passed:

- Maximum relative frequency difference: 1.28e-9 (limit 0.001).
- Maximum relative RMS difference: 2.28e-7 (limit 0.01).
- Minimum mass-weighted mode-subspace overlap: 0.9999999999999989.

Both `doctor --backend cpu --full` and `doctor --backend cuda --full` passed.
The cantilever acceptance covers analytical/mesh frequency convergence, modal
accuracy and PSD/backend checks. Additional componentwise RMS mesh diagnostics
are retained; weak stress components near its neutral axis are mesh-sensitive.
The full RMS mesh gate remains mandatory for the board study below.

The AMGX bridge runs device-mode PCG solves, with reused setup, explicit
convergence-status checks and a refinement correction against the original
physical matrix. The initial multigrid configurations failed to converge and
were rejected. An initial PCG result with residual 1.55e-6 was also rejected;
the acceptance tolerance was not relaxed. Native logs record actual AMGX solves,
and the device-memory guard observed approximately 1.33–1.46 GiB total device
usage during example modal solves. CuPy formed the actual response covariances
and RMS fields on the RTX 2060, in float64/complex128, before backend comparison.

## Board-study acceptance

Board-specific input snapshots, case definitions, results and timing evidence
remain in ignored working directories. They are not included in the public
repository. A new study writes `report.md` and `study.json` under
`results/studies/<board-stem>/<backend>/` unless `--output` is supplied.

The board-study acceptance gates remain less than 2% change in the first ten frequencies,
less than 5% change in representative componentwise RMS responses, adequate
frequency/modal coverage, and an uncached end-to-end runtime under one hour per
backend. A study that finishes computation but fails mesh convergence reports
`unconverged` and exits nonzero; runtime alone never implies numerical acceptance.

## Workflow and GUI checks

- 27 unit tests pass, including explicit mounting validation, case-preserving
  studies, analytical SDOF response, coherent modal cross
  terms, damping dependence, g-to-SI conversion and absolute base acceleration.
- Missing GPU, nonconvergence, insufficient frequency coverage, deadlines,
  interruption and memory limits are tested. The resource test stops its own
  child while leaving an unrelated child alive.
- Actual extraction runs verified cache reuse and invalidation after changes to
  source/artifacts and simulated implementation/tool identities.
- Snapshot and GUI-copy tests verify source isolation. Simulation containers
  mount input snapshots read-only. Source checkouts and indexes receive no writes.
- The installed editable Python entry point and repository launcher were tested.
- Gmsh and ParaView were launched through the supplied GUI commands. ParaView
  rendered the actual RMS field and saved a PVSM state. ElmerGUI loaded the
  generated native mesh and authoritative `case.sif`; its project load reached
  `Ready` and the expected project title in an isolated virtual display.

The used images were built by extending exact installed thermal-lab image IDs;
the consumed source fingerprints and patches are retained in `env/locks/` and
inside each image. The standalone recipes do not import sibling Python code or
require a sibling checkout. The offline CPU/tools/CUDA export/import round trip passed identity and archive
hash checks. The 26 GiB temporary archive was removed after verification; rerun
`export` to create a transfer bundle. A completely fresh source build has not
been demonstrated in this session.

## Case-driven study check

The generic `study --case examples/cantilever/case.json --backend cpu` path
completed both meshes and all modal/PSD/report stages. It retained the physical
case settings and generated board-independent output paths and report titles.
Its strict componentwise RMS mesh check reports `unconverged`, consistent with
the weak-component mesh sensitivity noted above; the gate was not relaxed.
The study result is at `results/studies/board/cpu/study.json` when reproduced
with the included board filename.

## Local evidence and reproduction

Large input snapshots, native matrices, fields and logs remain ignored:

- `results/validation/{cpu,cuda}/doctor.json`
- `results/validation/backend-comparison.json`
- `results/validation/cache/checks.json`
- `results/studies/<board-stem>/<backend>/study.json` and `report.md`
- `results/studies/<board-stem>/<backend>/{coarse,fine}/postprocess/report.md`
- `results/gui/` and `results/examples/cantilever/cpu/postprocess/view.pvsm`

Use the commands in the root README to reproduce the studies. Successful stages
must show `completed`, rather than `cached`, for an uncached timing claim. GPU
allocation is bounded conservatively by device-wide usage, including the desktop;
only owned processes are stopped if a limit is reached. Board studies reserve five
minutes of a one-hour budget for interruption and cleanup.
