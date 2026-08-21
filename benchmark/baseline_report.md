# BWHOOP/Rajawali binary baseline

Generated from `6240000::V6.24::ARMCLANG` for `NFE_Silverware` / `STM32F030F4`.

All cost values below are **STATIC COST ESTIMATE** relative units. They are not cycles or physical time.

## Exact target and build flags

- Board: `BWHOOP` only
- Receiver: `RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND` with `USE_MULTI`; `RX_SBUS` is disabled
- CPU: Cortex-M0 / ARMv6-M soft float; active firmware clock path is 48 MHz (`ENABLE_OVERCLOCK` disabled)
- Optimizer: ArmClang `-O2`, fast-math enabled, LTO disabled
- Exact per-file commands for every translation unit are saved in `compiler_flags.json` and raw `compiler_dependency.dep`

Representative exact C command recorded by µVision for `control.c`:

```text
-xc -std=c99 --target=arm-arm-none-eabi -mcpu=cortex-m0 -c -fno-rtti -funsigned-char -fshort-enums -fshort-wchar -D__MICROLIB -gdwarf-4 -O2 -ffunction-sections -Wall -Wextra -Wno-packed -Wno-reserved-id-macro -Wno-unused-macros -Wno-documentation-unknown-command -Wno-documentation -Wno-license-management -Wno-parentheses-equality -Wno-reserved-identifier -I ./src -I ../Libraries/STM32F0xx_StdPeriph_Driver/inc -I ../Libraries/CMSIS/Include -I ./src -I ../ -I ../Libraries/CMSIS/Device/ST/STM32F0xx/Include -I ../Libraries/CMSIS/Include -I ../Libraries/STM32F0xx_StdPeriph_Driver/inc -I ../Utilities/ -ffast-math -IC:/Users/windows/AppData/Local/Arm/Packs/Keil/STM32F0xx_DFP/3.1.1/Device/Include -D__UVISION_VERSION="543" -DSTM32F030x6 -DUSE_STDPERIPH_DRIVER -DSTM32F031 -o ./objects/control.o -MMD
```

Exact linker options from the generated response file:

```text
--cpu Cortex-M0 --library_type=microlib --strict --scatter ".\Objects\nfe_silverware.sct" --summary_stderr --info summarysizes --map --load_addr_map_info --xref --callgraph --symbols --info sizes --info totals --info unused --info veneers --list ".\Listings\nfe_silverware.map" -o .\Objects\nfe_silverware.axf
```

## Binary memory

- Flash/ROM: 22180 bytes (code 21698, RO data 282, RW initializers 200)
- RAM: 2240 bytes (RW 200, ZI 2040)
- Linker regions: 31744 bytes Flash and 4096 bytes RAM
- Project device declaration: 16384 bytes IROM for STM32F030F4
- Linked functions reachable from active loop roots: 54

The generated scatter file permits 31,744 Flash bytes and the compiler command defines `STM32F030x6`, while the µVision device/CPU declaration says `STM32F030F4` with 16,384 bytes IROM. The 22,180-byte image fits the linker region but exceeds the declared device IROM by 5,796 bytes. This configuration inconsistency must be resolved before physical flashing; the benchmark does not silently reinterpret it.

## Top 10 linked static-cost triage targets

| Rank | Function | Model entries/loop | ROM B | Static score/body | Model score/loop | Static helper BL sites × model entries |
|---:|---|---:|---:|---:|---:|---|
| 1 | `pid` | 3 | 832 | 3294 | 9882 | __aeabi_fmul×54, __aeabi_fsub×12, __aeabi_fadd×33, __aeabi_fdiv×9 |
| 2 | `control` | 1 | 2936 | 8696 | 8696 | __aeabi_fmul×29, __aeabi_fadd×39, __aeabi_fsub×25 |
| 3 | `imu_calc` | 1 | 808 | 4585 | 4585 | __aeabi_fsub×12, __aeabi_fmul×48, __aeabi_fadd×7 |
| 4 | `lpffilter` | 3 | 96 | 553 | 1659 | __aeabi_fadd×9, __aeabi_fdiv×3, __aeabi_fsub×3, __aeabi_fmul×6 |
| 5 | `lpffilter2` | 3 | 96 | 553 | 1659 | __aeabi_fadd×9, __aeabi_fdiv×3, __aeabi_fsub×3, __aeabi_fmul×6 |
| 6 | `checkrx` | 1 | 1328 | 1297 | 1297 | __aeabi_fmul×4 |
| 7 | `rotateErrors` | 1 | 168 | 1093 | 1093 | __aeabi_fmul×10, __aeabi_fsub×3, __aeabi_fadd×3 |
| 8 | `Q_rsqrt` | 2 | 84 | 543 | 1086 | __aeabi_fmul×14, __aeabi_fsub×4 |
| 9 | `lpf` | 4 | 30 | 184 | 736 | __aeabi_fsub×4, __aeabi_fmul×4, __aeabi_fadd×4 |
| 10 | `pid_precalc` | 1 | 156 | 638 | 638 | __aeabi_fdiv×2, __aeabi_fmul×3, __aeabi_fadd×1 |

Ranking combines linked function assembly, linked software-helper bodies, and the explicit source-path entry model. Helper values are static BL sites scaled by model entries, not measured dynamic calls; branch-dependent and cached helper executions are reported by the deterministic trace below. It is triage evidence, not hardware timing.

## Linked active-path functions

| Function | Object | ROM B | Instructions | Stack frame (derived) | BL sites | Loads | Stores | Branches |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `GPIO_Init` | `stm32f0xx_gpio.o` | 230 | 115 | 36 | 0 | 33 | 22 | 7 |
| `I2C_GetFlagStatus` | `stm32f0xx_i2c.o` | 10 | 5 | 0 | 0 | 1 | 0 | 0 |
| `I2C_TransferHandling` | `stm32f0xx_i2c.o` | 28 | 14 | 8 | 0 | 4 | 2 | 0 |
| `Q_rsqrt` | `imu.o` | 84 | 33 | 16 | 9 | 1 | 1 | 0 |
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
| `apid` | `angle_pid.o` | 184 | 76 | 40 | 16 | 23 | 10 | 0 |
| `atan2approx` | `imu.o` | 256 | 109 | 40 | 19 | 13 | 5 | 10 |
| `beacon_sequence` | `rx_bayang_protocol_telemetry_autobind.o` | 128 | 57 | 16 | 7 | 13 | 8 | 5 |
| `checkrx` | `rx_bayang_protocol_telemetry_autobind.o` | 1328 | 593 | 80 | 55 | 177 | 111 | 40 |
| `control` | `control.o` | 2936 | 1157 | 64 | 183 | 310 | 84 | 109 |
| `fastcos` | `util.o` | 256 | 105 | 24 | 23 | 15 | 1 | 13 |
| `fastsin` | `util.o` | 248 | 102 | 24 | 22 | 14 | 1 | 13 |
| `gettime` | `drv_time.o` | 52 | 26 | 8 | 0 | 10 | 4 | 1 |
| `hw_i2c_readdata` | `drv_hw_i2c.o` | 100 | 47 | 32 | 3 | 6 | 6 | 6 |
| `hw_i2c_sendheader` | `drv_hw_i2c.o` | 116 | 54 | 32 | 4 | 5 | 6 | 8 |
| `i2c_readdata` | `drv_i2c.o` | 8 | 3 | 8 | 1 | 0 | 1 | 0 |
| `imu_calc` | `imu.o` | 808 | 325 | 48 | 79 | 65 | 28 | 7 |
| `limitf` | `util.o` | 70 | 32 | 24 | 3 | 1 | 2 | 4 |
| `lpf` | `util.o` | 30 | 12 | 16 | 3 | 1 | 2 | 0 |
| `lpfcalc_hz` | `util.o` | 58 | 25 | 16 | 4 | 0 | 1 | 2 |
| `lpffilter` | `filter.o` | 96 | 41 | 24 | 7 | 9 | 4 | 0 |
| `lpffilter2` | `filter.o` | 96 | 41 | 24 | 7 | 9 | 4 | 0 |
| `mosi_input` | `drv_spi_3wire.o` | 28 | 13 | 8 | 1 | 3 | 3 | 1 |
| `pid` | `pid.o` | 832 | 367 | 72 | 49 | 127 | 35 | 34 |
| `pid_precalc` | `pid.o` | 156 | 68 | 16 | 10 | 22 | 7 | 6 |
| `pwm_set` | `drv_pwm.o` | 80 | 30 | 8 | 2 | 5 | 2 | 4 |
| `rcexpo` | `util.o` | 116 | 49 | 24 | 9 | 2 | 2 | 4 |
| `rotateErrors` | `pid.o` | 168 | 68 | 32 | 16 | 17 | 6 | 0 |
| `send_telemetry` | `rx_bayang_protocol_telemetry_autobind.o` | 172 | 78 | 88 | 8 | 11 | 19 | 2 |
| `sixaxis_read` | `sixaxis.o` | 228 | 95 | 56 | 19 | 24 | 14 | 0 |
| `spi_csoff` | `drv_spi_3wire.o` | 8 | 4 | 0 | 0 | 1 | 1 | 0 |
| `spi_cson` | `drv_spi_3wire.o` | 8 | 4 | 0 | 0 | 1 | 1 | 0 |
| `spi_recvbyte` | `drv_spi_3wire.o` | 124 | 62 | 32 | 0 | 13 | 20 | 0 |
| `spi_sendbyte` | `drv_spi_3wire.o` | 184 | 91 | 16 | 1 | 5 | 35 | 18 |
| `splpf` | `filter.o` | 44 | 18 | 16 | 4 | 4 | 3 | 0 |
| `stick_vector` | `stickvector.o` | 312 | 129 | 32 | 27 | 31 | 14 | 5 |
| `xn_command` | `drv_xn297_3wire.o` | 22 | 8 | 8 | 3 | 0 | 1 | 0 |
| `xn_readpayload` | `drv_xn297_3wire.o` | 40 | 15 | 16 | 5 | 0 | 2 | 2 |
| `xn_readreg` | `drv_xn297_3wire.o` | 36 | 13 | 8 | 5 | 0 | 1 | 0 |
| `xn_writepayload` | `drv_xn297_3wire.o` | 36 | 14 | 16 | 4 | 1 | 1 | 2 |
| `xn_writereg` | `drv_xn297_3wire.o` | 34 | 13 | 16 | 4 | 0 | 1 | 0 |

## External peripheral timing (kept separate)

- MPU6050: 14 payload bytes, 17 wire bytes / 153 SCL clocks per loop. At the configured nominal 1 MHz this is 153 µs theoretical bus time. The driver blocks in flag-poll loops; this wait is not included in CPU static scores.
- XN297L: steady status polling performs two software-SPI bytes (16 bit iterations); packet and telemetry traffic are conditional. This GPIO work is reported separately from flight-math emulation.

See `function_metrics.csv`, `static_analysis.json`, `callgraph.dot`, `expected_loop_cost.json`, and the saved AXF/map/disassembly for auditable evidence.

## Deterministic linked-math execution

- Iterations: 2048
- Executed ARM instruction trace: 49161140
- **STATIC COST ESTIMATE**: 61601630 relative units (30078.92 per iteration)
- Maximum observed stack depth: 260 bytes
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

Runtime soft-float calls: `__aeabi_fadd` × 232594, `__aeabi_fcmpeq` × 18944, `__aeabi_fcmpge` × 37670, `__aeabi_fcmpgt` × 51712, `__aeabi_fcmple` × 42698, `__aeabi_fcmplt` × 56897, `__aeabi_fdiv` × 14859, `__aeabi_fmul` × 375151, `__aeabi_fsub` × 106795, `__aeabi_i2f` × 18432, `__aeabi_memclr` × 2, `__aeabi_ui2f` × 4096.

The output corpus contains 2048 × 17 production-state/output floats (0 non-finite) and is saved in binary and JSON form for ULP comparison.
