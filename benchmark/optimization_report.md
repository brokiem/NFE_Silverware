# Rajawali/BWHOOP implementation optimization report

This report compares the linked ArmClang 6.24 Cortex-M0 firmware before source-level optimization (`o2_fastmath_actual`) with the final clean rebuild (`baseline`). Both use the exact `NFE_Silverware` Keil target, `-O2 -ffast-math`, function sections, and no LTO.

All execution scores and instruction totals are **STATIC PERFORMANCE ESTIMATE** results from deterministic emulation of the linked flight-math ELF. They are not cycles or physical time. Peripheral waits, interrupts, Flash wait states, and real bus contention are excluded.

## Aggregate result

| Metric | O2/fast-math source baseline | Final | Delta |
|---|---:|---:|---:|
| Firmware ROM | 22,424 B | 22,180 B | -244 B |
| Static RAM | 2,240 B | 2,240 B | 0 B |
| Executed ARM instruction trace, 2,048 iterations | 50,735,548 | 49,161,140 | -1,574,408 (-3.10%) |
| STATIC PERFORMANCE ESTIMATE | 63,497,169 | 61,601,630 | -1,895,539 (-2.99%) |
| Observed harness stack depth | 252 B | 260 B | +8 B |
| Non-finite outputs | 0 | 0 | 0 |

The final linker load region is bounded at `0x08007C00`; persistent storage remains `0x08007C00`–`0x08007FFF`. Total ROM leaves 9,564 bytes inside the 31,744-byte firmware region. The link fails if firmware crosses the storage boundary.

There is a hardware-configuration conflict that must be resolved before flashing: the compiler defines `STM32F030x6` and the scatter file allows 31,744 firmware bytes, but the µVision device is `STM32F030F4` with 16,384 bytes declared IROM. The 22,180-byte image exceeds that declaration by 5,796 bytes. Verify the physical MCU marking/Flash capacity and select the matching Keil device without weakening the `0x08007C00` reservation.

## Active flight-loop call graph

The linked and source-ordered steady loop is:

```text
main
├─ sixaxis_read ×1
│  ├─ i2c_readdata → hw_i2c_readdata → hw_i2c_sendheader
│  ├─ lpffilter ×3
│  └─ lpffilter2 ×3
├─ control ×1
│  ├─ pid_precalc ×1
│  ├─ stick_vector / apid (mode-dependent)
│  ├─ rotateErrors ×1
│  ├─ pid ×3 → splpf / lpf2 (configured branches)
│  └─ pwm_set ×4
├─ imu_calc ×1
│  ├─ lpfcalc_hz ×1 on the executed ground/in-air branch
│  ├─ lpf ×3
│  ├─ Q_rsqrt work (valid-acceleration, branch-dependent)
│  └─ atan2approx ×2 in Horizon mode
├─ adc_read ×2 and battery filters
└─ checkrx ×1 → XN297/Bayang software-SPI work (packet-dependent)
```

`motormap` is no longer linked when `MOTOR_CURVE_NONE` is selected. The complete direct-BL graph and dynamic edge counts are generated at `benchmark/results/baseline/active_callgraph.md`.

## Runtime-helper comparison

These totals use the same linked deterministic harness before and after. The harness substitutes motor capture for physical PWM; the production `pwm_set` assembly separately contains one `__aeabi_fmul` and one `__aeabi_f2iz` per motor call (four each per flight loop), unchanged by these patches.

| Runtime helper | Before | After | Delta |
|---|---:|---:|---:|
| `__aeabi_fadd` | 232,594 | 232,594 | 0 |
| `__aeabi_fsub` | 119,083 | 106,795 | -12,288 |
| `__aeabi_fmul` | 387,951 | 375,151 | -12,800 |
| `__aeabi_fdiv` | 14,859 | 14,859 | 0 |
| `__aeabi_fcmpgt` | 52,736 | 51,712 | -1,024 |
| `__aeabi_i2f` | 18,432 | 18,432 | 0 |
| `__aeabi_ui2f` | 4,096 | 4,096 | 0 |
| linked `__aeabi_d*` | 0 | 0 | 0 |
| all `__aeabi_f*` calls | 963,432 | 937,320 | -26,112 |

The 14,859 remaining float divisions are dominated by the unchanged algorithms: Kalman pass 1/pass 2 account for 12,288 calls (six per loop), `atan2approx` for 1,024, `stick_vector` for 1,533, and guarded PID/profile precalculation for 14 total calls in this corpus.

## Numerical regression

The corpus contains 2,048 iterations × 17 outputs/states = 34,816 floats covering rate, level, race, Horizon, and both PID profiles.

| Check | Result |
|---|---:|
| Maximum absolute error | 1.1324882507324219e-6 |
| Maximum relative error | 8.488964346349745e-4 |
| Maximum ULP difference | 8,192 |
| Bitwise mismatches | 12,277 |
| Non-finite mismatches | 0 |

The maximum absolute error is `motor_fl` at iteration 1907: baseline `0.5907411575317383`, final `0.590742290019989`. Its deterministic input is:

```text
mode=Horizon, PID profile=1
rx=[-0.1401275694, -0.3347809017, 0.3405365050, 0.6690661907]
gyro_sample=[-0.6898443699, -1.5970442295, 1.7011932135]
accel_sample=[-44.66020584, -147.80508423, 2048.74584961]
```

The maximum relative/ULP values occur close to zero: relative error on `gyro_yaw` around `1.404e-4`, and ULP error on `gyro_roll` around `-4.705e-4`. Setpoints are bit-identical. Maximum absolute errors are 1.133e-6 for motors, 7.153e-7 for PID outputs, 4.769e-7 for filtered gyro, and 1.789e-7 for the gravity vector.

## Retained patches

### 1. Kalman covariance identity

Finding: Both active Kalman passes evaluated `(1.0f - K) * P_temp` after `K = P_temp / (P_temp + R)`.

Why it matters: Six filter steps execute per flight loop on this target.

Before assembly/codegen: Each `lpffilter` body was 104 B/44 instructions with an additional `BL __aeabi_fsub`, a 32-byte derived frame, and 49,152 helper calls per function in the corpus.

Expected dynamic frequency: Three axes × two passes = six per loop.

Why armclang did not optimize it: Replacing the covariance expression with `R * K` is an algebraic identity across a prior division, but it changes IEEE-754 rounding; armclang did not perform that transformation.

Patch: Store covariance as `R * K`; the Kalman gain, state estimate, Q/R values, and recurrence are otherwise unchanged.

After assembly/codegen: Each filter is 96 B/41 instructions, uses a 24-byte derived frame, and has no covariance subtraction helper.

ROM/RAM: -12 B ROM, 0 B static RAM.

Hot-helper delta: `__aeabi_fsub` -12,288 across 2,048 iterations.

Numerical regression: Maximum absolute error 1.371e-6 for the isolated patch; maximum PID error 7.153e-7 and motor error 1.371e-6.

Risk: Float-rounding change accumulates in filter state; hardware noise/flight validation is still required.

Verdict: **MERGE**.

### 2. Shared Horizon angle fade

Finding: Standard Horizon mode recomputed the identical roll/pitch inclination maximum and angle fade inside both iterations of the axis loop.

Why it matters: The values cannot change during those two iterations; `apid()` prevented armclang from safely hoisting them.

Before assembly/codegen: `control` was 3,040 B/1,187 instructions.

Expected dynamic frequency: Duplicate work once per standard-Horizon flight loop; the corpus exercised 512 such iterations.

Patch: Compute only the shared inclination maximum and angle fade before the two-axis loop. Stick fade and per-axis PID work remain inside.

After assembly/codegen: `control` became 2,952 B/1,161 instructions for this patch.

ROM/RAM: -116 B ROM, 0 B RAM.

Hot-helper delta: `__aeabi_fcmpgt` -1,024 and `__aeabi_fmul` -512 in the corpus.

Numerical regression: Bit-identical, maximum ULP 0.

Risk: Limited to standard Horizon branch; no formula change.

Verdict: **MERGE**.

### 3. Automatic I2C byte index

Finding: `hw_i2c_readdata` used a persistent `static uint8_t` index. The linked byte loop loaded and stored that RAM object for every received byte.

Why it matters: Fourteen bytes are read on every MPU6050 burst, and persistent state made the routine non-reentrant.

Before assembly/codegen: 124 B/58 instructions, 8 loads, 8 stores, 32-byte frame.

Expected dynamic frequency: One initialization plus 14 index updates per flight loop.

Patch: Use an automatic `int` loop index.

After assembly/codegen: 104 B/48 instructions, 5 loads, 6 stores, same frame.

ROM/RAM: -48 B ROM; total image RAM unchanged because alignment absorbed the removed byte.

Hot-helper delta: None; this is native load/store/loop work outside the math harness.

Numerical regression: Flight math bit-identical; I2C transactions unchanged.

Risk: Hardware polling frequency is not emulated.

Verdict: **MERGE**.

### 4. Direct RXDR read

Finding: Every byte called the separately linked three-instruction `I2C_ReceiveData` wrapper.

Before assembly/codegen: Caller setup + `BL`; callee `LDR RXDR`, `UXTB`, `BX LR`.

Expected dynamic frequency: 14 calls per MPU burst/flight loop.

Patch: Read the volatile `I2C1->RXDR` register in the hardware driver.

After assembly/codegen: In-place `LDR`/`UXTB`; wrapper stripped.

ROM/RAM: -8 B ROM, 0 B RAM.

Hot-helper delta: None; static estimate is 28 fewer executed native instructions per 14-byte burst.

Numerical regression: Bit-identical.

Risk: Peripheral wait time is unchanged.

Verdict: **MERGE**.

### 5. Byte-accurate I2C buffers

Finding: The MPU byte API used `int *`, forcing word stores and a 64-byte local array in `sixaxis_read`.

Before assembly/codegen: `hw_i2c_readdata` scaled the byte index by four and used `STR`; `sixaxis_read` had a 96-byte derived frame.

Expected dynamic frequency: 14 driver stores and one sensor stack allocation per loop.

Patch: Use `uint8_t *` consistently in hardware/software I2C and `uint8_t` arrays in all sensor callers.

After assembly/codegen: Direct `STRB`, no index scaling/receive `UXTB`; `sixaxis_read` frame is 56 bytes. Cold `gyro_cal` falls from 112 to 96 bytes.

ROM/RAM: -4 B ROM, 0 B static RAM; active stack -40 B.

Hot-helper delta: None; two fewer native driver-loop instructions per byte.

Numerical regression: Decoding operations are equivalent in linked assembly; production-math corpus bit-identical.

Risk: Software-I2C is compile-checked but stripped from this hardware-I2C target.

Verdict: **MERGE**.

### 6. Compile-time identity motor map

Finding: `MOTOR_CURVE_NONE` linked a two-byte identity function and `control` called it four times per armed loop.

Before assembly/codegen: Four `BL motormap` sites plus four `BX LR` executions.

Expected dynamic frequency: Four per loop.

Patch: Select the input directly at compile time only for `MOTOR_CURVE_NONE`; configured nonlinear curves retain the existing call.

After assembly/codegen: Four call sites and the function are stripped.

ROM/RAM: -20 B ROM, 0 B RAM.

Hot-helper delta: None; -16,384 traced instructions and -32,768 static-cost units across the corpus.

Numerical regression: Bit-identical.

Risk: Conditional compilation must remain synchronized with the motor-curve selection.

Verdict: **MERGE**.

### 7. Factored proportional gain

Finding: The brushed setpoint-weighted P term multiplied `pidkp[x]` independently into both components.

Before assembly/codegen: Four active soft-float multiplies in the P expression; `pid` was 856 B/377 instructions.

Expected dynamic frequency: Once for each of three axes per loop.

Patch: Factor the common proportional gain after the weighted error/gyro difference.

After assembly/codegen: One fewer multiply site; `pid` became 848 B/374 instructions with the same 64-byte frame.

ROM/RAM: -8 B ROM, 0 B RAM.

Hot-helper delta: `__aeabi_fmul` -6,144; -375,609 traced instructions and -437,231 static-cost units.

Numerical regression: Maximum PID/motor absolute error 4.769e-7/4.470e-7 for this isolated patch.

Risk: Algebraically identical but reassociated float rounding.

Verdict: **MERGE**.

### 8. Factored derivative gain

Finding: The advanced D term applied the shared `pidkd[x] * timefactor` gain separately to setpoint and gyro derivative components.

Before assembly/codegen: `pid` was 848 B/374 instructions.

Expected dynamic frequency: Once for each of three axes per loop.

Patch: Form the weighted derivative difference and apply the common gain once. D filtering and state updates are unchanged.

After assembly/codegen: 832 B/367 instructions and one fewer soft-float multiply site. Armclang had already reassociated part of the original expression, so measured savings are one helper per axis rather than the two suggested by raw source. The derived `pid` frame increases from 64 to 72 bytes with one additional store.

ROM/RAM: -16 B ROM, 0 B static RAM; observed harness stack +8 B.

Hot-helper delta: `__aeabi_fmul` -6,144; -249,230 traced instructions and -284,535 static-cost units.

Numerical regression: Maximum PID/motor absolute error 3.576e-7/3.949e-7 for this isolated patch.

Risk: Reassociated float rounding and +8 B worst observed stack. Final static RAM plus observed harness stack still leaves 1,596 B between those measured regions, but cold/interrupt stack usage is not covered.

Verdict: **MERGE**.

### 9. Direct TXDR write

Finding: The hot register header called the two-instruction `I2C_SendData` wrapper.

Before assembly/codegen: Argument setup + `BL`; callee `STR TXDR`, `BX LR`.

Expected dynamic frequency: Once per MPU burst; additional calls occur only during configuration writes.

Patch: Write volatile `I2C1->TXDR` in the hardware driver.

After assembly/codegen: In-place `UXTB`/`STR`; wrapper stripped. `hw_i2c_sendheader` loses one instruction/call.

ROM/RAM: -12 B ROM, 0 B RAM.

Hot-helper delta: None; static estimate is three fewer native instructions per sensor burst.

Numerical regression: Bit-identical.

Risk: Bus timing and transaction order unchanged.

Verdict: **MERGE**.

## Rejected/reverted patches

### PID scalar locals

Finding: Three one-element local arrays in `pid` looked unnecessary in C.

Machine-code result: Replacing them with scalars increased firmware ROM by 4 B, added two static instructions to `pid`, added 150,501 traced instructions and 165,968 static-cost units, with unchanged 64-byte stack and bit-identical outputs.

Why armclang: The original indexed layout produced better register allocation/code scheduling for this function.

Verdict: **REJECT**, reverted before commit.

### Direct I2C status polling

Finding: `I2C_GetFlagStatus` is a five-instruction wrapper called from each polling loop.

Machine-code result: Direct ISR masks exposed the fixed 8,192-iteration timeouts to O2. Armclang unrolled them heavily: `hw_i2c_readdata` grew from 48 to 254 instructions/104 to 516 B, `hw_i2c_writereg` grew from 26 to 228 instructions, and firmware ROM increased 636 B.

Why armclang: The external call had inhibited timeout-loop unrolling; removing it changed the optimizer's cost model.

Numerical regression: Bit-identical, but peripheral dynamic timing is unavailable.

Verdict: **REJECT**, reverted before commit.

### Algorithm substitutions and global optimizer changes

Kalman→PT1, alternate `atan2approx`, PID/mixer/rate changes, fixed-point conversion, scheduler redesign, DMA I2C, O3, and LTO were not introduced. They remain algorithm/toolchain experiments requiring separate evidence and, where applicable, flight validation.

## External peripheral timing

The active `hardware.h` selects `HW_I2C_SPEED_FAST2`, documented by this driver as nominal 1 MHz. The MPU6050 read is one 14-byte burst: write address + register + repeated-start read address + 14 data bytes = 17 wire bytes/153 SCL periods. Ideal bus occupancy is therefore 153 µs. This is theoretical bus time, not measured sensor-to-motor latency.

The driver blocks in BUSY/TXIS/TXE/RXNE flag polls. Dynamic polling iterations, clock stretching, interrupt interference, and physical rise times are unknown. XN297/Bayang uses software SPI: the steady status check has one command/response byte pair (16 bit iterations), while payload and telemetry work is packet-dependent. Neither peripheral time is mixed into the flight-math score.

## Remaining major bottlenecks

1. Software float helper bodies dominate the trace: `__aeabi_fmul` contributes 22.38M static-cost units, `__aeabi_fadd` 16.56M, and `__aeabi_fdiv` 3.96M. Ordinary required multiply/add work should not be mechanically rewritten.
2. The unchanged Kalman filters perform six `__aeabi_fdiv` calls per loop. Removing them would require a recurrence/algorithm decision and is **ALGORITHM CHANGE — DEFER**.
3. `pid` and `control` remain the largest production bodies/callers (2.42M and 2.18M exclusive static-cost units in the corpus), followed by `imu_calc` (0.81M). Further factoring must pass the same numerical tests.
4. Horizon `atan2approx` and level-mode `stick_vector` account for the remaining mode-dependent divisions. Approximation replacement is **ALGORITHM CHANGE — DEFER**.
5. Production brushed `pwm_set` still performs four float multiplies and four float-to-int conversions per armed loop. Specializing four outputs risks code duplication and update-order changes; benchmark further only with linked-code evidence.
6. I2C polling and XN297 software-SPI dominate peripheral-facing CPU occupancy but cannot be converted into time claims without real bus/interrupt measurements.

## First physical-board measurements

1. Confirm the exact MCU part marking and usable Flash before flashing this 22,180-byte image.
2. Toggle spare GPIOs around `sixaxis_read`, `control`, `imu_calc`, and the final `pwm_set`; capture worst-case phase time and jitter with a logic analyzer across acro/level/Horizon and RX packet/no-packet loops.
3. Capture MPU6050 SCL/SDA to verify actual frequency, 153-clock burst duration, clock stretching, and time from data readiness through the final byte.
4. Measure gyro-data-ready (or I2C start) to motor PWM compare update, not just total loop duration.
5. Exercise Bayang packet reception/telemetry/failsafe while measuring loop jitter and missed nominal deadlines.
6. Add a stack watermark and test startup, calibration, failsafe, telemetry, gestures, and interrupt nesting; the emulator's 260-byte maximum covers only its deterministic math scenario.
7. Compare stock and optimized firmware in restrained hover/prop-off bench tests before tuning. PID, filters, rates, mixer, failsafe, and protocol behavior were intentionally left unchanged.

## Reproducible commands and evidence

```powershell
.\benchmark.ps1 baseline
.\benchmark.ps1 candidate --compare baseline
.\benchmark\.venv\Scripts\python.exe compare.py baseline candidate
```

The clean final snapshot is `benchmark/results/baseline/` and contains the AXF, map, full disassembly, compiler/linker flags, function metrics, static analysis, call graph, and deterministic output corpus. The aggregate comparison against the pre-patch O2/fast-math source baseline is `benchmark/results/baseline/comparison_vs_o2_fastmath_actual.md`.
