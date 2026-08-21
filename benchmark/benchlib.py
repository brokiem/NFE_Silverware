from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from bisect import bisect_right
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmark"
RESULTS = BENCHMARK / "results"
PROJECT_DIR = ROOT / "Silverware"
PROJECT = PROJECT_DIR / "Silverware.uvprojx"
TARGET = "NFE_Silverware"
OBJECTS = PROJECT_DIR / "Objects"
LISTINGS = PROJECT_DIR / "Listings"

EXPECTED_DEFINES = {
    "board": "BWHOOP",
    "receiver": "RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND",
    "transmitter_compatibility": "USE_MULTI",
}

PRODUCTION_MATH_OBJECTS = [
    "control.o",
    "pid.o",
    "filter.o",
    "imu.o",
    "angle_pid.o",
    "stickvector.o",
    "motorcurve.o",
    "util.o",
]

INSTRUCTION_RE = re.compile(
    r"^\s*0x([0-9a-fA-F]+):\s+([0-9a-fA-F]{4,8})\s+.{0,8}?\s{2,}([A-Z][A-Z0-9.]*)\s*(.*?)\s*$"
)
SYMBOL_RE = re.compile(
    r"^\s*\d+\s+(\S+)\s+0x([0-9a-fA-F]+)\s+\S+\s+\S+\s+Code\s+\S+\s+0x([0-9a-fA-F]+)\s*$"
)
MAP_FUNCTION_RE = re.compile(
    r"^\s*(\S+)\s+0x[0-9a-fA-F]+\s+Thumb Code\s+\d+\s+(\S+\.o)\("
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: list[str], cwd: Path, output_path: Path | None = None, ok_codes: tuple[int, ...] = (0,)) -> str:
    printable = subprocess.list2cmdline(args)
    process = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = f"> {printable}\n{process.stdout}"
    if output_path:
        output_path.write_text(output, encoding="utf-8")
    if process.returncode not in ok_codes:
        raise RuntimeError(f"Command failed ({process.returncode}): {printable}\n{process.stdout}")
    return process.stdout


def find_first(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path.resolve()
    return None


def locate_tools() -> dict[str, Path]:
    roots = []
    if os.environ.get("KEIL_ROOT"):
        roots.append(Path(os.environ["KEIL_ROOT"]))
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "Keil_v5")
    roots.extend([Path("C:/Keil_v5"), Path("C:/Keil")])

    uv4 = find_first([root / "UV4" / "UV4.exe" for root in roots])
    bin_dirs = [root / "ARM" / "ARMCLANG" / "Bin" for root in roots]
    armclang = find_first([path / "armclang.exe" for path in bin_dirs])
    armlink = find_first([path / "armlink.exe" for path in bin_dirs])
    fromelf = find_first([path / "fromelf.exe" for path in bin_dirs])
    missing = [name for name, value in {"UV4": uv4, "armclang": armclang, "armlink": armlink, "fromelf": fromelf}.items() if value is None]
    if missing:
        raise RuntimeError(
            "Missing Keil/Arm Community tools: "
            + ", ".join(missing)
            + ". Install free Keil MDK Community/STM32 edition or set KEIL_ROOT."
        )
    return {"uv4": uv4, "armclang": armclang, "armlink": armlink, "fromelf": fromelf}


def tool_versions(tools: dict[str, Path]) -> dict:
    versions = {"paths": {key: str(value) for key, value in tools.items()}}
    for name in ("armclang", "armlink", "fromelf"):
        version_option = "--version" if name == "armclang" else "--vsn"
        output = run([str(tools[name]), version_option], ROOT)
        versions[name] = output.strip()
    return versions


def active_defines(path: Path) -> set[str]:
    defines = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*#\s*define\s+([A-Za-z_]\w*)", line)
        if match:
            defines.add(match.group(1))
    return defines


def capture_target_configuration() -> dict:
    config_path = PROJECT_DIR / "src" / "config.h"
    defines = active_defines(config_path)
    tree = ET.parse(PROJECT)
    target = tree.find("./Targets/Target")
    if target is None:
        raise RuntimeError("No Keil target found")
    target_name = target.findtext("TargetName")
    option = target.find("./TargetOption/TargetCommonOption")
    if option is None:
        option = target.find("./TargetOption/TargetCommonOption")

    board_options = ["BWHOOP", "E011", "H8mini_blue_board", "Silverlite_Brushless", "Alienwhoop_ZERO"]
    receiver_options = [
        "RX_SBUS", "RX_CRSF", "RX_DSMX_2048", "RX_DSM2_1024", "RX_IBUS",
        "RX_NRF24_BAYANG_TELEMETRY", "RX_BAYANG_BLE_APP",
        "RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND",
    ]
    selected_boards = [name for name in board_options if name in defines]
    selected_receivers = [name for name in receiver_options if name in defines]
    problems = []
    for role, define in EXPECTED_DEFINES.items():
        if define not in defines:
            problems.append(f"expected {role} define {define}")
    forbidden = [name for name in ("E011", "Alienwhoop_ZERO", "RX_SBUS", "ENABLE_OVERCLOCK") if name in defines]
    if forbidden:
        problems.append("unexpected active defines: " + ", ".join(forbidden))
    if target_name != TARGET:
        problems.append(f"expected target {TARGET}, got {target_name}")
    if selected_boards != [EXPECTED_DEFINES["board"]]:
        problems.append("board selection is not exactly BWHOOP: " + repr(selected_boards))
    if selected_receivers != [EXPECTED_DEFINES["receiver"]]:
        problems.append("receiver selection is not exactly Bayang telemetry autobind: " + repr(selected_receivers))
    if problems:
        raise RuntimeError("Target configuration is not the Rajawali baseline: " + "; ".join(problems))

    return {
        "keil_target": target_name,
        "device": option.findtext("Device") if option is not None else None,
        "cpu": option.findtext("Cpu") if option is not None else None,
        "toolchain": target.findtext("pCCUsed"),
        "active_required_defines": EXPECTED_DEFINES,
        "selected_board_defines": selected_boards,
        "selected_receiver_defines": selected_receivers,
        "verified_disabled": ["E011", "Alienwhoop_ZERO", "RX_SBUS", "ENABLE_OVERCLOCK"],
        "clock_hz_from_active_firmware_configuration": 48000000,
        "active_defines": sorted(defines),
        "configuration_source": str(config_path.relative_to(ROOT)),
    }


def parse_compiler_commands(dep_path: Path) -> list[dict]:
    text = dep_path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"^F \((.*?)\)\([^\n]*?\)\((.*?)\)\r?\nI ", text, flags=re.MULTILINE | re.DOTALL)
    commands = []
    for source, command in matches:
        commands.append({
            "source": source,
            "arguments_as_recorded_by_uvision": " ".join(command.split()),
        })
    return commands


def parse_memory(map_path: Path) -> dict:
    text = map_path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "ro_bytes": r"Total RO\s+Size \(Code \+ RO Data\)\s+(\d+)",
        "rw_bytes": r"Total RW\s+Size \(RW Data \+ ZI Data\)\s+(\d+)",
        "rom_bytes": r"Total ROM Size \(Code \+ RO Data \+ RW Data\)\s+(\d+)",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        values[key] = int(match.group(1)) if match else None
    build_log = (OBJECTS / "nfe_silverware.build_log.htm").read_text(encoding="utf-8", errors="replace")
    size = re.search(r"Program Size: Code=(\d+) RO-data=(\d+) RW-data=(\d+) ZI-data=(\d+)", build_log)
    if size:
        values.update({
            "code_bytes": int(size.group(1)),
            "ro_data_bytes": int(size.group(2)),
            "rw_data_bytes": int(size.group(3)),
            "zi_data_bytes": int(size.group(4)),
        })
        values["ram_bytes"] = values["rw_data_bytes"] + values["zi_data_bytes"]
    scatter_text = (OBJECTS / "nfe_silverware.sct").read_text(encoding="utf-8", errors="replace")
    flash_region = re.search(r"LR_IROM1\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)", scatter_text)
    ram_region = re.search(r"RW_IRAM1\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)", scatter_text)
    values["linker_flash_region_bytes"] = int(flash_region.group(1), 16) if flash_region else None
    values["linker_ram_region_bytes"] = int(ram_region.group(1), 16) if ram_region else None
    project_text = PROJECT.read_text(encoding="utf-8", errors="replace")
    project_irom = re.search(r"<Cpu>.*?IROM\(0x[0-9a-fA-F]+,0x([0-9a-fA-F]+)\)", project_text)
    values["project_device_irom_bytes"] = int(project_irom.group(1), 16) if project_irom else None
    return values


def register_count(register_list: str) -> int:
    count = 0
    for item in register_list.split(","):
        item = item.strip().lower()
        range_match = re.fullmatch(r"r(\d+)-r(\d+)", item)
        if range_match:
            count += int(range_match.group(2)) - int(range_match.group(1)) + 1
        elif re.fullmatch(r"r\d+|lr|pc", item):
            count += 1
    return count


def classify_instruction(mnemonic: str, operands: str, weights: dict) -> tuple[str, int]:
    op = mnemonic.upper().split(".")[0]
    if op in {"BL", "BLX"}:
        return "call", weights["call"]
    if op in {"BX"} or (op == "POP" and "pc" in operands.lower()):
        return "return", weights["return"]
    if op in {"B", "BAL"}:
        return "unconditional_branch", weights["unconditional_branch"]
    if (op.startswith("B") and op not in {"BIC", "BICS", "BKPT"}) or op in {"CBZ", "CBNZ"}:
        return "conditional_branch", weights["conditional_branch"]
    if op.startswith("LDR") or op.startswith("LDM") or op == "POP":
        return "load", weights["load"]
    if op.startswith("STR") or op.startswith("STM") or op == "PUSH":
        return "store", weights["store"]
    if op.startswith("MUL"):
        return "multiply", weights["multiply"]
    return "native_alu_or_other", weights["native_alu_or_other"]


def call_target(operands: str) -> str:
    target = operands.split(";", 1)[0].strip().split(",", 1)[0].strip()
    if re.fullmatch(r"r\d+", target.lower()):
        return "<indirect>"
    return target or "<unknown>"


def parse_map_sources(map_path: Path) -> dict[str, str]:
    sources = {}
    for line in map_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MAP_FUNCTION_RE.match(line)
        if match:
            sources[match.group(1)] = match.group(2)
    return sources


def analyze_disassembly(disasm_path: Path, map_path: Path, cost_model_path: Path) -> dict:
    lines = disasm_path.read_text(encoding="utf-8", errors="replace").splitlines()
    weights = read_json(cost_model_path)["weights"]
    symbols = []
    for line in lines:
        match = SYMBOL_RE.match(line)
        if match:
            symbols.append({"name": match.group(1), "address": int(match.group(2), 16) & ~1, "size": int(match.group(3), 16)})

    # Collapse code aliases at the same address/size while retaining all names.
    grouped: dict[tuple[int, int], list[str]] = {}
    for symbol in symbols:
        grouped.setdefault((symbol["address"], symbol["size"]), []).append(symbol["name"])
    functions = []
    for (address, size), aliases in grouped.items():
        candidates = [name for name in aliases if not name.startswith("$")]
        name = min(candidates or aliases, key=lambda value: (value.startswith("_"), len(value), value))
        functions.append({"name": name, "aliases": sorted(set(aliases)), "address": address, "size": size})
    functions.sort(key=lambda item: (item["address"], item["size"]))
    starts = [item["address"] for item in functions]
    by_name = {alias: item for item in functions for alias in item["aliases"]}
    sources = parse_map_sources(map_path)

    for function in functions:
        function.update({
            "source_object": next((sources[name] for name in function["aliases"] if name in sources), None),
            "instructions": 0,
            "loads": 0,
            "stores": 0,
            "branches": 0,
            "conditional_branches": 0,
            "unconditional_branches": 0,
            "calls_count": 0,
            "calls": {},
            "float_helpers": {},
            "double_helpers": {},
            "conversion_helpers": {},
            "multiply_instructions": 0,
            "stack_local_bytes": 0,
            "stack_saved_bytes": 0,
            "stack_frame_bytes_derived": 0,
            "static_cost_local": 0,
        })

    instruction_rows = []
    for line in lines:
        match = INSTRUCTION_RE.match(line)
        if not match:
            continue
        address = int(match.group(1), 16)
        encoding = match.group(2)
        mnemonic = match.group(3)
        operands = match.group(4)
        if mnemonic in {"DCD", "DCW", "DCB"}:
            continue
        index = bisect_right(starts, address) - 1
        if index < 0:
            continue
        function = functions[index]
        if address >= function["address"] + function["size"]:
            continue
        category, score = classify_instruction(mnemonic, operands, weights)
        function["instructions"] += 1
        function["static_cost_local"] += score
        if category == "load":
            function["loads"] += 1
        elif category == "store":
            function["stores"] += 1
        elif category in {"conditional_branch", "unconditional_branch"}:
            function["branches"] += 1
            function[category + "es"] = function.get(category + "es", 0) + 1
        elif category == "call":
            function["calls_count"] += 1
            target = call_target(operands)
            function["calls"][target] = function["calls"].get(target, 0) + 1
            if re.match(r"__aeabi_f(?:add|sub|mul|div)$", target):
                function["float_helpers"][target] = function["float_helpers"].get(target, 0) + 1
            if re.match(r"__aeabi_d", target):
                function["double_helpers"][target] = function["double_helpers"].get(target, 0) + 1
            if re.match(r"__aeabi_(?:(?:ui|i)2f|f2(?:iz|uiz|lz|ulz)|d2f|f2d)", target):
                function["conversion_helpers"][target] = function["conversion_helpers"].get(target, 0) + 1
        elif category == "multiply":
            function["multiply_instructions"] += 1

        op = mnemonic.upper().split(".")[0]
        if op == "PUSH":
            regs = re.search(r"\{([^}]+)\}", operands)
            if regs:
                function["stack_saved_bytes"] = max(function["stack_saved_bytes"], 4 * register_count(regs.group(1)))
        if op in {"SUB", "SUBS"} and re.search(r"\bsp\s*,\s*sp\s*,", operands, re.IGNORECASE):
            immediate = re.search(r"#(?:0x([0-9a-fA-F]+)|(\d+))", operands)
            if immediate:
                value = int(immediate.group(1), 16) if immediate.group(1) else int(immediate.group(2))
                function["stack_local_bytes"] = max(function["stack_local_bytes"], value)
        instruction_rows.append({
            "address": address,
            "size": len(encoding) // 2,
            "function": function["name"],
            "mnemonic": mnemonic,
            "operands": operands,
            "category": category,
            "score": score,
        })

    helper_scores = {}
    for function in functions:
        function["stack_frame_bytes_derived"] = function["stack_local_bytes"] + function["stack_saved_bytes"]
        for alias in function["aliases"]:
            if alias.startswith("__aeabi_"):
                helper_scores[alias] = function["static_cost_local"]
    for function in functions:
        helper_expansion = 0
        for target, count in function["calls"].items():
            if target.startswith("__aeabi_"):
                helper_expansion += helper_scores.get(target, 0) * count
        function["static_cost_with_linked_helpers"] = function["static_cost_local"] + helper_expansion
        function["helper_static_expansion"] = helper_expansion

    totals = {
        "function_count": len(functions),
        "instruction_count": sum(item["instructions"] for item in functions),
        "linked_code_bytes_by_function_symbols": sum(item["size"] for item in functions),
        "float_helper_call_sites": {},
        "double_helper_call_sites": {},
        "conversion_helper_call_sites": {},
    }
    for function in functions:
        for target, count in function["float_helpers"].items():
            totals["float_helper_call_sites"][target] = totals["float_helper_call_sites"].get(target, 0) + count
        for target, count in function["double_helpers"].items():
            totals["double_helper_call_sites"][target] = totals["double_helper_call_sites"].get(target, 0) + count
        for target, count in function["conversion_helpers"].items():
            totals["conversion_helper_call_sites"][target] = totals["conversion_helper_call_sites"].get(target, 0) + count

    return {
        "cost_label": "STATIC COST ESTIMATE",
        "cost_unit": "relative units, not cycles or time",
        "functions": functions,
        "instructions": instruction_rows,
        "totals": totals,
    }


def write_function_csv(path: Path, analysis: dict) -> None:
    fields = [
        "name", "source_object", "address", "size", "instructions", "stack_frame_bytes_derived",
        "loads", "stores", "branches", "calls_count", "multiply_instructions",
        "static_cost_local", "helper_static_expansion", "static_cost_with_linked_helpers",
        "float_helpers", "double_helpers", "conversion_helpers", "calls",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for item in analysis["functions"]:
            row = {field: item.get(field) for field in fields}
            row["address"] = f"0x{item['address']:08x}"
            for field in ("float_helpers", "double_helpers", "conversion_helpers", "calls"):
                row[field] = json.dumps(row[field], sort_keys=True)
            writer.writerow(row)


def call_edges(analysis: dict) -> list[dict]:
    known = {alias for item in analysis["functions"] for alias in item["aliases"]}
    edges = []
    for item in analysis["functions"]:
        for callee, sites in item["calls"].items():
            edges.append({"caller": item["name"], "callee": callee, "static_call_sites": sites, "linked_target": callee in known})
    return edges


def reachable_functions(analysis: dict, roots: list[str]) -> set[str]:
    aliases = {alias: item["name"] for item in analysis["functions"] for alias in item["aliases"]}
    calls = {item["name"]: list(item["calls"]) for item in analysis["functions"]}
    pending = [aliases[root] for root in roots if root in aliases]
    reached = set(pending)
    while pending:
        caller = pending.pop()
        for target in calls.get(caller, []):
            canonical = aliases.get(target)
            if canonical and canonical not in reached:
                reached.add(canonical)
                pending.append(canonical)
    return reached


def write_callgraph(path: Path, analysis: dict, roots: list[str]) -> set[str]:
    reached = reachable_functions(analysis, roots)
    lines = ["digraph linked_callgraph {", "  rankdir=LR;", '  label="Linked ArmClang call graph; edge labels are static BL sites";']
    for item in analysis["functions"]:
        if item["name"] in reached:
            lines.append(f'  "{item["name"]}" [label="{item["name"]}\\n{item["size"]} B"];')
    for edge in call_edges(analysis):
        if edge["caller"] in reached and edge["callee"] in reached:
            lines.append(f'  "{edge["caller"]}" -> "{edge["callee"]}" [label="{edge["static_call_sites"]}"];')
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return reached


def expected_loop_cost(analysis: dict) -> list[dict]:
    model = read_json(BENCHMARK / "flight_loop_model.json")
    lookup = {alias: item for item in analysis["functions"] for alias in item["aliases"]}
    rows = []
    for entry in model["entries"]:
        function = lookup.get(entry["function"])
        if not function:
            rows.append({**entry, "active_on_target": False})
            continue
        count = entry["executions_per_loop"]
        rows.append({
            **entry,
            "active_on_target": True,
            "rom_bytes": function["size"],
            "static_cost_per_invocation": function["static_cost_with_linked_helpers"],
            "expected_static_cost_per_loop": function["static_cost_with_linked_helpers"] * count,
            "float_helper_call_sites": function["float_helpers"],
            "expected_float_helper_calls_per_loop": {
                key: value * count for key, value in function["float_helpers"].items()
            },
        })
    return rows


def render_static_report(result_dir: Path, configuration: dict, memory: dict, analysis: dict, active: set[str]) -> None:
    expected = expected_loop_cost(analysis)
    write_json(result_dir / "expected_loop_cost.json", expected)
    ranked = sorted(
        [row for row in expected if row.get("active_on_target")],
        key=lambda row: row["expected_static_cost_per_loop"],
        reverse=True,
    )
    functions = {item["name"]: item for item in analysis["functions"]}
    compiler_records = read_json(result_dir / "compiler_flags.json")["commands"]
    control_command = next(
        item["arguments_as_recorded_by_uvision"] for item in compiler_records
        if item["source"].lower().endswith("control.c")
    )
    optimization_flag = next(
        (argument for argument in control_command.split() if re.fullmatch(r"-O(?:[0-3sz]|fast)", argument)),
        "not recorded",
    )
    fast_math = "enabled" if "-ffast-math" in control_command.split() else "disabled"
    lto = "enabled" if any("lto" in argument.lower() for argument in control_command.split()) else "disabled"
    hardware_text = (result_dir / "hardware.h").read_text(encoding="utf-8", errors="replace")
    i2c_speed_options = (
        ("HW_I2C_SPEED_FAST_OC", 1_000_000),
        ("HW_I2C_SPEED_FAST2", 1_000_000),
        ("HW_I2C_SPEED_FAST", 400_000),
        ("HW_I2C_SPEED_SLOW1", 200_000),
        ("HW_I2C_SPEED_SLOW2", 100_000),
    )
    i2c_hz = next(
        (frequency for define, frequency in i2c_speed_options
         if re.search(rf"^\s*#define\s+{define}\b", hardware_text, re.MULTILINE)),
        400_000,
    )
    i2c_theoretical_us = 153 * 1_000_000 / i2c_hz
    linker_options = " ".join(
        line.strip() for line in (result_dir / "linker_flags.lnp").read_text(encoding="utf-8", errors="replace").splitlines()
        if line.lstrip().startswith("--")
    )
    lines = [
        "# BWHOOP/Rajawali binary baseline",
        "",
        f"Generated from `{configuration['toolchain']}` for `{configuration['keil_target']}` / `{configuration['device']}`.",
        "",
        "All cost values below are **STATIC COST ESTIMATE** relative units. They are not cycles or physical time.",
        "",
        "## Exact target and build flags",
        "",
        "- Board: `BWHOOP` only",
        "- Receiver: `RX_BAYANG_PROTOCOL_TELEMETRY_AUTOBIND` with `USE_MULTI`; `RX_SBUS` is disabled",
        "- CPU: Cortex-M0 / ARMv6-M soft float; active firmware clock path is 48 MHz (`ENABLE_OVERCLOCK` disabled)",
        f"- Optimizer: ArmClang `{optimization_flag}`, fast-math {fast_math}, LTO {lto}",
        "- Exact per-file commands for every translation unit are saved in `compiler_flags.json` and raw `compiler_dependency.dep`",
        "",
        "Representative exact C command recorded by µVision for `control.c`:",
        "",
        "```text",
        control_command,
        "```",
        "",
        "Exact linker options from the generated response file:",
        "",
        "```text",
        linker_options,
        "```",
        "",
        "## Binary memory",
        "",
        f"- Flash/ROM: {memory.get('rom_bytes')} bytes (code {memory.get('code_bytes')}, RO data {memory.get('ro_data_bytes')}, RW initializers {memory.get('rw_data_bytes')})",
        f"- RAM: {memory.get('ram_bytes')} bytes (RW {memory.get('rw_data_bytes')}, ZI {memory.get('zi_data_bytes')})",
        f"- Linker regions: {memory.get('linker_flash_region_bytes')} bytes Flash and {memory.get('linker_ram_region_bytes')} bytes RAM",
        f"- Project device declaration: {memory.get('project_device_irom_bytes')} bytes IROM for {configuration['device']}",
        f"- Linked functions reachable from active loop roots: {len(active)}",
        "",
        f"The generated scatter file permits {memory.get('linker_flash_region_bytes'):,} Flash bytes and the compiler command defines `STM32F030x6`, while the µVision device/CPU declaration says `{configuration['device']}` with {memory.get('project_device_irom_bytes'):,} bytes IROM. The {memory.get('rom_bytes'):,}-byte image fits the linker region but exceeds the declared device IROM by {max(0, memory.get('rom_bytes') - memory.get('project_device_irom_bytes')):,} bytes. This configuration inconsistency must be resolved before physical flashing; the benchmark does not silently reinterpret it.",
        "",
        "## Top 10 expected dynamic CPU opportunities",
        "",
        "| Rank | Function | Expected calls/loop | ROM B | Static score/call | Expected score/loop | Expected float-helper calls/loop |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for rank, row in enumerate(ranked[:10], 1):
        helpers = ", ".join(f"{key}×{value}" for key, value in row["expected_float_helper_calls_per_loop"].items()) or "—"
        lines.append(
            f"| {rank} | `{row['function']}` | {row['executions_per_loop']} | {row['rom_bytes']} | "
            f"{row['static_cost_per_invocation']} | {row['expected_static_cost_per_loop']} | {helpers} |"
        )
    lines.extend([
        "",
        "Ranking combines linked function assembly, linked software-helper bodies, and the explicit expected-executions model. It is triage evidence, not hardware timing.",
        "",
        "## Linked active-path functions",
        "",
        "| Function | Object | ROM B | Instructions | Stack frame (derived) | BL sites | Loads | Stores | Branches |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name in sorted(active):
        item = functions[name]
        lines.append(
            f"| `{name}` | `{item.get('source_object') or 'Arm runtime'}` | {item['size']} | {item['instructions']} | "
            f"{item['stack_frame_bytes_derived']} | {item['calls_count']} | {item['loads']} | {item['stores']} | {item['branches']} |"
        )
    lines.extend([
        "",
        "## External peripheral timing (kept separate)",
        "",
        f"- MPU6050: 14 payload bytes, 17 wire bytes / 153 SCL clocks per loop. At the configured nominal {i2c_hz / 1_000_000:g} MHz this is {i2c_theoretical_us:g} µs theoretical bus time. The driver blocks in flag-poll loops; this wait is not included in CPU static scores.",
        "- XN297L: steady status polling performs two software-SPI bytes (16 bit iterations); packet and telemetry traffic are conditional. This GPIO work is reported separately from flight-math emulation.",
        "",
        "See `function_metrics.csv`, `static_analysis.json`, `callgraph.dot`, `expected_loop_cost.json`, and the saved AXF/map/disassembly for auditable evidence.",
    ])
    (result_dir / "baseline_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_active_callgraph(result_dir: Path, analysis: dict, active: set[str]) -> None:
    model = read_json(BENCHMARK / "flight_loop_model.json")
    trace = read_json(result_dir / "math_trace.json")
    roots = {entry["function"]: entry["executions_per_loop"] for entry in model["entries"]}
    lines = [
        "# Active BWHOOP/Rajawali flight-loop call graph",
        "",
        "This graph is extracted from direct `BL`/`BLX` instructions in the linked firmware AXF. Static call sites, expected per-loop invocations, and deterministic harness executions are separate columns; none is hardware timing.",
        "",
        "## Loop roots",
        "",
        "| Function | Linked in firmware | Expected executions/loop | Harness executions |",
        "|---|---|---:|---:|",
    ]
    linked_aliases = {alias for item in analysis["functions"] for alias in item["aliases"]}
    dynamic_entries = trace.get("function_entry_counts", {})
    for name, count in roots.items():
        linked = name in linked_aliases
        active_count = count if linked else 0
        lines.append(f"| `{name}` | {'yes' if linked else 'no'} | {active_count} | {dynamic_entries.get(name, 'not exercised')} |")
    lines.extend([
        "",
        "## Linked edges in the active closure",
        "",
        "| Caller | Callee | Static BL sites |",
        "|---|---|---:|",
    ])
    for edge in sorted(call_edges(analysis), key=lambda item: (item["caller"], item["callee"])):
        if edge["caller"] in active and edge["callee"] in active:
            lines.append(f"| `{edge['caller']}` | `{edge['callee']}` | {edge['static_call_sites']} |")
    lines.extend([
        "",
        "## Executed production-math edges",
        "",
        "| Caller | Callee | Dynamic calls in 2,048 iterations |",
        "|---|---|---:|",
    ])
    for edge in trace.get("dynamic_call_edges", []):
        if edge["caller"] in active and (edge["callee"] in active or edge["callee"].startswith("__aeabi_")):
            lines.append(f"| `{edge['caller']}` | `{edge['callee']}` | {edge['executions']} |")
    lines.extend([
        "",
        "Sensor acquisition and radio edges are present only in the linked-firmware graph. The deterministic harness intentionally replaces those peripherals and dynamically exercises the production filters, control, PID, mixer, and IMU path.",
    ])
    (result_dir / "active_callgraph.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_dynamic_report(result_dir: Path, analysis: dict) -> None:
    trace = read_json(result_dir / "math_trace.json")
    output = read_json(result_dir / "math_output.json")
    double_sites = analysis["totals"].get("double_helper_call_sites", {})
    production_names = ["lpffilter", "lpffilter2", "control", "pid", "pwm_set", "imu_calc", "Q_rsqrt"]
    lines = [
        "",
        "## Deterministic linked-math execution",
        "",
        f"- Iterations: {trace['iterations']}",
        f"- Executed ARM instruction trace: {trace['executed_arm_instructions']}",
        f"- **STATIC COST ESTIMATE**: {trace['relative_static_cost']} relative units ({trace['relative_static_cost_per_iteration']:.2f} per iteration)",
        f"- Maximum observed stack depth: {trace['maximum_observed_stack_depth_bytes']} bytes",
        f"- Accidental linked double-helper call sites: {double_sites or 'none'}",
        "",
        "| Production function | Dynamic entries | Entries/iteration |",
        "|---|---:|---:|",
    ]
    for name in production_names:
        count = trace.get("function_entry_counts", {}).get(name, 0)
        lines.append(f"| `{name}` | {count} | {count / trace['iterations']:.4f} |")
    lines.extend([
        "",
        "Runtime soft-float calls: " + ", ".join(
            f"`{name}` × {count}" for name, count in sorted(trace.get("runtime_helper_call_counts", {}).items())
        ) + ".",
        "",
        f"The output corpus contains {output['iterations']} × {output['floats_per_record']} production-state/output floats ({trace.get('nonfinite_output_values', 0)} non-finite) and is saved in binary and JSON form for ULP comparison.",
    ])
    with (result_dir / "baseline_report.md").open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def copy_evidence(result_dir: Path) -> None:
    copies = {
        OBJECTS / "nfe_silverware.axf": result_dir / "firmware.axf",
        OBJECTS / "nfe_silverware.hex": result_dir / "firmware.hex",
        LISTINGS / "nfe_silverware.map": result_dir / "firmware.map",
        OBJECTS / "nfe_silverware.lnp": result_dir / "linker_flags.lnp",
        OBJECTS / "nfe_silverware.sct": result_dir / "firmware_scatter.sct",
        OBJECTS / "nfe_silverware.build_log.htm": result_dir / "uvision_build_log.htm",
        OBJECTS / "silverware_NFE_Silverware.dep": result_dir / "compiler_dependency.dep",
        PROJECT: result_dir / "Silverware.uvprojx",
        PROJECT_DIR / "src" / "config.h": result_dir / "config.h",
        PROJECT_DIR / "src" / "targets.h": result_dir / "targets.h",
        PROJECT_DIR / "src" / "hardware.h": result_dir / "hardware.h",
    }
    for source, target in copies.items():
        if not source.is_file():
            raise RuntimeError(f"Expected build artifact was not generated: {source}")
        shutil.copy2(source, target)


def build_firmware(result_dir: Path, tools: dict[str, Path]) -> None:
    uv_log = result_dir / "uvision_console.log"
    # -r is a full rebuild. The timestamp check prevents silently analyzing an old AXF.
    before = (OBJECTS / "nfe_silverware.axf").stat().st_mtime if (OBJECTS / "nfe_silverware.axf").exists() else 0
    # uVision returns 1 when a successful build contains warnings; the build
    # log below is the authoritative success/error check.
    run(
        [str(tools["uv4"]), "-r", str(PROJECT), "-t", TARGET, "-j0", "-o", str(uv_log)],
        ROOT,
        result_dir / "uvision_invocation.log",
        ok_codes=(0, 1),
    )
    axf = OBJECTS / "nfe_silverware.axf"
    if not axf.is_file() or axf.stat().st_mtime < before:
        raise RuntimeError(f"uVision did not refresh {axf}; inspect {uv_log}")
    build_text = (OBJECTS / "nfe_silverware.build_log.htm").read_text(encoding="utf-8", errors="replace")
    if "0 Error(s)" not in build_text:
        raise RuntimeError("uVision build did not report zero errors")
    copy_evidence(result_dir)
    run(
        [str(tools["fromelf"]), "--text", "-c", "-s", "-z", "--output", str(result_dir / "firmware.disassembly.txt"), str(result_dir / "firmware.axf")],
        ROOT,
        result_dir / "fromelf_firmware.log",
    )


def compile_math_harness(result_dir: Path, tools: dict[str, Path]) -> None:
    harness_obj = result_dir / "flight_math_harness.o"
    compiler_records = read_json(result_dir / "compiler_flags.json")["commands"]
    reference_command = next(
        item["arguments_as_recorded_by_uvision"] for item in compiler_records
        if item["source"].lower().endswith("control.c")
    )
    recorded_tokens = reference_command.split()
    optimization_flag = next(
        (token for token in recorded_tokens if re.fullmatch(r"-O(?:0|1|2|3|s|z|fast)", token)),
        "-O1",
    )
    floating_point_flags = [
        token for token in recorded_tokens
        if token in {
            "-ffast-math", "-fno-fast-math", "-ffinite-math-only", "-fno-finite-math-only",
            "-fno-signed-zeros", "-fsigned-zeros", "-freciprocal-math", "-fno-reciprocal-math",
        }
    ]
    compile_args = [
        str(tools["armclang"]), "-xc", "-std=c99", "--target=arm-arm-none-eabi", "-mcpu=cortex-m0", "-c",
        "-fno-rtti", "-funsigned-char", "-fshort-enums", "-fshort-wchar", "-D__MICROLIB", "-gdwarf-4", optimization_flag,
        *floating_point_flags,
        "-ffunction-sections", "-Wall", "-Wextra", "-Wno-packed", "-Wno-reserved-id-macro", "-Wno-unused-macros",
        "-Wno-documentation-unknown-command", "-Wno-documentation", "-Wno-license-management", "-Wno-parentheses-equality",
        "-Wno-reserved-identifier", "-I", "./src", "-I", "../Libraries/STM32F0xx_StdPeriph_Driver/inc",
        "-I", "../Libraries/CMSIS/Include", "-I", "../", "-I", "../Libraries/CMSIS/Device/ST/STM32F0xx/Include",
        "-I", "../Utilities/", '-D__UVISION_VERSION="543"', "-DSTM32F030x6", "-DUSE_STDPERIPH_DRIVER", "-DSTM32F031",
        str(BENCHMARK / "harness" / "flight_math_harness.c"), "-o", str(harness_obj),
    ]
    run(compile_args, PROJECT_DIR, result_dir / "harness_compile.log")

    axf = result_dir / "flight_math.axf"
    map_path = result_dir / "flight_math.map"
    link_args = [
        str(tools["armlink"]), "--cpu", "Cortex-M0", "--library_type=microlib", "--strict", "--remove",
        "--entry", "benchmark_entry", "--scatter", str(BENCHMARK / "harness" / "math_harness.sct"),
        "--map", "--symbols", "--xref", "--callgraph", "--info", "sizes", "--info", "totals", "--info", "unused",
        "--list", str(map_path), "-o", str(axf), str(harness_obj),
    ] + [str(OBJECTS / name) for name in PRODUCTION_MATH_OBJECTS]
    run(link_args, ROOT, result_dir / "harness_link.log")
    run(
        [str(tools["fromelf"]), "--text", "-c", "-s", "-z", "--output", str(result_dir / "flight_math.disassembly.txt"), str(axf)],
        ROOT,
        result_dir / "fromelf_harness.log",
    )


def prepare_result_directory(label: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", label):
        raise ValueError("Label must contain only letters, digits, dot, underscore, or dash")
    RESULTS.mkdir(parents=True, exist_ok=True)
    result_dir = (RESULTS / label).resolve()
    if result_dir.parent != RESULTS.resolve():
        raise ValueError("Result label escapes benchmark/results")
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir()
    return result_dir


def create_snapshot(label: str) -> Path:
    result_dir = prepare_result_directory(label)
    configuration = capture_target_configuration()
    tools = locate_tools()
    write_json(result_dir / "target_configuration.json", configuration)
    write_json(result_dir / "toolchain.json", tool_versions(tools))

    build_firmware(result_dir, tools)
    commands = parse_compiler_commands(result_dir / "compiler_dependency.dep")
    write_json(result_dir / "compiler_flags.json", {
        "source_of_truth": "uVision-generated dependency file saved as compiler_dependency.dep",
        "commands": commands,
        "linker_response_file": "linker_flags.lnp",
    })
    memory = parse_memory(result_dir / "firmware.map")
    write_json(result_dir / "memory.json", memory)

    analysis = analyze_disassembly(result_dir / "firmware.disassembly.txt", result_dir / "firmware.map", BENCHMARK / "cost_model.json")
    write_json(result_dir / "static_analysis.json", {key: value for key, value in analysis.items() if key != "instructions"})
    write_json(result_dir / "instructions.json", analysis["instructions"])
    write_function_csv(result_dir / "function_metrics.csv", analysis)
    write_json(result_dir / "callgraph.json", call_edges(analysis))
    model_roots = [entry["function"] for entry in read_json(BENCHMARK / "flight_loop_model.json")["entries"]]
    active = write_callgraph(result_dir / "callgraph.dot", analysis, model_roots)
    write_json(result_dir / "active_functions.json", sorted(active))
    render_static_report(result_dir, configuration, memory, analysis, active)

    compile_math_harness(result_dir, tools)
    harness_analysis = analyze_disassembly(result_dir / "flight_math.disassembly.txt", result_dir / "flight_math.map", BENCHMARK / "cost_model.json")
    write_json(result_dir / "flight_math_static_analysis.json", {key: value for key, value in harness_analysis.items() if key != "instructions"})
    write_json(result_dir / "flight_math_instructions.json", harness_analysis["instructions"])

    from .run_elf import execute_math_elf
    execute_math_elf(result_dir)
    render_active_callgraph(result_dir, analysis, active)
    append_dynamic_report(result_dir, analysis)

    metadata = {
        "label": label,
        "created_unix": int(time.time()),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True).stdout.strip(),
        "git_dirty": bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True).stdout.strip()),
        "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in result_dir.iterdir() if path.is_file()},
    }
    write_json(result_dir / "metadata.json", metadata)
    return result_dir


def ordered_float_int(value: float) -> int:
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    return 0x80000000 - bits if bits & 0x80000000 else bits + 0x80000000


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _xorshift32(state: int) -> int:
    state ^= (state << 13) & 0xffffffff
    state ^= state >> 17
    state ^= (state << 5) & 0xffffffff
    return state & 0xffffffff


def _signed_unit(state: int) -> tuple[int, float]:
    state = _xorshift32(state)
    value = state & 0xffff
    return state, _float32(_float32(float(value) - 32768.0) * _float32(1.0 / 32768.0))


def deterministic_benchmark_input(iteration: int) -> dict:
    """Replay the fixed flight-math PRNG through one requested iteration."""
    if iteration < 0:
        raise ValueError("iteration must be non-negative")
    state = 0x13579bdf
    result = {}
    for current in range(iteration + 1):
        state, roll_unit = _signed_unit(state)
        state, pitch_unit = _signed_unit(state)
        state, yaw_unit = _signed_unit(state)
        roll = _float32(roll_unit * _float32(0.85))
        pitch = _float32(pitch_unit * _float32(0.85))
        yaw = _float32(yaw_unit * _float32(0.70))

        state = _xorshift32(state)
        throttle_scale = _float32(0.75 / 65535.0)
        throttle = _float32(_float32(0.15) + _float32(float(state & 0xffff) * throttle_scale))

        gyro_samples = []
        for stimulus in (roll, pitch, yaw):
            state, noise_unit = _signed_unit(state)
            noise = _float32(noise_unit * _float32(0.08))
            gyro_samples.append(_float32(_float32(stimulus * _float32(5.0)) + noise))

        state, accel_x_unit = _signed_unit(state)
        state, accel_y_unit = _signed_unit(state)
        state, accel_z_unit = _signed_unit(state)
        accel_samples = [
            _float32(_float32(roll * _float32(368.0)) + _float32(accel_x_unit * _float32(30.0))),
            _float32(_float32(pitch * _float32(368.0)) + _float32(accel_y_unit * _float32(30.0))),
            _float32(_float32(2048.0) + _float32(accel_z_unit * _float32(52.0))),
        ]
        if current == iteration:
            phase = (current // 256) & 3
            result = {
                "iteration": current,
                "mode": phase,
                "pid_profile": (current // 512) & 1,
                "rx": [roll, pitch, yaw, throttle],
                "gyro_sample": gyro_samples,
                "accel_sample": accel_samples,
            }
    return result


def _difference_location(
    iteration: int,
    field: int,
    left: float,
    right: float,
    field_order: list[str],
) -> dict:
    return {
        "iteration": iteration,
        "field": field,
        "field_name": field_order[field] if field < len(field_order) else f"field_{field}",
        "baseline": left,
        "candidate": right,
        "deterministic_input": deterministic_benchmark_input(iteration),
    }


def compare_float_outputs(baseline: dict, candidate: dict) -> dict:
    base = baseline["records"]
    cand = candidate["records"]
    if len(base) != len(cand):
        return {"shape_mismatch": True, "baseline_records": len(base), "candidate_records": len(cand)}
    max_abs = 0.0
    max_rel = 0.0
    max_ulp = 0
    bitwise_mismatches = 0
    finite_mismatches = 0
    field_order = baseline.get("field_order", [])
    worst_absolute = None
    worst_relative = None
    worst_ulp = None
    for iteration, (base_record, cand_record) in enumerate(zip(base, cand)):
        if len(base_record) != len(cand_record):
            return {"shape_mismatch": True, "iteration": iteration}
        for field, (left, right) in enumerate(zip(base_record, cand_record)):
            left_bits = struct.unpack("<I", struct.pack("<f", left))[0]
            right_bits = struct.unpack("<I", struct.pack("<f", right))[0]
            if left_bits != right_bits:
                bitwise_mismatches += 1
            if left != left or right != right:
                finite_mismatches += 1
                continue
            absolute = abs(left - right)
            relative = absolute / max(abs(left), 1.0e-30)
            ulp = abs(ordered_float_int(left) - ordered_float_int(right))
            if absolute > max_abs:
                max_abs = absolute
                worst_absolute = _difference_location(iteration, field, left, right, field_order)
            if relative > max_rel:
                max_rel = relative
                worst_relative = _difference_location(iteration, field, left, right, field_order)
            if ulp > max_ulp:
                max_ulp = ulp
                worst_ulp = _difference_location(iteration, field, left, right, field_order)
    return {
        "shape_mismatch": False,
        "max_absolute_float_error": max_abs,
        "max_relative_error": max_rel,
        "max_ulp_difference": max_ulp,
        "bitwise_output_mismatches": bitwise_mismatches,
        "nonfinite_mismatches": finite_mismatches,
        "worst_absolute_location": worst_absolute,
        "worst_relative_location": worst_relative,
        "worst_ulp_location": worst_ulp,
    }
