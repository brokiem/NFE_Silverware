from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

from benchmark.benchlib import RESULTS, compare_float_outputs, read_json, write_json


def _snapshot(label: str) -> Path:
    path = (RESULTS / label).resolve()
    if path.parent != RESULTS.resolve() or not path.is_dir():
        raise ValueError(f"snapshot does not exist: {label}")
    return path


def _functions(analysis: dict) -> dict[str, dict]:
    result = {}
    for function in analysis["functions"]:
        result[function["name"]] = function
        for alias in function.get("aliases", []):
            result.setdefault(alias, function)
    return result


def _helper_count(trace: dict, function: str) -> int:
    return sum(trace.get("runtime_helper_calls_by_function", {}).get(function, {}).values())


def _function_assembly(disassembly: Path, function: dict | None) -> list[str]:
    if not function:
        return []
    start = function["address"]
    end = start + function["size"]
    rows = []
    pattern = re.compile(r"^\s*0x([0-9a-fA-F]+):\s+([0-9a-fA-F]{4,8})\s+.{0,8}?\s{2,}(.*?)\s*$")
    for line in disassembly.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        address = int(match.group(1), 16)
        if start <= address < end:
            rows.append(f"+0x{address - start:04x}  {match.group(2)}  {match.group(3)}")
    return rows


def _verdict(numerical: dict, rom_delta: int, ram_delta: int, cost_delta: int, instruction_delta: int) -> str:
    if numerical.get("shape_mismatch") or numerical.get("nonfinite_mismatches", 0):
        return "REJECT"
    if numerical.get("bitwise_output_mismatches", 0):
        return "BENCHMARK FURTHER"
    if cost_delta < 0 or instruction_delta < 0 or rom_delta < 0 or ram_delta < 0:
        if cost_delta <= 0 and rom_delta <= 0 and ram_delta <= 0:
            return "MERGE"
        return "BENCHMARK FURTHER"
    if cost_delta == 0 and instruction_delta == 0 and rom_delta == 0 and ram_delta == 0:
        return "IRRELEVANT TO TARGET"
    return "REJECT"


def compare(baseline_label: str, candidate_label: str) -> Path:
    baseline_dir = _snapshot(baseline_label)
    candidate_dir = _snapshot(candidate_label)
    base_memory = read_json(baseline_dir / "memory.json")
    cand_memory = read_json(candidate_dir / "memory.json")
    base_analysis = read_json(baseline_dir / "static_analysis.json")
    cand_analysis = read_json(candidate_dir / "static_analysis.json")
    base_trace = read_json(baseline_dir / "math_trace.json")
    cand_trace = read_json(candidate_dir / "math_trace.json")
    numerical = compare_float_outputs(
        read_json(baseline_dir / "math_output.json"),
        read_json(candidate_dir / "math_output.json"),
    )

    base_functions = _functions(base_analysis)
    cand_functions = _functions(cand_analysis)
    canonical_names = sorted(
        set(function["name"] for function in base_analysis["functions"])
        | set(function["name"] for function in cand_analysis["functions"])
    )
    changes = []
    for name in canonical_names:
        before = base_functions.get(name)
        after = cand_functions.get(name)
        row = {
            "function": name,
            "source_object_before": before.get("source_object") if before else None,
            "source_object_after": after.get("source_object") if after else None,
            "rom_before": before["size"] if before else 0,
            "rom_after": after["size"] if after else 0,
            "instructions_before": before["instructions"] if before else 0,
            "instructions_after": after["instructions"] if after else 0,
            "static_cost_before": before["static_cost_with_linked_helpers"] if before else 0,
            "static_cost_after": after["static_cost_with_linked_helpers"] if after else 0,
            "dynamic_helper_calls_before": _helper_count(base_trace, name),
            "dynamic_helper_calls_after": _helper_count(cand_trace, name),
        }
        if any(row[left] != row[right] for left, right in (
            ("rom_before", "rom_after"),
            ("instructions_before", "instructions_after"),
            ("static_cost_before", "static_cost_after"),
            ("dynamic_helper_calls_before", "dynamic_helper_calls_after"),
        )):
            changes.append(row)

    rom_delta = cand_memory["rom_bytes"] - base_memory["rom_bytes"]
    ram_delta = cand_memory["ram_bytes"] - base_memory["ram_bytes"]
    dynamic_cost_delta = cand_trace["relative_static_cost"] - base_trace["relative_static_cost"]
    dynamic_instruction_delta = cand_trace["executed_arm_instructions"] - base_trace["executed_arm_instructions"]
    verdict = _verdict(numerical, rom_delta, ram_delta, dynamic_cost_delta, dynamic_instruction_delta)
    comparison = {
        "baseline": baseline_label,
        "candidate": candidate_label,
        "cost_label": "STATIC COST ESTIMATE",
        "rom": {"before": base_memory["rom_bytes"], "after": cand_memory["rom_bytes"], "delta": rom_delta},
        "ram": {"before": base_memory["ram_bytes"], "after": cand_memory["ram_bytes"], "delta": ram_delta},
        "executed_instruction_trace": {
            "before": base_trace["executed_arm_instructions"],
            "after": cand_trace["executed_arm_instructions"],
            "delta": dynamic_instruction_delta,
        },
        "estimated_static_cost": {
            "before": base_trace["relative_static_cost"],
            "after": cand_trace["relative_static_cost"],
            "delta": dynamic_cost_delta,
        },
        "numerical_regression": numerical,
        "function_changes": changes,
        "verdict": verdict,
        "verdict_note": "Automatic verdict is conservative; explicitly classify intentional algorithm changes as ALGORITHM CHANGE during review.",
    }
    output_json = candidate_dir / f"comparison_vs_{baseline_label}.json"
    write_json(output_json, comparison)

    assembly_diff_path = candidate_dir / f"assembly_diff_vs_{baseline_label}.txt"
    assembly_diff_lines = []
    for change in changes:
        before = base_functions.get(change["function"])
        after = cand_functions.get(change["function"])
        assembly_diff_lines.extend(difflib.unified_diff(
            _function_assembly(baseline_dir / "firmware.disassembly.txt", before),
            _function_assembly(candidate_dir / "firmware.disassembly.txt", after),
            fromfile=f"{baseline_label}/{change['function']}",
            tofile=f"{candidate_label}/{change['function']}",
            lineterm="",
        ))
    assembly_diff_path.write_text("\n".join(assembly_diff_lines) + ("\n" if assembly_diff_lines else ""), encoding="utf-8")

    lines = [
        f"# `{baseline_label}` vs `{candidate_label}`",
        "",
        "All cost values are **STATIC COST ESTIMATE** relative units, not cycles or physical time.",
        "",
        f"- ROM before/after: {base_memory['rom_bytes']} / {cand_memory['rom_bytes']} bytes ({rom_delta:+d})",
        f"- RAM before/after: {base_memory['ram_bytes']} / {cand_memory['ram_bytes']} bytes ({ram_delta:+d})",
        f"- Executed ARM instruction trace: {base_trace['executed_arm_instructions']} / {cand_trace['executed_arm_instructions']} ({dynamic_instruction_delta:+d})",
        f"- Estimated static cost: {base_trace['relative_static_cost']} / {cand_trace['relative_static_cost']} ({dynamic_cost_delta:+d})",
        f"- Max absolute float error: {numerical.get('max_absolute_float_error', 'shape mismatch')}",
        f"- Max relative error: {numerical.get('max_relative_error', 'shape mismatch')}",
        f"- Max ULP difference: {numerical.get('max_ulp_difference', 'shape mismatch')}",
        f"- Output mismatches: {numerical.get('bitwise_output_mismatches', 'shape mismatch')}",
        f"- Verdict: **{verdict}**",
        "",
        "## Function evidence",
        "",
    ]
    if not changes:
        lines.append("No linked function metric changed.")
    for change in changes:
        helper_delta = change["dynamic_helper_calls_after"] - change["dynamic_helper_calls_before"]
        instruction_delta = change["instructions_after"] - change["instructions_before"]
        lines.extend([
            f"### `{change['function']}`",
            "",
            f"Function: `{change['function']}`  ",
            f"Source object: `{change['source_object_before']}` / `{change['source_object_after']}`  ",
            f"ROM before/after: {change['rom_before']} / {change['rom_after']} bytes  ",
            f"RAM before/after: image total {base_memory['ram_bytes']} / {cand_memory['ram_bytes']} bytes (per-function RAM is not derivable from code symbols)  ",
            f"Static instruction delta: {instruction_delta:+d}  ",
            f"Dynamic helper delta: {helper_delta:+d} calls in the deterministic run  ",
            f"Estimated static cost before/after: {change['static_cost_before']} / {change['static_cost_after']} relative units per static function body  ",
            f"Numerical regression: max abs {numerical.get('max_absolute_float_error', 'n/a')}, max rel {numerical.get('max_relative_error', 'n/a')}, max ULP {numerical.get('max_ulp_difference', 'n/a')}, mismatches {numerical.get('bitwise_output_mismatches', 'n/a')}  ",
            f"Assembly evidence: `assembly_diff_vs_{baseline_label}.txt` plus both saved full disassemblies  ",
            "Risk: deterministic CPU-math regression only; hardware timing and flight validation remain separate  ",
            f"Verdict: **{verdict}**",
            "",
        ])
    output_md = candidate_dir / f"comparison_vs_{baseline_label}.md"
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two saved binary benchmark snapshots.")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args()
    try:
        output = compare(args.baseline, args.candidate)
    except Exception as error:
        print(f"comparison failed: {error}", file=sys.stderr)
        return 1
    print(output)
    print(output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
