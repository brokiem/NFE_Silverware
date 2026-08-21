# ArmClang Rajawali compiler matrix

This matrix rebuilds the exact linked BWHOOP/Rajawali firmware and deterministic production flight-math harness for every ArmClang 6.24 optimization level, with fast-math explicitly enabled/disabled and LTO enabled/disabled.

All dynamic instruction and cost results are **STATIC PERFORMANCE ESTIMATE** values from the hardware-independent linked harness. They are not physical cycles or time. LTO harness code is generated in the harness link context, so the saved full-firmware AXF/map/disassembly remains the ground truth for actual linked firmware structure.

Successful configurations: 20/28. Reference: `-O2 -ffast-math`, no LTO.
The working hardware assumption is 32 KB Flash, with only `0x08000000`–`0x08007BFF` (31,744 bytes) available to firmware and the final 1,024 bytes reserved for persistence.

## Ranked results

| Rank | Effective configuration | ROM B | ROM Δ | RAM B | Firmware insns | Executed insns | Trace Δ | Static cost | Cost Δ | Stack B | Max abs error | ULP | Mismatches |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `-Os fast LTO` | 18096 | -4084 | 2000 | 6930 | 47768207 | -1392933 | 59884902 | -1716728 | 260 | 1.31130219e-06 | 12288 | 10169 |
| 2 | `-O1 fast LTO` | 22112 | -68 | 2016 | 8751 | 48029126 | -1132014 | 60252500 | -1349130 | 260 | 1.31130219e-06 | 12288 | 9875 |
| 3 | `-O3 fast no-LTO` | 22308 | +128 | 2376 | 8817 | 49161170 | +30 | 61534350 | -67280 | 252 | 0 | 0 | 0 |
| 4 | `-Ofast fast no-LTO` | 22308 | +128 | 2376 | 8817 | 49161170 | +30 | 61534350 | -67280 | 252 | 0 | 0 | 0 |
| 5 | `-O2 fast no-LTO` | 22180 | +0 | 2240 | 8631 | 49161140 | +0 | 61601630 | +0 | 260 | 0 | 0 | 0 |
| 6 | `-O1 fast no-LTO` | 19280 | -2900 | 2248 | 7371 | 49604074 | +442934 | 62397324 | +795694 | 324 | 1.31130219e-06 | 12288 | 9875 |
| 7 | `-Os fast no-LTO` | 17764 | -4416 | 2288 | 6735 | 49830952 | +669812 | 62576072 | +974442 | 284 | 1.31130219e-06 | 12288 | 10169 |
| 8 | `-Oz fast LTO` | 15160 | -7020 | 2048 | 5986 | 51539518 | +2378378 | 64478827 | +2877197 | 268 | 1.78813934e-06 | 12288 | 14812 |
| 9 | `-Oz fast no-LTO` | 16824 | -5356 | 2424 | 6496 | 53058344 | +3897204 | 66546129 | +4944499 | 292 | 1.78813934e-06 | 12288 | 14812 |
| 10 | `-O0 fast LTO` | 24824 | +2644 | 2176 | 10125 | 60135070 | +10973930 | 77174781 | +15573151 | 436 | 2.56299973e-06 | 12288 | 20100 |
| 11 | `-O0 fast no-LTO` | 26188 | +4008 | 2344 | 10769 | 61895678 | +12734538 | 80591717 | +18990087 | 812 | 2.56299973e-06 | 12288 | 20100 |
| 12 | `-O1 precise LTO` | 27156 | +4976 | 2016 | 10694 | 66673771 | +17512631 | 83919268 | +22317638 | 252 | 2.56299973e-06 | 12288 | 19320 |
| 13 | `-Os precise LTO` | 21844 | -336 | 2000 | 8367 | 66725933 | +17564793 | 83993447 | +22391817 | 252 | 2.56299973e-06 | 12288 | 19320 |
| 14 | `-Oz precise LTO` | 18376 | -3804 | 2048 | 7220 | 67083466 | +17922326 | 84391217 | +22789587 | 252 | 2.56299973e-06 | 12288 | 19320 |
| 15 | `-O2 precise no-LTO` | 25712 | +3532 | 2248 | 9920 | 67060857 | +17899717 | 84528025 | +22926395 | 284 | 2.56299973e-06 | 12288 | 19320 |
| 16 | `-Os precise no-LTO` | 20740 | -1440 | 2288 | 7895 | 67655161 | +18494021 | 85369378 | +23767748 | 300 | 2.56299973e-06 | 12288 | 19320 |
| 17 | `-O1 precise no-LTO` | 22276 | +96 | 2248 | 8544 | 67936610 | +18775470 | 85816152 | +24214522 | 340 | 2.56299973e-06 | 12288 | 19320 |
| 18 | `-Oz precise no-LTO` | 19396 | -2784 | 2424 | 7507 | 68126315 | +18965175 | 85884914 | +24283284 | 276 | 2.56299973e-06 | 12288 | 19320 |
| 19 | `-O0 precise LTO` | 27128 | +4948 | 2176 | 11014 | 75646276 | +26485136 | 97359842 | +35758212 | 444 | 2.56299973e-06 | 12288 | 19320 |
| 20 | `-O0 precise no-LTO` | 28744 | +6564 | 2344 | 11774 | 76996702 | +27835562 | 100737891 | +39136261 | 1060 | 2.56299973e-06 | 12288 | 19320 |

## Reviewed decision

**Keep `-O2 -ffast-math`, no LTO as the production configuration until hardware A/B timing is available.**

- `-Os -ffast-math -flto` is **BENCHMARK FURTHER**. It saves 4,084 B ROM and 240 B RAM, and reduces the harness trace by 1,392,933 instructions (2.83%). Its maximum output difference is 1.31130219e-06, with no non-finite mismatches.
- LTO changes the actual full-firmware structure substantially: `main` grows from 1,428 B/574 instructions/32-byte derived frame to 10,916 B/4,243 instructions/160-byte frame, while `control`, `imu_calc`, filters, and PWM are inlined. The harness is necessarily a different LTO link context, so physical sensor-to-PWM timing and jitter must decide whether the static win transfers to the real loop.
- `-O3 -ffast-math`, no LTO is **REJECT** for this target: only 67,280 modeled cost units improve (0.109%), while ROM grows by 128 B and RAM by 136 B. Its executed trace is 30 instructions higher across the corpus, and `hw_i2c_readdata` grows from 100 B/47 instructions/32-byte frame to 192 B/90 instructions/40-byte frame.
- `-Ofast -ffast-math`, no LTO is machine-code equivalent to the tested O3 fast build and has the same verdict.
- `-Os -ffast-math`, no LTO and both `-Oz` fast variants are **REJECT** for the responsive-flight default: they save Flash but increase the executed trace/static cost. `-Oz -ffast-math -flto` is the 15,160-byte emergency Flash-pressure option.
- Precise-math and O0 variants are **REJECT** for the flight build because their linked helper work and traces are much larger. The O3/Ofast precise no-LTO cells trigger an ArmClang 6.24 backend crash; the remaining O2/O3/Ofast LTO cells do not fit the protected firmware region.

## Runtime helper execution

| Configuration | fadd | fsub | fmul | fdiv | i2f | ui2f | f2iz |
|---|---:|---:|---:|---:|---:|---:|---:|
| `-Os fast LTO` | 219282 | 110891 | 362351 | 14857 | 18432 | 4096 | 0 |
| `-O1 fast LTO` | 219282 | 110891 | 362351 | 14857 | 18432 | 4096 | 0 |
| `-O3 fast no-LTO` | 232594 | 106795 | 375151 | 14859 | 18432 | 4096 | 0 |
| `-Ofast fast no-LTO` | 232594 | 106795 | 375151 | 14859 | 18432 | 4096 | 0 |
| `-O2 fast no-LTO` | 232594 | 106795 | 375151 | 14859 | 18432 | 4096 | 0 |
| `-O1 fast no-LTO` | 232594 | 106795 | 375151 | 14859 | 18432 | 4096 | 0 |
| `-Os fast no-LTO` | 232594 | 106795 | 375151 | 14859 | 18432 | 4096 | 0 |
| `-Oz fast LTO` | 213215 | 125073 | 382831 | 20924 | 18432 | 4096 | 0 |
| `-Oz fast no-LTO` | 226527 | 118929 | 393583 | 20926 | 18432 | 4096 | 0 |
| `-O0 fast LTO` | 232035 | 155297 | 400239 | 24504 | 0 | 22528 | 0 |
| `-O0 fast no-LTO` | 233059 | 164001 | 409967 | 24504 | 0 | 22528 | 0 |
| `-O1 precise LTO` | 229329 | 167219 | 431052 | 40887 | 118100 | 24576 | 0 |
| `-Os precise LTO` | 229329 | 167219 | 431052 | 40887 | 118100 | 24576 | 0 |
| `-Oz precise LTO` | 229329 | 167219 | 431052 | 40887 | 118100 | 24576 | 0 |
| `-O2 precise no-LTO` | 231889 | 169779 | 431052 | 40888 | 118100 | 24576 | 0 |
| `-Os precise no-LTO` | 231889 | 169779 | 431052 | 40888 | 118100 | 24576 | 0 |
| `-O1 precise no-LTO` | 231889 | 172339 | 431052 | 40888 | 120660 | 24576 | 0 |
| `-Oz precise no-LTO` | 231889 | 169779 | 431052 | 40888 | 118100 | 24576 | 0 |
| `-O0 precise LTO` | 231889 | 172339 | 432588 | 61368 | 123732 | 24576 | 0 |
| `-O0 precise no-LTO` | 231889 | 172339 | 432588 | 61368 | 123732 | 24576 | 0 |

## Failed configurations

- `matrix_o2_precise_lto`: link overflow: 8936 bytes could not fit in the 0x7C00 firmware region
- `matrix_o2_fast_lto`: link overflow: 2396 bytes could not fit in the 0x7C00 firmware region
- `matrix_o3_precise_nolto`: armclang: error in backend: underestimated function size
- `matrix_o3_precise_lto`: link overflow: 10068 bytes could not fit in the 0x7C00 firmware region
- `matrix_o3_fast_lto`: link overflow: 2968 bytes could not fit in the 0x7C00 firmware region
- `matrix_ofast_precise_nolto`: armclang: error in backend: underestimated function size
- `matrix_ofast_precise_lto`: link overflow: 10068 bytes could not fit in the 0x7C00 firmware region
- `matrix_ofast_fast_lto`: link overflow: 2968 bytes could not fit in the 0x7C00 firmware region

## Reproduction

```powershell
.\benchmark.ps1 matrix
```

Each successful configuration has its own `benchmark/results/matrix_*/` directory containing the exact AXF, map, disassembly, recorded compiler flags, call graph, static analysis, linked harness, dynamic trace, and numerical corpus. The project file is restored byte-for-byte after the matrix, including when a build fails.
