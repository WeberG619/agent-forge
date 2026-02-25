#!/usr/bin/env python3
"""
run_benchmarks.py
=================
Main benchmark runner for cadre-ai.

Usage:
    python benchmarks/run_benchmarks.py                  # all suites
    python benchmarks/run_benchmarks.py --suite memory   # single suite
    python benchmarks/run_benchmarks.py --suite sense    # single suite
    python benchmarks/run_benchmarks.py --suite agents   # single suite
    python benchmarks/run_benchmarks.py --json out.json  # save results
    python benchmarks/run_benchmarks.py --verbose        # verbose output
    python benchmarks/run_benchmarks.py --quiet          # suppress per-benchmark details

Outputs:
    - System info header (Python, OS, RAM, CPU count)
    - Aligned results table per suite
    - Optional JSON dump of all results
"""

import sys
import os
import json
import time
import platform
import argparse
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------

_BENCH_DIR = Path(__file__).parent
_PROJECT_ROOT = _BENCH_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------

def get_system_info() -> dict:
    """Collect system metadata for the benchmark header."""
    info = {
        "python_version": sys.version.split()[0],
        "python_impl": platform.python_implementation(),
        "os": platform.system(),
        "os_version": platform.version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # RAM (best-effort)
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    info["ram_gb"] = round(kb / 1024 / 1024, 1)
                    break
    except Exception:
        try:
            info["ram_gb"] = "N/A"
        except Exception:
            info["ram_gb"] = "N/A"

    # SQLite version
    try:
        import sqlite3
        info["sqlite_version"] = sqlite3.sqlite_version
    except Exception:
        info["sqlite_version"] = "N/A"

    return info


def print_system_info(info: dict) -> None:
    sep = "=" * 70
    print(sep)
    print("  cadre-ai Benchmark Suite")
    print(sep)
    print(f"  Python   : {info['python_version']} ({info['python_impl']})")
    print(f"  OS       : {info['os']} / {info['machine']}")
    print(f"  CPUs     : {info['cpu_count']}")
    print(f"  RAM      : {info.get('ram_gb', 'N/A')} GB")
    print(f"  SQLite   : {info.get('sqlite_version', 'N/A')}")
    print(f"  Time     : {info['timestamp']}")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------

def _format_result_row(suite: str, result: dict) -> Optional[tuple[str, str, str]]:
    """
    Convert a result dict to a (suite, benchmark, value) tuple for table display.
    Returns None if the result should be skipped (e.g. nested-detail-only entries).
    """
    bench = result.get("benchmark", "?")

    # Primary metric selection — pick the most useful single number
    if "error" in result:
        value = f"ERROR: {result['error'][:50]}"
    elif "elapsed_s" in result and "ops_per_s" in result:
        value = f"{result['elapsed_s']*1000:.2f} ms  |  {result['ops_per_s']:,} ops/s"
    elif "elapsed_s" in result and "per_call_ms" in result:
        value = f"{result['elapsed_s']*1000:.2f} ms  |  {result['per_call_ms']:.3f} ms/call"
    elif "elapsed_s" in result and "per_file_ms" in result:
        value = f"{result['elapsed_s']*1000:.2f} ms  |  {result['per_file_ms']:.3f} ms/file"
    elif "elapsed_s" in result and "per_call_us" in result:
        value = f"{result['elapsed_s']*1000:.2f} ms  |  {result['per_call_us']:.1f} us/call"
    elif "elapsed_s" in result:
        value = f"{result['elapsed_s']*1000:.3f} ms"
    elif "size_kb" in result:
        value = f"{result['size_kb']} KB  |  {result.get('bytes_per_row', '?')} bytes/row"
    elif "hit_ratio" in result:
        value = f"hit_ratio={result['hit_ratio']:.1%}  |  {result.get('detail', {}).get('avg_hit_s', 0)*1000:.3f}ms hit"
    elif "accuracy_pct" in result:
        value = f"accuracy={result['accuracy_pct']}"
    elif "ordering_correct" in result:
        value = f"ordering_ok={result['ordering_correct']}  |  out_of_range={result.get('out_of_range', 0)}"
    elif "total" in result and "md" in result:
        value = f"{result['total']} agents ({result['md']} .md, {result['yaml']} .yaml)"
    elif "valid" in result and "invalid" in result:
        value = f"{result['valid']} valid, {result['invalid']} invalid, {result.get('total_errors', 0)} errors"
    elif "route_success_rate" in result:
        value = f"success={result['route_success_rate']:.1%}  |  {result.get('ops_per_s', '?'):,} ops/s"
    elif "cold_ms" in result:
        value = f"cold={result['cold_ms']:.2f}ms  |  warm={result['warm_avg_ms']:.2f}ms  |  {result['speedup']:.1f}x"
    elif "seed_count" in result:
        d = result.get("detail", {})
        value = f"{d.get('seed_count', '?')} seeds  |  cold={d.get('cold_load_ms', 0):.2f}ms"
    else:
        value = str({k: v for k, v in result.items() if k not in ("benchmark", "label", "detail")})[:60]

    return (suite, bench, value)


def print_results_table(suite_results: dict[str, list[dict]]) -> None:
    """Print all results as an aligned table."""
    rows = []
    for suite, results in suite_results.items():
        for r in results:
            row = _format_result_row(suite, r)
            if row:
                rows.append(row)

    if not rows:
        print("No results to display.")
        return

    col_w = [
        max(len("Suite"), max(len(r[0]) for r in rows)),
        max(len("Benchmark"), max(len(r[1]) for r in rows)),
        max(len("Result"), max(len(r[2]) for r in rows)),
    ]

    header = (
        f"{'Suite':<{col_w[0]}}  "
        f"{'Benchmark':<{col_w[1]}}  "
        f"{'Result'}"
    )
    divider = "  ".join("-" * w for w in col_w)

    print(header)
    print(divider)

    last_suite = None
    for suite, bench, value in rows:
        if suite != last_suite and last_suite is not None:
            print()  # Blank line between suites
        last_suite = suite
        print(f"{suite:<{col_w[0]}}  {bench:<{col_w[1]}}  {value}")

    print()


# ---------------------------------------------------------------------------
# Suite loading
# ---------------------------------------------------------------------------

AVAILABLE_SUITES = ["memory", "sense", "agents"]


def load_suite(name: str):
    """Dynamically import and return a benchmark suite module."""
    import importlib
    module_name = f"bench_{name}"
    try:
        mod = importlib.import_module(module_name)
        return mod
    except ImportError as e:
        print(f"  [WARN] Could not load suite '{name}': {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="cadre-ai benchmark runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmarks/run_benchmarks.py
  python benchmarks/run_benchmarks.py --suite memory
  python benchmarks/run_benchmarks.py --suite sense --verbose
  python benchmarks/run_benchmarks.py --json /tmp/bench_results.json
        """,
    )
    parser.add_argument(
        "--suite",
        choices=AVAILABLE_SUITES,
        default=None,
        help="Run only this suite (default: all suites)",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="Write full results as JSON to this path",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-benchmark details during run",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-suite headers; show only final table",
    )
    args = parser.parse_args()

    suites_to_run = [args.suite] if args.suite else AVAILABLE_SUITES

    # --- System info ---
    sys_info = get_system_info()
    print_system_info(sys_info)

    # --- Run suites ---
    all_results: dict[str, list[dict]] = {}
    suite_timings: dict[str, float] = {}
    overall_t0 = time.perf_counter()

    for suite_name in suites_to_run:
        if not args.quiet:
            print(f"[{suite_name.upper()}]")

        mod = load_suite(suite_name)
        if mod is None:
            all_results[suite_name] = [{"benchmark": "load_error", "error": f"Could not import bench_{suite_name}"}]
            continue

        suite_t0 = time.perf_counter()
        try:
            suite_results = mod.run(verbose=args.verbose)
        except Exception as exc:
            import traceback
            suite_results = [{
                "benchmark": "runtime_error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }]
            if not args.quiet:
                print(f"  [ERROR] Suite crashed: {exc}")

        suite_elapsed = time.perf_counter() - suite_t0
        suite_timings[suite_name] = round(suite_elapsed, 3)
        all_results[suite_name] = suite_results

        if not args.quiet:
            print(f"  Completed in {suite_elapsed:.3f}s ({len(suite_results)} benchmarks)\n")

    overall_elapsed = time.perf_counter() - overall_t0

    # --- Print results table ---
    print("\nResults")
    print("=" * 70)
    print_results_table(all_results)

    # --- Suite timing summary ---
    print("Suite Timing Summary")
    print("-" * 40)
    for suite_name, t in suite_timings.items():
        print(f"  {suite_name:<12}  {t:.3f}s")
    print(f"  {'TOTAL':<12}  {overall_elapsed:.3f}s")
    print()

    # --- JSON output ---
    if args.json:
        output = {
            "system": sys_info,
            "suites": all_results,
            "timings": suite_timings,
            "total_elapsed_s": round(overall_elapsed, 3),
        }
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2, default=str))
        print(f"Results written to: {out_path.resolve()}")

    # Return non-zero if any suite had errors
    has_errors = any(
        any("error" in r for r in suite_results)
        for suite_results in all_results.values()
    )
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
