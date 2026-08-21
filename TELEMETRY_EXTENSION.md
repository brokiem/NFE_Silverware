# Rajawali extended Bayang telemetry

`RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND` keeps the standard 15-byte response and
5 ms telemetry cadence. Bytes that were previously placeholders now carry HUD
data, so packet size and radio airtime do not increase.

| Byte | Value |
|---:|---|
| 0 | `0x85` telemetry packet |
| 1 | Low-battery value |
| 2 | Extended format marker `0x42` |
| 3–4 | Filtered battery, centivolts; byte 3 bit 3 retains legacy low-battery indication |
| 5–6 | Compensated battery, centivolts |
| 7 | Valid receiver packets per second divided by two |
| 8 | Status flags |
| 9 | Actual flight-controller throttle, 0–255 |
| 10–12 | Signed X/Y/Z gravity-vector components, scaled by 127 |
| 13 | Telemetry sequence counter |
| 14 | Eight-bit sum of bytes 0–13 |

Status flags in byte 8 are: bit 0 armed, bit 1 failsafe, bit 2 in air, bit 3
idle-up, bit 4 level mode, bit 5 race mode, bit 6 horizon mode, and bit 7 low
battery.

The matching ESP32 host displays this data in `fpv_hud.html`. Receivers without
the `0x42` marker still provide battery and LQI through the legacy fields.
