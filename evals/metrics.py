"""Metrics for the evaluation harness: accuracy, calibration, dissent value.

Pure functions over per-question result dicts (keys: correct, confidence,
dissent). No numpy — seeded stdlib randomness keeps every number in the
published results reproducible from the committed raw files.
"""

from __future__ import annotations

import random


def accuracy(results: list[dict]) -> float:
    return sum(r["correct"] for r in results) / len(results)


def bootstrap_ci(
    results: list[dict], stat, resamples: int = 10_000, seed: int = 0
) -> tuple[float, float]:
    """95% percentile bootstrap CI for `stat` over the question sample."""
    rng = random.Random(seed)
    n = len(results)
    stats = sorted(stat([results[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return stats[int(0.025 * resamples)], stats[int(0.975 * resamples)]


def brier(results: list[dict]) -> float:
    """Mean squared error of stated confidence against correctness (0 best, lower is better)."""
    return sum((r["confidence"] - r["correct"]) ** 2 for r in results) / len(results)


def ece(results: list[dict], bins: int = 10) -> float:
    """Expected calibration error: |confidence − accuracy| averaged over equal-width bins."""
    binned: list[list[dict]] = [[] for _ in range(bins)]
    for r in results:
        binned[min(int(r["confidence"] * bins), bins - 1)].append(r)
    total = len(results)
    error = 0.0
    for bucket in binned:
        if not bucket:
            continue
        conf = sum(r["confidence"] for r in bucket) / len(bucket)
        acc = accuracy(bucket)
        error += (len(bucket) / total) * abs(conf - acc)
    return error


def dissent_split(results: list[dict]) -> dict:
    """Does recorded dissent predict errors? Accuracy with and without dissent."""
    with_dissent = [r for r in results if r.get("dissent")]
    unanimous = [r for r in results if not r.get("dissent")]
    return {
        "n_dissent": len(with_dissent),
        "n_unanimous": len(unanimous),
        "accuracy_dissent": accuracy(with_dissent) if with_dissent else None,
        "accuracy_unanimous": accuracy(unanimous) if unanimous else None,
    }


def summarize(results: list[dict]) -> dict:
    """One condition's published row, CIs included."""
    acc_lo, acc_hi = bootstrap_ci(results, accuracy)
    summary = {
        "n": len(results),
        "accuracy": accuracy(results),
        "accuracy_ci95": [acc_lo, acc_hi],
        "brier": brier(results),
        "ece": ece(results),
        "mean_input_tokens": sum(r["usage"]["input"] for r in results) / len(results),
        "mean_output_tokens": sum(r["usage"]["output"] for r in results) / len(results),
    }
    if any(r.get("dissent") is not None for r in results):
        summary["dissent"] = dissent_split(results)
    return summary
