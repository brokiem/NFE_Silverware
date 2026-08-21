from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from benchmark.benchlib import BENCHMARK, create_snapshot, read_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild and capture a binary-grounded NFE_Silverware benchmark snapshot."
    )
    parser.add_argument("label", help="snapshot label, for example baseline or candidate")
    parser.add_argument("--compare", metavar="BASELINE", help="after rebuilding this label, compare it with BASELINE")
    args = parser.parse_args()

    try:
        result = create_snapshot(args.label)
    except Exception as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    if args.label == "baseline":
        shutil.copy2(result / "baseline_report.md", BENCHMARK / "baseline_report.md")
    memory = read_json(result / "memory.json")
    trace = read_json(result / "math_trace.json")
    print(f"snapshot: {result}")
    print(f"firmware ROM/RAM: {memory.get('rom_bytes')} / {memory.get('ram_bytes')} bytes")
    print(
        "STATIC COST ESTIMATE: "
        f"{trace['relative_static_cost']} relative units across {trace['iterations']} deterministic iterations"
    )
    if args.compare:
        from compare import compare
        comparison = compare(args.compare, args.label)
        print(f"comparison: {comparison}")
    print("No physical cycle or timing claim is made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
