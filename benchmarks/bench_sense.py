#!/usr/bin/env python3
"""
bench_sense.py
==============
Benchmarks for the cadre-ai common sense engine.

Tests: action check throughput, seed matching accuracy (known-blocked actions),
and confidence scoring consistency.

Imports CommonSense directly — no live MCP server required.
Seeds are loaded from the real seeds.json.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Locate project root and inject framework path
# ---------------------------------------------------------------------------

_BENCH_DIR = Path(__file__).parent
_PROJECT_ROOT = _BENCH_DIR.parent
_SENSE_DIR = _PROJECT_ROOT / "framework" / "common-sense"
_SEEDS_PATH = _SENSE_DIR / "seeds.json"

if str(_SENSE_DIR) not in sys.path:
    sys.path.insert(0, str(_SENSE_DIR))

try:
    from sense import CommonSense

    _SENSE_AVAILABLE = True
except ImportError as _e:
    _SENSE_AVAILABLE = False
    _SENSE_IMPORT_ERROR = str(_e)


# ---------------------------------------------------------------------------
# Test action corpus
# ---------------------------------------------------------------------------

# Actions that should be BLOCKED or WARNED based on seeds.json
_BLOCKED_ACTIONS = [
    # git-001: force push
    "git push --force origin main",
    "git push -f main",
    # git-002: commit secrets
    "git add .env && git commit",
    "git commit credentials.json",
    # data-001: destructive DB ops
    "DROP TABLE memories",
    "TRUNCATE users",
    # deploy-001: deployment
    "deploy application to /opt/app",
    "copy build to /opt/production",
    # git-003: hard reset
    "git reset --hard HEAD~3",
    "git checkout . --force",
]

# Actions that should pass cleanly (low risk)
_SAFE_ACTIONS = [
    "read the config file",
    "list files in directory",
    "run unit tests",
    "check git status",
    "view log output",
    "describe database schema",
    "print environment variables",
    "search for keyword in codebase",
    "generate report",
    "parse JSON file",
]

# Mixed bag for throughput testing (representative workload)
_MIXED_ACTIONS = (
    _BLOCKED_ACTIONS
    + _SAFE_ACTIONS
    + [
        "push feature branch to remote",
        "send webhook notification",
        "deploy to staging",
        "delete temp directory",
        "overwrite output file",
        "merge pull request",
        "publish npm package",
        "rm -rf ./cache",
        "backup database before migration",
        "verify path exists before writing",
    ]
)


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def _make_cs(db_path: Optional[str] = None) -> "CommonSense":
    """Instantiate CommonSense pointing at a bench DB (or no DB)."""
    cs = CommonSense(project="bench", db_path=db_path)
    # Pre-warm seed cache so we don't measure first-load in throughput tests
    cs._ensure_seeds()
    return cs


def bench_check_throughput(cs: "CommonSense", actions: list[str], label: str = "mixed") -> dict:
    """
    Call cs.before() on each action and measure total + per-call time.
    Returns: elapsed_s, ops_per_s, per_call_ms
    """
    count = len(actions)
    t0 = time.perf_counter()
    results = [cs.before(a) for a in actions]
    elapsed = time.perf_counter() - t0

    blocked = sum(1 for r in results if r.blocked)
    warned = sum(1 for r in results if r.warnings and not r.blocked)
    clean = sum(1 for r in results if r.safe)

    return {
        "label": label,
        "action_count": count,
        "elapsed_s": round(elapsed, 6),
        "per_call_ms": round(elapsed / count * 1000, 4),
        "ops_per_s": round(count / elapsed),
        "blocked": blocked,
        "warned": warned,
        "clean": clean,
    }


def bench_seed_accuracy(cs: "CommonSense") -> dict:
    """
    Verify that every action in _BLOCKED_ACTIONS triggers a warning or block.
    Measures both correctness and timing.
    """
    hits = 0
    misses = []
    timings = []

    for action in _BLOCKED_ACTIONS:
        t0 = time.perf_counter()
        result = cs.before(action)
        timings.append(time.perf_counter() - t0)

        if result.blocked or result.warnings:
            hits += 1
        else:
            misses.append(action)

    accuracy = hits / len(_BLOCKED_ACTIONS)
    avg_ms = sum(timings) / len(timings) * 1000

    return {
        "total_blocked_actions": len(_BLOCKED_ACTIONS),
        "correctly_caught": hits,
        "missed": len(misses),
        "accuracy": round(accuracy, 4),
        "accuracy_pct": f"{accuracy:.1%}",
        "avg_check_ms": round(avg_ms, 4),
        "missed_actions": misses,
    }


def bench_confidence_consistency(cs: "CommonSense") -> dict:
    """
    Check that:
    1. All confidence values are in [0.0, 1.0]
    2. Destructive/blocked actions score strictly lower than known-safe actions
    3. Variance within the safe group is low
    """
    safe_confs = []
    blocked_confs = []
    out_of_range = []

    for action in _SAFE_ACTIONS:
        r = cs.before(action)
        if not (0.0 <= r.confidence <= 1.0):
            out_of_range.append((action, r.confidence))
        safe_confs.append(r.confidence)

    for action in _BLOCKED_ACTIONS:
        r = cs.before(action)
        if not (0.0 <= r.confidence <= 1.0):
            out_of_range.append((action, r.confidence))
        blocked_confs.append(r.confidence)

    safe_avg = sum(safe_confs) / len(safe_confs) if safe_confs else 0
    blocked_avg = sum(blocked_confs) / len(blocked_confs) if blocked_confs else 0

    # Compute variance for safe group
    safe_var = (
        sum((c - safe_avg) ** 2 for c in safe_confs) / len(safe_confs)
        if len(safe_confs) > 1
        else 0.0
    )

    ordering_correct = blocked_avg < safe_avg

    return {
        "safe_avg_confidence": round(safe_avg, 4),
        "blocked_avg_confidence": round(blocked_avg, 4),
        "safe_variance": round(safe_var, 6),
        "ordering_correct": ordering_correct,
        "out_of_range_count": len(out_of_range),
        "out_of_range": out_of_range,
    }


def bench_seed_load_time() -> dict:
    """Measure cold and warm seed loading time."""
    import sense as sense_module

    # Cold load — clear the cache
    sense_module._SEEDS_CACHE = None
    cs_cold = CommonSense(project="bench")

    t0 = time.perf_counter()
    cs_cold._ensure_seeds()
    cold_elapsed = time.perf_counter() - t0

    seed_count = len(sense_module._SEEDS_CACHE or [])

    # Warm load — cache already populated
    cs_warm = CommonSense(project="bench")
    t0 = time.perf_counter()
    cs_warm._ensure_seeds()
    warm_elapsed = time.perf_counter() - t0

    # Reset for other tests
    sense_module._SEEDS_CACHE = None

    return {
        "seed_count": seed_count,
        "cold_load_ms": round(cold_elapsed * 1000, 4),
        "warm_load_ms": round(warm_elapsed * 1000, 6),
        "speedup": round(cold_elapsed / max(warm_elapsed, 1e-9), 1),
    }


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> list[dict]:
    """Run all sense benchmarks. Returns list of result dicts."""
    results = []

    if not _SENSE_AVAILABLE:
        results.append(
            {
                "benchmark": "import_error",
                "error": f"Could not import sense.py: {_SENSE_IMPORT_ERROR}",
                "seeds_path": str(_SEEDS_PATH),
                "seeds_exists": _SEEDS_PATH.exists(),
            }
        )
        if verbose:
            print(f"  [ERROR] Could not import sense.py: {_SENSE_IMPORT_ERROR}")
        return results

    # --- Seed load time ---
    seed_load = bench_seed_load_time()
    results.append(
        {
            "benchmark": "seed_load_time",
            "label": f"Load {seed_load['seed_count']} seeds from JSON",
            "elapsed_s": round(seed_load["cold_load_ms"] / 1000, 6),
            "detail": seed_load,
        }
    )
    if verbose:
        print(
            f"  [seed_load] cold={seed_load['cold_load_ms']:.2f}ms | warm={seed_load['warm_load_ms'] * 1000:.4f}us | {seed_load['seed_count']} seeds"
        )

    # Create a warm CommonSense instance for remaining tests
    cs = _make_cs()

    # --- Check throughput (safe actions) ---
    safe_tp = bench_check_throughput(cs, _SAFE_ACTIONS * 5, label="safe_x5")
    results.append(
        {
            "benchmark": "check_throughput_safe",
            "label": f"cs.before() x{safe_tp['action_count']} safe actions",
            "elapsed_s": safe_tp["elapsed_s"],
            "ops_per_s": safe_tp["ops_per_s"],
            "per_call_ms": safe_tp["per_call_ms"],
            "detail": safe_tp,
        }
    )
    if verbose:
        print(
            f"  [throughput_safe] {safe_tp['ops_per_s']:,} ops/s | {safe_tp['per_call_ms']:.3f}ms/call"
        )

    # --- Check throughput (blocked actions) ---
    blocked_tp = bench_check_throughput(cs, _BLOCKED_ACTIONS * 5, label="blocked_x5")
    results.append(
        {
            "benchmark": "check_throughput_blocked",
            "label": f"cs.before() x{blocked_tp['action_count']} blocked actions",
            "elapsed_s": blocked_tp["elapsed_s"],
            "ops_per_s": blocked_tp["ops_per_s"],
            "per_call_ms": blocked_tp["per_call_ms"],
            "detail": blocked_tp,
        }
    )
    if verbose:
        print(
            f"  [throughput_blocked] {blocked_tp['ops_per_s']:,} ops/s | {blocked_tp['per_call_ms']:.3f}ms/call"
        )

    # --- Check throughput (mixed, 100 calls) ---
    mixed_actions = (_MIXED_ACTIONS * 3)[:100]
    mixed_tp = bench_check_throughput(cs, mixed_actions, label="mixed_100")
    results.append(
        {
            "benchmark": "check_throughput_mixed_100",
            "label": "cs.before() x100 mixed actions",
            "elapsed_s": mixed_tp["elapsed_s"],
            "ops_per_s": mixed_tp["ops_per_s"],
            "per_call_ms": mixed_tp["per_call_ms"],
            "detail": mixed_tp,
        }
    )
    if verbose:
        print(
            f"  [throughput_mixed_100] {mixed_tp['ops_per_s']:,} ops/s | {mixed_tp['per_call_ms']:.3f}ms/call | blocked={mixed_tp['blocked']} warned={mixed_tp['warned']} clean={mixed_tp['clean']}"
        )

    # --- Seed matching accuracy ---
    accuracy = bench_seed_accuracy(cs)
    results.append(
        {
            "benchmark": "seed_accuracy",
            "label": "Seed block detection accuracy",
            "accuracy": accuracy["accuracy"],
            "accuracy_pct": accuracy["accuracy_pct"],
            "detail": accuracy,
        }
    )
    if verbose:
        print(
            f"  [seed_accuracy] {accuracy['accuracy_pct']} ({accuracy['correctly_caught']}/{accuracy['total_blocked_actions']}) | missed: {accuracy['missed']}"
        )
        if accuracy["missed_actions"]:
            for m in accuracy["missed_actions"]:
                print(f"    MISSED: {m}")

    # --- Confidence scoring consistency ---
    conf = bench_confidence_consistency(cs)
    results.append(
        {
            "benchmark": "confidence_consistency",
            "label": "Confidence scoring bounds + ordering",
            "ordering_correct": conf["ordering_correct"],
            "out_of_range": conf["out_of_range_count"],
            "detail": conf,
        }
    )
    if verbose:
        print(
            f"  [confidence] safe_avg={conf['safe_avg_confidence']:.3f} | "
            f"blocked_avg={conf['blocked_avg_confidence']:.3f} | "
            f"ordering_correct={conf['ordering_correct']} | "
            f"out_of_range={conf['out_of_range_count']}"
        )

    return results


if __name__ == "__main__":
    print("Running sense benchmarks standalone...\n")
    results = run(verbose=True)
    print(f"\nDone. {len(results)} benchmark results collected.")
