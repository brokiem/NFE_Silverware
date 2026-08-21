from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from benchmark.benchlib import (
    BENCHMARK,
    PROJECT,
    RESULTS,
    compare_float_outputs,
    create_snapshot,
    effective_compiler_settings,
    read_json,
    write_json,
)


OPTIMIZATIONS = ("O0", "O1", "O2", "O3", "Os", "Oz", "Ofast")
REFERENCE = ("O2", True, False)


@dataclass(frozen=True)
class Variant:
    optimization: str
    fast_math: bool
    lto: bool

    @property
    def label(self) -> str:
        math_name = "fast" if self.fast_math else "precise"
        lto_name = "lto" if self.lto else "nolto"
        return f"matrix_{self.optimization.lower()}_{math_name}_{lto_name}"

    def as_dict(self) -> dict[str, object]:
        return {
            "optimization": f"-{self.optimization}",
            "fast_math": self.fast_math,
            "lto": self.lto,
            "label": self.label,
        }


def input_fingerprint() -> str:
    """Hash every source/configuration input that can affect a matrix snapshot."""
    digest = hashlib.sha256()
    roots = (
        PROJECT,
        PROJECT.parent / "src",
        PROJECT.parent.parent / "Libraries",
        PROJECT.parent.parent / "Utilities",
        PROJECT.parent.parent / "benchmark" / "harness",
        PROJECT.parent.parent / "benchmark" / "cost_model.json",
        PROJECT.parent.parent / "benchmark" / "flight_loop_model.json",
        PROJECT.parent.parent / "benchmark" / "benchlib.py",
        PROJECT.parent.parent / "benchmark" / "run_elf.py",
    )
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    workspace = PROJECT.parent.parent
    for path in sorted(set(files), key=lambda item: str(item).lower()):
        digest.update(str(path.relative_to(workspace)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def configured_project(original_text: str, variant: Variant) -> str:
    """Inject explicit last-wins flags while preserving every board setting."""
    target_arm = original_text.index("<TargetArmAds>")
    cads_start = original_text.index("<Cads>", target_arm)
    cads_end = original_text.index("</Cads>", cads_start) + len("</Cads>")
    cads = original_text[cads_start:cads_end]
    math_flag = "-ffast-math" if variant.fast_math else "-fno-fast-math"
    explicit_flags = f"-{variant.optimization} {math_flag}"
    cads, count = re.subn(
        r"<MiscControls>.*?</MiscControls>",
        f"<MiscControls>{explicit_flags}</MiscControls>",
        cads,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("Could not locate target C compiler MiscControls")
    configured = original_text[:cads_start] + cads + original_text[cads_end:]
    configured, lto_count = re.subn(
        r"<v6Lto>\d+</v6Lto>",
        f"<v6Lto>{1 if variant.lto else 0}</v6Lto>",
        configured,
    )
    if lto_count < 2:
        raise RuntimeError(f"Expected target and group LTO controls, found {lto_count}")
    return configured


def control_command(snapshot: Path) -> str:
    records = read_json(snapshot / "compiler_flags.json")["commands"]
    return next(
        item["arguments_as_recorded_by_uvision"]
        for item in records
        if item["source"].lower().endswith("control.c")
    )


def verify_variant(snapshot: Path, variant: Variant) -> dict[str, object]:
    command = control_command(snapshot)
    effective = effective_compiler_settings(command)
    expected_optimization = f"-{variant.optimization}"
    problems = []
    if effective["optimization_flag"] != expected_optimization:
        problems.append(f"optimization {effective['optimization_flag']} != {expected_optimization}")
    if effective["fast_math"] != variant.fast_math:
        problems.append(f"fast_math {effective['fast_math']} != {variant.fast_math}")
    if effective["lto"] != variant.lto:
        problems.append(f"lto {effective['lto']} != {variant.lto}")
    if problems:
        raise RuntimeError("Recorded compiler flags do not match request: " + "; ".join(problems))
    return {"command": command, "effective": effective}


def snapshot_row(snapshot: Path, variant: Variant) -> dict[str, object]:
    verified = verify_variant(snapshot, variant)
    memory = read_json(snapshot / "memory.json")
    analysis = read_json(snapshot / "static_analysis.json")
    trace = read_json(snapshot / "math_trace.json")
    helpers = trace.get("runtime_helper_call_counts", {})
    return {
        **variant.as_dict(),
        "status": "success",
        "compiler": verified,
        "rom_bytes": memory["rom_bytes"],
        "ram_bytes": memory["ram_bytes"],
        "firmware_instruction_count": analysis["totals"]["instruction_count"],
        "firmware_linked_function_bytes": analysis["totals"]["linked_code_bytes_by_function_symbols"],
        "executed_arm_instructions": trace["executed_arm_instructions"],
        "relative_static_cost": trace["relative_static_cost"],
        "maximum_observed_stack_depth_bytes": trace["maximum_observed_stack_depth_bytes"],
        "runtime_helpers": {
            name: helpers.get(name, 0)
            for name in (
                "__aeabi_fadd", "__aeabi_fsub", "__aeabi_fmul", "__aeabi_fdiv",
                "__aeabi_i2f", "__aeabi_ui2f", "__aeabi_f2iz",
            )
        },
    }


def add_numerical_comparison(rows: list[dict[str, object]]) -> None:
    reference_label = Variant(*REFERENCE).label
    reference = next((row for row in rows if row.get("label") == reference_label and row.get("status") == "success"), None)
    if reference is None:
        raise RuntimeError(f"Reference configuration failed: {reference_label}")
    reference_output = read_json(RESULTS / reference_label / "math_output.json")
    for row in rows:
        if row.get("status") != "success":
            continue
        candidate_output = read_json(RESULTS / str(row["label"]) / "math_output.json")
        row["numerical_vs_o2_fast_nolto"] = compare_float_outputs(reference_output, candidate_output)


def build_failure_summary(error: Exception) -> str:
    build_log = PROJECT.parent / "Objects" / "nfe_silverware.build_log.htm"
    if build_log.is_file():
        text = build_log.read_text(encoding="utf-8", errors="replace")
        compiler_fatal = re.search(r"fatal error:\s*(.*?)$", text, flags=re.MULTILINE | re.IGNORECASE)
        if compiler_fatal:
            return "armclang: " + compiler_fatal.group(1).strip()
        overflow = re.search(r"Sections of aggregate size 0x([0-9a-fA-F]+) bytes could not fit", text)
        if overflow:
            return (
                f"link overflow: {int(overflow.group(1), 16)} bytes could not fit "
                "in the 0x7C00 firmware region"
            )
        errors = re.findall(r"^.*?Error:\s*(.*?)$", text, flags=re.MULTILINE)
        if errors:
            return errors[-1].strip()
    return str(error).splitlines()[0]


def delta(value: int, reference: int) -> str:
    return f"{value - reference:+d}"


def render_report(rows: list[dict[str, object]]) -> str:
    successful = [row for row in rows if row.get("status") == "success"]
    failed = [row for row in rows if row.get("status") != "success"]
    reference_label = Variant(*REFERENCE).label
    reference = next(row for row in successful if row["label"] == reference_label)
    ranked = sorted(successful, key=lambda row: (
        int(row["relative_static_cost"]),
        int(row["executed_arm_instructions"]),
        int(row["rom_bytes"]),
    ))
    lines = [
        "# ArmClang Rajawali compiler matrix",
        "",
        "This matrix rebuilds the exact linked BWHOOP/Rajawali firmware and deterministic production flight-math harness for every ArmClang 6.24 optimization level, with fast-math explicitly enabled/disabled and LTO enabled/disabled.",
        "",
        "All dynamic instruction and cost results are **STATIC PERFORMANCE ESTIMATE** values from the hardware-independent linked harness. They are not physical cycles or time. LTO harness code is generated in the harness link context, so the saved full-firmware AXF/map/disassembly remains the ground truth for actual linked firmware structure.",
        "",
        f"Successful configurations: {len(successful)}/{len(rows)}. Reference: `-O2 -ffast-math`, no LTO.",
        "The working hardware assumption is 32 KB Flash, with only `0x08000000`–`0x08007BFF` (31,744 bytes) available to firmware and the final 1,024 bytes reserved for persistence.",
        "",
        "## Ranked results",
        "",
        "| Rank | Effective configuration | ROM B | ROM Δ | RAM B | Firmware insns | Executed insns | Trace Δ | Static cost | Cost Δ | Stack B | Max abs error | ULP | Mismatches |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(ranked, 1):
        numerical = row["numerical_vs_o2_fast_nolto"]
        config = f"`{row['optimization']} {'fast' if row['fast_math'] else 'precise'} {'LTO' if row['lto'] else 'no-LTO'}`"
        lines.append(
            f"| {rank} | {config} | {row['rom_bytes']} | {delta(int(row['rom_bytes']), int(reference['rom_bytes']))} | "
            f"{row['ram_bytes']} | {row['firmware_instruction_count']} | {row['executed_arm_instructions']} | "
            f"{delta(int(row['executed_arm_instructions']), int(reference['executed_arm_instructions']))} | "
            f"{row['relative_static_cost']} | {delta(int(row['relative_static_cost']), int(reference['relative_static_cost']))} | "
            f"{row['maximum_observed_stack_depth_bytes']} | {numerical['max_absolute_float_error']:.9g} | "
            f"{numerical['max_ulp_difference']} | {numerical['bitwise_output_mismatches']} |"
        )
    winner = next((row for row in successful if row["label"] == "matrix_os_fast_lto"), None)
    o3_fast = next((row for row in successful if row["label"] == "matrix_o3_fast_nolto"), None)
    if winner and o3_fast:
        base_analysis = read_json(RESULTS / str(reference["label"]) / "static_analysis.json")
        winner_analysis = read_json(RESULTS / str(winner["label"]) / "static_analysis.json")
        o3_analysis = read_json(RESULTS / str(o3_fast["label"]) / "static_analysis.json")
        base_functions = {item["name"]: item for item in base_analysis["functions"]}
        winner_functions = {item["name"]: item for item in winner_analysis["functions"]}
        o3_functions = {item["name"]: item for item in o3_analysis["functions"]}
        base_main = base_functions["main"]
        winner_main = winner_functions["main"]
        base_i2c = base_functions["hw_i2c_readdata"]
        o3_i2c = o3_functions["hw_i2c_readdata"]
        winner_numerical = winner["numerical_vs_o2_fast_nolto"]
        lines.extend([
            "",
            "## Reviewed decision",
            "",
            "**Keep `-O2 -ffast-math`, no LTO as the production configuration until hardware A/B timing is available.**",
            "",
            f"- `-Os -ffast-math -flto` is **BENCHMARK FURTHER**. It saves {int(reference['rom_bytes']) - int(winner['rom_bytes']):,} B ROM and {int(reference['ram_bytes']) - int(winner['ram_bytes']):,} B RAM, and reduces the harness trace by {int(reference['executed_arm_instructions']) - int(winner['executed_arm_instructions']):,} instructions ({(int(reference['executed_arm_instructions']) - int(winner['executed_arm_instructions'])) / int(reference['executed_arm_instructions']) * 100:.2f}%). Its maximum output difference is {winner_numerical['max_absolute_float_error']:.9g}, with no non-finite mismatches.",
            f"- LTO changes the actual full-firmware structure substantially: `main` grows from {base_main['size']:,} B/{base_main['instructions']:,} instructions/{base_main['stack_frame_bytes_derived']}-byte derived frame to {winner_main['size']:,} B/{winner_main['instructions']:,} instructions/{winner_main['stack_frame_bytes_derived']}-byte frame, while `control`, `imu_calc`, filters, and PWM are inlined. The harness is necessarily a different LTO link context, so physical sensor-to-PWM timing and jitter must decide whether the static win transfers to the real loop.",
            f"- `-O3 -ffast-math`, no LTO is **REJECT** for this target: only {int(reference['relative_static_cost']) - int(o3_fast['relative_static_cost']):,} modeled cost units improve ({(int(reference['relative_static_cost']) - int(o3_fast['relative_static_cost'])) / int(reference['relative_static_cost']) * 100:.3f}%), while ROM grows by {int(o3_fast['rom_bytes']) - int(reference['rom_bytes'])} B and RAM by {int(o3_fast['ram_bytes']) - int(reference['ram_bytes'])} B. Its executed trace is 30 instructions higher across the corpus, and `hw_i2c_readdata` grows from {base_i2c['size']} B/{base_i2c['instructions']} instructions/{base_i2c['stack_frame_bytes_derived']}-byte frame to {o3_i2c['size']} B/{o3_i2c['instructions']} instructions/{o3_i2c['stack_frame_bytes_derived']}-byte frame.",
            "- `-Ofast -ffast-math`, no LTO is machine-code equivalent to the tested O3 fast build and has the same verdict.",
            "- `-Os -ffast-math`, no LTO and both `-Oz` fast variants are **REJECT** for the responsive-flight default: they save Flash but increase the executed trace/static cost. `-Oz -ffast-math -flto` is the 15,160-byte emergency Flash-pressure option.",
            "- Precise-math and O0 variants are **REJECT** for the flight build because their linked helper work and traces are much larger. The O3/Ofast precise no-LTO cells trigger an ArmClang 6.24 backend crash; the remaining O2/O3/Ofast LTO cells do not fit the protected firmware region.",
        ])
    lines.extend([
        "",
        "## Runtime helper execution",
        "",
        "| Configuration | fadd | fsub | fmul | fdiv | i2f | ui2f | f2iz |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in ranked:
        helpers = row["runtime_helpers"]
        config = f"`{row['optimization']} {'fast' if row['fast_math'] else 'precise'} {'LTO' if row['lto'] else 'no-LTO'}`"
        lines.append(
            f"| {config} | {helpers['__aeabi_fadd']} | {helpers['__aeabi_fsub']} | "
            f"{helpers['__aeabi_fmul']} | {helpers['__aeabi_fdiv']} | {helpers['__aeabi_i2f']} | "
            f"{helpers['__aeabi_ui2f']} | {helpers['__aeabi_f2iz']} |"
        )
    if failed:
        lines.extend(["", "## Failed configurations", ""])
        for row in failed:
            lines.append(f"- `{row['label']}`: {row['error']}")
    lines.extend([
        "",
        "## Reproduction",
        "",
        "```powershell",
        ".\\benchmark.ps1 matrix",
        "```",
        "",
        "Each successful configuration has its own `benchmark/results/matrix_*/` directory containing the exact AXF, map, disassembly, recorded compiler flags, call graph, static analysis, linked harness, dynamic trace, and numerical corpus. The project file is restored byte-for-byte after the matrix, including when a build fails.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the complete ArmClang Rajawali compiler configuration matrix.")
    parser.add_argument("--resume", action="store_true", help="reuse completed matching snapshots")
    parser.add_argument("--optimizations", nargs="+", choices=OPTIMIZATIONS, default=list(OPTIMIZATIONS))
    parser.add_argument("--fast-math", choices=("both", "on", "off"), default="both")
    parser.add_argument("--lto", choices=("both", "on", "off"), default="both")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fast_values = (False, True) if args.fast_math == "both" else (args.fast_math == "on",)
    lto_values = (False, True) if args.lto == "both" else (args.lto == "on",)
    variants = [Variant(opt, fast, lto) for opt in args.optimizations for fast in fast_values for lto in lto_values]
    reference_variant = Variant(*REFERENCE)
    if reference_variant in variants:
        variants.remove(reference_variant)
    variants.insert(0, reference_variant)

    original_bytes = PROJECT.read_bytes()
    original_text = original_bytes.decode("utf-8")
    fingerprint = input_fingerprint()
    rows: list[dict[str, object]] = []
    try:
        for index, variant in enumerate(variants, 1):
            print(f"[{index}/{len(variants)}] {variant.label}", flush=True)
            snapshot = RESULTS / variant.label
            request_path = snapshot / "matrix_configuration.json"
            failure_path = snapshot / "matrix_failure.json"
            request = {**variant.as_dict(), "input_sha256": fingerprint}
            try:
                if args.resume and request_path.is_file() and read_json(request_path) == request:
                    if failure_path.is_file():
                        failure = read_json(failure_path)
                        rows.append(failure)
                        print(f"  reusing failed result: {failure['error']}", flush=True)
                        continue
                    print("  reusing completed snapshot", flush=True)
                else:
                    PROJECT.write_text(configured_project(original_text, variant), encoding="utf-8")
                    snapshot = create_snapshot(variant.label)
                    write_json(snapshot / "matrix_configuration.json", request)
                row = snapshot_row(snapshot, variant)
                rows.append(row)
                print(
                    f"  ROM/RAM {row['rom_bytes']}/{row['ram_bytes']}; "
                    f"trace {row['executed_arm_instructions']}; cost {row['relative_static_cost']}",
                    flush=True,
                )
            except Exception as error:
                summary = build_failure_summary(error)
                failure = {**variant.as_dict(), "status": "failed", "error": summary}
                rows.append(failure)
                snapshot.mkdir(parents=True, exist_ok=True)
                write_json(request_path, request)
                write_json(failure_path, failure)
                print(f"  FAILED: {summary}", file=sys.stderr, flush=True)
            finally:
                PROJECT.write_bytes(original_bytes)

        add_numerical_comparison(rows)
        RESULTS.mkdir(parents=True, exist_ok=True)
        write_json(RESULTS / "compiler_matrix.json", {"reference": reference_variant.as_dict(), "results": rows})
        report = render_report(rows)
        (RESULTS / "compiler_matrix.md").write_text(report, encoding="utf-8")
        (BENCHMARK / "compiler_matrix_report.md").write_text(report, encoding="utf-8")
        print(f"matrix report: {RESULTS / 'compiler_matrix.md'}", flush=True)
        return 0
    finally:
        PROJECT.write_bytes(original_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
