# BWHOOP/Rajawali binary baseline

Generated from `6240000::V6.24::ARMCLANG` for `NFE_Silverware` / `STM32F030F4`.

All cost values below are **STATIC COST ESTIMATE** relative units. They are not cycles or physical time.

## Exact target and build flags

- Board: `BWHOOP` only
- Receiver: `RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND` with `USE_MULTI`; `RX_SBUS` is disabled
- CPU: Cortex-M0 / ARMv6-M soft float; active firmware clock path is 48 MHz (`ENABLE_OVERCLOCK` disabled)
- Optimizer: ArmClang `-O1`, function sections, no LTO
- Exact per-file commands for every translation unit are saved in `compiler_flags.json` and raw `compiler_dependency.dep`

Representative exact C command recorded by µVision for `control.c`:

```text
-xc -std=c99 --target=arm-arm-none-eabi -mcpu=cortex-m0 -c -fno-rtti -funsigned-char -fshort-enums -fshort-wchar -D__MICROLIB -gdwarf-4 -O1 -ffunction-sections -Wall -Wextra -Wno-packed -Wno-reserved-id-macro -Wno-unused-macros -Wno-documentation-unknown-command -Wno-documentation -Wno-license-management -Wno-parentheses-equality -Wno-reserved-identifier -I ./src -I ../Libraries/STM32F0xx_StdPeriph_Driver/inc -I ../Libraries/CMSIS/Include -I ./src -I ../ -I ../Libraries/CMSIS/Device/ST/STM32F0xx/Include -I ../Libraries/CMSIS/Include -I ../Libraries/STM32F0xx_StdPeriph_Driver/inc -I ../Utilities/ -IC:/Users/windows/AppData/Local/Arm/Packs/Keil/STM32F0xx_DFP/3.1.1/Device/Include -D__UVISION_VERSION="543" -DSTM32F030x6 -DUSE_STDPERIPH_DRIVER -DSTM32F031 -o ./objects/control.o -MMD
```

Exact linker options from the generated response file:

```text
--cpu Cortex-M0 --library_type=microlib --strict --scatter ".\Objects\nfe_silverware.sct" --summary_stderr --info summarysizes --map --load_addr_map_info --xref --callgraph --symbols --info sizes --info totals --info unused --info veneers --list ".\Listings\nfe_silverware.map" -o .\Objects\nfe_silverware.axf
```

## Binary memory

- Flash/ROM: 19576 bytes (code 19054, RO data 322, RW initializers 200)
- RAM: 2248 bytes (RW 200, ZI 2048)
- Linker regions: 31744 bytes Flash and 4096 bytes RAM
- Project device declaration: 16384 bytes IROM for STM32F030F4
- Linked functions reachable from active loop roots: 57

The generated scatter file permits 31,744 Flash bytes and the compiler command defines `STM32F030x6`, while the µVision device/CPU declaration says `STM32F030F4` with 16,384 bytes IROM. The 19,576-byte image fits the linker region but exceeds the declared device IROM by 3,192 bytes. This configuration inconsistency must be resolved before physical flashing; the benchmark does not silently reinterpret it.

## Top 10 expected dynamic CPU opportunities

| Rank | Function | Expected calls/loop | ROM B | Static score/call | Expected score/loop | Expected float-helper calls/loop |
|---:|---|---:|---:|---:|---:|---|
| 1 | `pid` | 3 | 792 | 3296 | 9888 | __aeabi_fmul×63, __aeabi_fsub×12, __aeabi_fadd×33, __aeabi_fdiv×3 |
| 2 | `control` | 1 | 2512 | 6951 | 6951 | __aeabi_fsub×23, __aeabi_fdiv×5, __aeabi_fadd×24, __aeabi_fmul×28 |
| 3 | `imu_calc` | 1 | 744 | 3843 | 3843 | __aeabi_fsub×12, __aeabi_fmul×38, __aeabi_fadd×7 |
| 4 | `lpffilter` | 3 | 104 | 564 | 1692 | __aeabi_fadd×9, __aeabi_fdiv×3, __aeabi_fsub×6, __aeabi_fmul×6 |
| 5 | `lpffilter2` | 3 | 104 | 564 | 1692 | __aeabi_fadd×9, __aeabi_fdiv×3, __aeabi_fsub×6, __aeabi_fmul×6 |
| 6 | `rotateErrors` | 1 | 180 | 1237 | 1237 | __aeabi_fmul×12, __aeabi_fsub×3, __aeabi_fadd×3 |
| 7 | `Q_rsqrt` | 2 | 88 | 545 | 1090 | __aeabi_fmul×14, __aeabi_fsub×4 |
| 8 | `checkrx` | 1 | 1012 | 1085 | 1085 | __aeabi_fmul×4 |
| 9 | `lpf` | 4 | 46 | 262 | 1048 | __aeabi_fsub×4, __aeabi_fmul×8, __aeabi_fadd×4 |
| 10 | `pid_precalc` | 1 | 164 | 721 | 721 | __aeabi_fdiv×3, __aeabi_fmul×3, __aeabi_fsub×1, __aeabi_fadd×1 |

Ranking combines linked function assembly, linked software-helper bodies, and the explicit expected-executions model. It is triage evidence, not hardware timing.

## Linked active-path functions

| Function | Object | ROM B | Instructions | Stack frame (derived) | BL sites | Loads | Stores | Branches |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `GPIO_Init` | `stm32f0xx_gpio.o` | 116 | 58 | 24 | 0 | 14 | 10 | 5 |
| `I2C_GetFlagStatus` | `stm32f0xx_i2c.o` | 10 | 5 | 0 | 0 | 1 | 0 | 0 |
| `I2C_ReceiveData` | `stm32f0xx_i2c.o` | 6 | 3 | 0 | 0 | 1 | 0 | 0 |
| `I2C_SendData` | `stm32f0xx_i2c.o` | 4 | 2 | 0 | 0 | 0 | 1 | 0 |
| `I2C_TransferHandling` | `stm32f0xx_i2c.o` | 28 | 14 | 8 | 0 | 4 | 2 | 0 |
| `Q_rsqrt` | `imu.o` | 88 | 35 | 16 | 9 | 1 | 1 | 0 |
| `__aeabi_f2iz` | `ffixi.o` | 50 | 25 | 0 | 0 | 0 | 0 | 4 |
| `__aeabi_fadd` | `fadd.o` | 162 | 79 | 24 | 2 | 0 | 1 | 9 |
| `__aeabi_fcmpeq` | `fcmpeq.o` | 28 | 14 | 0 | 0 | 0 | 0 | 3 |
| `__aeabi_fcmpge` | `fcmpge.o` | 28 | 14 | 0 | 0 | 0 | 0 | 3 |
| `__aeabi_fcmpgt` | `fcmpgt.o` | 28 | 14 | 0 | 0 | 0 | 0 | 3 |
| `__aeabi_fcmple` | `fcmple.o` | 28 | 14 | 0 | 0 | 0 | 0 | 3 |
| `__aeabi_fcmplt` | `fcmplt.o` | 28 | 14 | 0 | 0 | 0 | 0 | 3 |
| `__aeabi_fdiv` | `fdiv.o` | 124 | 61 | 16 | 1 | 0 | 1 | 12 |
| `__aeabi_fmul` | `fmul.o` | 122 | 61 | 16 | 0 | 0 | 1 | 7 |
| `__aeabi_fsub` | `fadd.o` | 8 | 4 | 0 | 0 | 0 | 0 | 1 |
| `__aeabi_i2f` | `fflti.o` | 22 | 10 | 8 | 1 | 0 | 1 | 0 |
| `__aeabi_ui2f` | `ffltui.o` | 14 | 6 | 8 | 1 | 0 | 1 | 0 |
| `_float_epilogue` | `fepilogue.o` | 114 | 57 | 12 | 0 | 2 | 1 | 12 |
| `adc_read` | `drv_adc.o` | 52 | 22 | 8 | 4 | 7 | 1 | 2 |
| `apid` | `angle_pid.o` | 196 | 81 | 40 | 17 | 24 | 11 | 0 |
| `atan2approx` | `imu.o` | 256 | 109 | 40 | 19 | 13 | 5 | 10 |
| `beacon_sequence` | `rx_bayang_protocol_telemetry_autobind.o` | 128 | 57 | 16 | 7 | 13 | 8 | 5 |
| `checkrx` | `rx_bayang_protocol_telemetry_autobind.o` | 1012 | 466 | 64 | 40 | 140 | 72 | 44 |
| `control` | `control.o` | 2512 | 991 | 104 | 139 | 278 | 101 | 104 |
| `fastcos` | `util.o` | 120 | 49 | 16 | 11 | 10 | 1 | 6 |
| `fastsin` | `util.o` | 116 | 48 | 16 | 10 | 9 | 1 | 6 |
| `gettime` | `drv_time.o` | 52 | 26 | 8 | 0 | 10 | 4 | 1 |
| `hw_i2c_readdata` | `drv_hw_i2c.o` | 124 | 58 | 32 | 4 | 8 | 8 | 6 |
| `hw_i2c_sendheader` | `drv_hw_i2c.o` | 120 | 55 | 32 | 5 | 5 | 5 | 8 |
| `i2c_readdata` | `drv_i2c.o` | 8 | 3 | 8 | 1 | 0 | 1 | 0 |
| `imu_calc` | `imu.o` | 744 | 307 | 40 | 65 | 58 | 18 | 14 |
| `limitf` | `util.o` | 40 | 18 | 16 | 2 | 2 | 3 | 2 |
| `lpf` | `util.o` | 46 | 19 | 16 | 4 | 1 | 2 | 0 |
| `lpfcalc_hz` | `util.o` | 52 | 22 | 16 | 4 | 0 | 1 | 2 |
| `lpffilter` | `filter.o` | 104 | 44 | 32 | 8 | 10 | 6 | 0 |
| `lpffilter2` | `filter.o` | 104 | 44 | 32 | 8 | 10 | 6 | 0 |
| `mosi_input` | `drv_spi_3wire.o` | 28 | 13 | 8 | 1 | 3 | 3 | 1 |
| `motormap` | `motorcurve.o` | 2 | 1 | 0 | 0 | 0 | 0 | 0 |
| `pid` | `pid.o` | 792 | 348 | 80 | 48 | 129 | 34 | 31 |
| `pid_precalc` | `pid.o` | 164 | 70 | 16 | 12 | 23 | 7 | 5 |
| `pwm_set` | `drv_pwm.o` | 72 | 32 | 8 | 2 | 7 | 5 | 2 |
| `rcexpo` | `util.o` | 132 | 56 | 24 | 10 | 2 | 1 | 4 |
| `rotateErrors` | `pid.o` | 180 | 72 | 24 | 18 | 16 | 5 | 0 |
| `send_telemetry` | `rx_bayang_protocol_telemetry_autobind.o` | 160 | 72 | 80 | 8 | 11 | 12 | 4 |
| `sixaxis_read` | `sixaxis.o` | 216 | 94 | 104 | 14 | 22 | 15 | 1 |
| `spi_csoff` | `drv_spi_3wire.o` | 8 | 4 | 0 | 0 | 1 | 1 | 0 |
| `spi_cson` | `drv_spi_3wire.o` | 8 | 4 | 0 | 0 | 1 | 1 | 0 |
| `spi_recvbyte` | `drv_spi_3wire.o` | 36 | 18 | 16 | 0 | 3 | 3 | 1 |
| `spi_sendbyte` | `drv_spi_3wire.o` | 68 | 33 | 16 | 1 | 4 | 7 | 5 |
| `splpf` | `filter.o` | 56 | 24 | 24 | 4 | 4 | 3 | 0 |
| `stick_vector` | `stickvector.o` | 300 | 121 | 24 | 29 | 28 | 10 | 4 |
| `xn_command` | `drv_xn297_3wire.o` | 22 | 8 | 8 | 3 | 0 | 1 | 0 |
| `xn_readpayload` | `drv_xn297_3wire.o` | 40 | 15 | 16 | 5 | 0 | 2 | 2 |
| `xn_readreg` | `drv_xn297_3wire.o` | 36 | 13 | 8 | 5 | 0 | 1 | 0 |
| `xn_writepayload` | `drv_xn297_3wire.o` | 36 | 14 | 16 | 4 | 1 | 1 | 2 |
| `xn_writereg` | `drv_xn297_3wire.o` | 34 | 13 | 16 | 4 | 0 | 1 | 0 |

## External peripheral timing (kept separate)

- MPU6050: 14 payload bytes, 17 wire bytes / 153 SCL clocks per loop. At the configured nominal 400 kHz this is 382.5 µs theoretical bus time. The driver blocks in flag-poll loops; this wait is not included in CPU static scores.
- XN297L: steady status polling performs two software-SPI bytes (16 bit iterations); packet and telemetry traffic are conditional. This GPIO work is reported separately from flight-math emulation.

See `function_metrics.csv`, `static_analysis.json`, `callgraph.dot`, `expected_loop_cost.json`, and the saved AXF/map/disassembly for auditable evidence.

## Deterministic linked-math execution

- Iterations: 2048
- Executed ARM instruction trace: 55607102
- **STATIC COST ESTIMATE**: 69830068 relative units (34096.71 per iteration)
- Maximum observed stack depth: 324 bytes
- Accidental linked double-helper call sites: none

| Production function | Dynamic entries | Entries/iteration |
|---|---:|---:|
| `lpffilter` | 6144 | 3.0000 |
| `lpffilter2` | 6144 | 3.0000 |
| `control` | 2048 | 1.0000 |
| `pid` | 6144 | 3.0000 |
| `pwm_set` | 8192 | 4.0000 |
| `imu_calc` | 2048 | 1.0000 |
| `Q_rsqrt` | 1533 | 0.7485 |

Runtime soft-float calls: `__aeabi_fadd` × 219322, `__aeabi_fcmpeq` × 18944, `__aeabi_fcmpge` × 50900, `__aeabi_fcmpgt` × 30720, `__aeabi_fcmple` × 67801, `__aeabi_fcmplt` × 42431, `__aeabi_fdiv` × 25022, `__aeabi_fmul` × 431548, `__aeabi_fsub` × 135427, `__aeabi_i2f` × 18432, `__aeabi_memclr` × 2, `__aeabi_ui2f` × 4096.

The output corpus contains 2048 × 17 production-state/output floats (0 non-finite) and is saved in binary and JSON form for ULP comparison.
