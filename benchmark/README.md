# NFE_Silverware binary benchmark

This framework treats the ArmClang-generated ARMv6-M binary as the performance source of truth. It does not infer an optimization merely from C/C++ source and it does not claim physical timing.

## Architecture

The workflow has three deliberately separated layers:

1. **Exact firmware build and binary evidence.** Keil µVision rebuilds `NFE_Silverware`; the workflow verifies the active `BWHOOP`, `RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND`, and `USE_MULTI` configuration, then saves the AXF, HEX, map, linker response/scatter files, exact compiler commands emitted in the µVision dependency file, tool versions, target headers, and FromELF disassembly.
2. **Linked ARMv6-M analysis.** FromELF symbols and instructions produce function sizes, derived stack frames, loads/stores, branches, BL edges, soft-float helper sites, conversions, call-graph files, expected loop invocations, and a clearly labeled **STATIC COST ESTIMATE**. The simple weights live in `cost_model.json`; they are relative units, never cycles or microseconds.
3. **Deterministic flight-math execution.** A small hardware-free entry point links the freshly built production `control.o`, `pid.o`, `filter.o`, `imu.o`, `angle_pid.o`, `stickvector.o`, `motorcurve.o`, and `util.o`. Unicorn executes that exact Cortex-M0 ELF for 2,048 deterministic iterations. MPU/RX inputs and PWM/time endpoints are replaced, but filters, IMU, control, PID, and mixer are not duplicated. Output floats and the executed instruction/helper trace are saved for regression comparison.

MPU6050 I2C and XN297 traffic are reported from `peripherals.json` as theoretical bus work and CPU polling behavior. They are never mixed with emulated CPU-math scores.

## Requirements

- Windows, Keil µVision/Arm Compiler 6 Community or STM32 edition (free), with `UV4.exe`, `armclang.exe`, `armlink.exe`, and `fromelf.exe`.
- Python 3.11 or later.
- The free Python packages pinned in `requirements.txt` (`unicorn` and `pyelftools`).

`benchmark.ps1` creates an ignored local virtual environment and installs those two packages automatically. It also recognizes the Python bundled with the Codex desktop app, so no system Python installation is required on this machine.

## Commands

From the repository root:

```powershell
.\benchmark.ps1 baseline
# make one small optimization patch
.\benchmark.ps1 candidate --compare baseline
```

With a normal Python environment whose requirements are already installed, the shorter equivalent is:

```powershell
python bench.py baseline
python bench.py candidate --compare baseline
python compare.py baseline candidate
```

Each build label is recreated under `benchmark/results/<label>/`. The directory contains:

- `firmware.axf`, `.hex`, `.map`, and `.disassembly.txt`
- `compiler_flags.json`, raw dependency flags, linker flags, build logs, project and target configuration snapshots
- `memory.json`, `function_metrics.csv`, `static_analysis.json`
- `callgraph.json`, `callgraph.dot`, `active_callgraph.md`, `active_functions.json`, `expected_loop_cost.json`
- `flight_math.axf`, map, disassembly, and static analysis
- `math_output.bin`, `math_output.json`, and `math_trace.json`
- `baseline_report.md`, plus `comparison_vs_<label>.md/.json` and normalized per-function `assembly_diff_vs_<label>.txt` after comparison

## Interpretation limits

- **STATIC COST ESTIMATE** is a deterministic relative score. It is useful for before/after ranking, not a cycle count.
- Emulator instruction counts are exact for the deterministic harness path but are not STM32 timing. There are no flash wait states, interrupts, DMA effects, bus contention, or peripherals.
- A derived stack frame is the largest visible `SUB sp, sp, #imm` plus saved registers in a conventional prologue. It is marked derivable because optimized code can use nonstandard or split adjustments.
- Static BL sites are not dynamic executions. The emulator trace and `flight_loop_model.json` report those concepts separately.
- The automatic verdict is conservative. An intentional change to PID/filter/control behavior must be reviewed as `ALGORITHM CHANGE`, even if its output error is small.

Renode and QEMU are not required. Neither is installed here, and full STM32F030 board emulation would add complexity without strengthening the CPU-side flight-math comparison.
