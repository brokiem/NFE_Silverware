from __future__ import annotations

import bisect
import json
import math
import struct
from collections import Counter
from pathlib import Path


def _symbol(symtab, name: str):
    matches = symtab.get_symbol_by_name(name)
    if not matches:
        raise RuntimeError(f"Required benchmark symbol not found: {name}")
    return matches[0]


def _align_down(value: int, alignment: int = 0x1000) -> int:
    return value & ~(alignment - 1)


def _align_up(value: int, alignment: int = 0x1000) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def execute_math_elf(result_dir: Path) -> None:
    try:
        from elftools.elf.elffile import ELFFile
        from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_BLOCK, UC_MODE_MCLASS, UC_MODE_THUMB
        from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_SP
    except ImportError as error:
        raise RuntimeError(
            "The free benchmark dependencies are missing. Run benchmark.ps1 once to create the local virtual environment."
        ) from error

    axf_path = result_dir / "flight_math.axf"
    instruction_rows = json.loads((result_dir / "flight_math_instructions.json").read_text(encoding="utf-8"))
    static_analysis = json.loads((result_dir / "flight_math_static_analysis.json").read_text(encoding="utf-8"))
    instructions = sorted(instruction_rows, key=lambda item: item["address"])
    instruction_addresses = [item["address"] for item in instructions]
    function_starts = {item["address"]: item["name"] for item in static_analysis["functions"]}

    with axf_path.open("rb") as stream:
        elf = ELFFile(stream)
        symtab = elf.get_section_by_name(".symtab")
        if symtab is None:
            raise RuntimeError("Harness ELF has no symbol table")

        alloc_sections = [
            section for section in elf.iter_sections()
            if section["sh_flags"] & 0x2 and section["sh_size"] and section["sh_addr"]
        ]
        ranges = []
        for section in alloc_sections:
            start = _align_down(section["sh_addr"])
            end = _align_up(section["sh_addr"] + section["sh_size"])
            ranges.append((start, end))
        ranges.append((0x30000000, 0x30001000))
        ranges.sort()
        merged = []
        for start, end in ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        emulator = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for start, end in merged:
            emulator.mem_map(start, end - start)
        for section in alloc_sections:
            if section["sh_type"] != "SHT_NOBITS":
                data = section.data()
                if data:
                    emulator.mem_write(section["sh_addr"], data)

        stop_address = 0x30000000
        emulator.mem_write(stop_address, b"\x00\xbe")
        stack_top = max(end for start, end in merged if start < 0x30000000) - 8
        # Prefer the top of the harness RW region, not the ROM region.
        ram_ranges = [(start, end) for start, end in merged if 0x20000000 <= start < 0x30000000]
        if ram_ranges:
            stack_top = max(end for _, end in ram_ranges) - 8
        emulator.reg_write(UC_ARM_REG_SP, stack_top)
        emulator.reg_write(UC_ARM_REG_LR, stop_address | 1)

        dynamic_categories = Counter()
        dynamic_functions = Counter()
        dynamic_calls = Counter()
        dynamic_cost_by_function = Counter()
        dynamic_instructions_by_function = Counter()
        dynamic_score = 0
        dynamic_instructions = 0
        minimum_sp = stack_top
        stopped = False

        def on_block(uc, address, size, _user_data):
            nonlocal dynamic_score, dynamic_instructions, minimum_sp, stopped
            if address == stop_address:
                stopped = True
                uc.emu_stop()
                return
            minimum_sp = min(minimum_sp, uc.reg_read(UC_ARM_REG_SP))
            if address in function_starts:
                dynamic_functions[function_starts[address]] += 1
            index = bisect.bisect_left(instruction_addresses, address)
            end = address + size
            while index < len(instructions) and instructions[index]["address"] < end:
                row = instructions[index]
                if row["address"] >= address:
                    dynamic_categories[row["category"]] += 1
                    dynamic_score += row["score"]
                    dynamic_instructions += 1
                    dynamic_cost_by_function[row["function"]] += row["score"]
                    dynamic_instructions_by_function[row["function"]] += 1
                    if row["category"] == "call":
                        target = row["operands"].split(";", 1)[0].strip().split(",", 1)[0].strip()
                        dynamic_calls[(row["function"], target)] += 1
                index += 1

        emulator.hook_add(UC_HOOK_BLOCK, on_block)
        entry = _symbol(symtab, "benchmark_entry")["st_value"] & ~1
        # Unoptimized matrix variants can take several minutes under the
        # instrumented block hook even though the same 2,048-iteration corpus
        # completes normally. Keep a finite ceiling without misclassifying
        # those builds as semantic failures.
        emulator.emu_start(entry | 1, 0, timeout=600_000_000, count=1_000_000_000)
        if not stopped:
            raise RuntimeError("Harness emulator stopped before returning through the sentinel")

        completed_address = _symbol(symtab, "benchmark_completed")["st_value"]
        completed = struct.unpack("<I", emulator.mem_read(completed_address, 4))[0]
        if completed != 1:
            raise RuntimeError(f"Harness did not complete (benchmark_completed={completed})")
        iteration_count = struct.unpack("<I", emulator.mem_read(_symbol(symtab, "benchmark_iteration_count")["st_value"], 4))[0]
        floats_per_record = struct.unpack("<I", emulator.mem_read(_symbol(symtab, "benchmark_floats_per_record")["st_value"], 4))[0]
        output_address = _symbol(symtab, "benchmark_output")["st_value"]
        output_bytes = bytes(emulator.mem_read(output_address, iteration_count * floats_per_record * 4))
        values = struct.unpack(f"<{iteration_count * floats_per_record}f", output_bytes)
        records = [list(values[index:index + floats_per_record]) for index in range(0, len(values), floats_per_record)]
        modes_address = _symbol(symtab, "benchmark_modes")["st_value"]
        mode_bytes = bytes(emulator.mem_read(modes_address, iteration_count * 4))
        modes = list(struct.unpack(f"<{iteration_count}I", mode_bytes))

    (result_dir / "math_output.bin").write_bytes(output_bytes)
    (result_dir / "math_output.json").write_text(json.dumps({
        "iterations": iteration_count,
        "floats_per_record": floats_per_record,
        "field_order": [
            "motor_bl", "motor_fl", "motor_fr", "motor_br",
            "gyro_roll", "gyro_pitch", "gyro_yaw",
            "pid_roll", "pid_pitch", "pid_yaw",
            "setpoint_roll", "setpoint_pitch", "setpoint_yaw",
            "gravity_x", "gravity_y", "gravity_z", "throttle_sum",
        ],
        "modes": modes,
        "records": records,
    }, separators=(",", ":")) + "\n", encoding="utf-8")

    helper_executions = Counter()
    helpers_by_caller = {}
    for (caller, callee), count in dynamic_calls.items():
        if callee.startswith("__aeabi_"):
            helper_executions[callee] += count
            helpers_by_caller.setdefault(caller, {})[callee] = count
    trace = {
        "label": "STATIC COST ESTIMATE",
        "execution_engine": "Unicorn ARM Cortex-M/Thumb emulator; no STM32 peripheral model",
        "iterations": iteration_count,
        "executed_arm_instructions": dynamic_instructions,
        "relative_static_cost": dynamic_score,
        "relative_static_cost_per_iteration": dynamic_score / iteration_count,
        "maximum_observed_stack_depth_bytes": stack_top - minimum_sp,
        "nonfinite_output_values": sum(not math.isfinite(value) for value in values),
        "instruction_categories": dict(dynamic_categories),
        "function_entry_counts": dict(dynamic_functions),
        "instruction_counts_by_function": dict(dynamic_instructions_by_function),
        "relative_static_cost_by_function": dict(dynamic_cost_by_function),
        "runtime_helper_call_counts": dict(helper_executions),
        "runtime_helper_calls_by_function": helpers_by_caller,
        "dynamic_call_edges": [
            {"caller": caller, "callee": callee, "executions": count}
            for (caller, callee), count in sorted(dynamic_calls.items())
        ],
        "limitations": [
            "Counts are from deterministic emulation of the linked math ELF, not hardware timing.",
            "The score applies static ARMv6-M category weights to the executed instruction trace.",
            "Flash wait states, peripheral waits, interrupts, and real bus contention are absent.",
        ],
    }
    (result_dir / "math_trace.json").write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
