#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdc", default="results/cdc-latency.csv")
    parser.add_argument("--output", default="results/summary.json")
    args = parser.parse_args()

    values: list[float] = []
    with Path(args.cdc).open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("latency_ms"):
                values.append(float(row["latency_ms"]))

    summary = {
        "samples": len(values),
        "latency_ms": {
            "min": min(values) if values else None,
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "max": max(values) if values else None,
            "mean": statistics.mean(values) if values else None,
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

