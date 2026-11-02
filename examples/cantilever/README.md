# Cantilever PCB verification

A self-contained 100 × 10 × 1.6 mm unpopulated rectangular PCB. The entire x=0
end face is fixed. The board is included here and has no component mass uncertainty.

```bash
./pcb-mechanical run examples/cantilever/case.json --backend cpu
./pcb-mechanical run examples/cantilever/case-cuda.json --backend cuda
./pcb-mechanical doctor --backend cpu --full
./pcb-mechanical doctor --backend cuda --full
```

The two case files write to separate `results/examples/cantilever/{cpu,cuda}`
directories. `doctor --full` also creates separate CPU/CUDA and coarse/fine results.

The Euler–Bernoulli first bending frequency is
`1.8751040687²/(2πL²) × t/√12 × √(E/ρ) = 91.5124 Hz` for the default material.
The analytical acceptance limit is 2%. Refinement compares 3 mm and 2 mm meshes.
The full PSD case uses synthetic 1 g RMS excitation separately in X/Y/Z, over
20–2000 Hz. It uses modal interference and static residual flexibility, and
includes the base term when reporting absolute acceleration.

Open `mesh/board.msh` in Gmsh, load `modal/mesh` as an ElmerGUI project, or open
`postprocess/modes.pvd`, `animation.pvd` and `rms.vtu` in ParaView using the root
README's GUI launch commands. `postprocess/open-view.py` creates a native ParaView
state and rendered RMS image when run with `pvpython`.
