#!/usr/bin/env python3
"""Probe direct KServe /v1/score-by-id latency with known application IDs."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_ids(args: argparse.Namespace) -> list[str]:
    ids: list[str] = []
    if args.ids:
        ids.extend(item.strip() for item in args.ids.split(",") if item.strip())
    if args.ids_file:
        ids.extend(
            line.strip()
            for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not ids:
        raise SystemExit("Provide --ids or --ids-file with sk_id_curr values already present in Feast.")
    return ids


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def post_score(url: str, sk_id_curr: str, timeout: float) -> dict[str, Any]:
    body = json.dumps({"sk_id_curr": sk_id_curr}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
        error = ""
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
        error = payload.decode("utf-8", errors="replace")[:500]
    except Exception as exc:  # pragma: no cover - exercised against live service
        payload = b""
        status = 0
        error = str(exc)
    finished = time.perf_counter()
    return {
        "sk_id_curr": sk_id_curr,
        "status": status,
        "latency_ms": (finished - started) * 1000,
        "bytes": len(payload),
        "error": error,
    }


def run_probe(args: argparse.Namespace) -> int:
    ids = load_ids(args)
    work = [ids[i % len(ids)] for i in range(args.requests)]
    results: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(post_score, args.url, sk_id, args.timeout) for sk_id in work]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    successes = [row for row in results if 200 <= int(row["status"]) < 300]
    failures = [row for row in results if row not in successes]
    latencies = [float(row["latency_ms"]) for row in successes]

    summary = {
        "url": args.url,
        "requests": len(results),
        "concurrency": args.concurrency,
        "successes": len(successes),
        "failures": len(failures),
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0.0,
            "p50": round(statistics.median(latencies), 3) if latencies else 0.0,
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "sample_failures": failures[:5],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Direct scoring URL ending in /v1/score-by-id")
    parser.add_argument("--ids", default="", help="Comma-separated sk_id_curr values")
    parser.add_argument("--ids-file", default="", help="File with one sk_id_curr per line")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    return run_probe(args)


if __name__ == "__main__":
    raise SystemExit(main())
