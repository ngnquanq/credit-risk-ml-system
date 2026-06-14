#!/usr/bin/env python3
"""Capture and summarize Kubernetes pod-level CFS metrics for load-test cycles."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_NAMESPACES = (
    "api-gateway",
    "data-services",
    "feature-registry",
    "kserve",
    "knative-eventing",
    "knative-serving",
    "kourier-system",
)

METRIC_NAMES = {
    "container_cpu_cfs_periods_total": "cfs_periods",
    "container_cpu_cfs_throttled_periods_total": "throttled_periods",
    "container_cpu_cfs_throttled_seconds_total": "throttled_seconds",
    "container_cpu_usage_seconds_total": "cpu_usage_seconds",
    "container_memory_working_set_bytes": "memory_working_set_bytes",
}

LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')
SAMPLE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)")


CPU_RE = re.compile(r"^([0-9.]+)(m?)$")
MEMORY_RE = re.compile(r"^([0-9.]+)(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?$")
MEMORY_MULTIPLIERS = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
    "P": 1000**5,
    "E": 1000**6,
    None: 1,
}


def run_kubectl(args: list[str]) -> str:
    proc = subprocess.run(
        ["kubectl", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def parse_cpu_cores(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    match = CPU_RE.match(str(value))
    if not match:
        return 0.0
    amount = float(match.group(1))
    return amount / 1000 if match.group(2) == "m" else amount


def parse_memory_mib(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    match = MEMORY_RE.match(str(value))
    if not match:
        return 0.0
    amount = float(match.group(1))
    suffix = match.group(2)
    return amount * MEMORY_MULTIPLIERS[suffix] / 1024 / 1024


def parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    return {match.group(1): match.group(2).replace(r"\"", '"') for match in LABEL_RE.finditer(raw)}


def parse_cadvisor(text: str, namespaces: set[str]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}

    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue

        sample = SAMPLE_RE.match(line)
        if not sample:
            continue

        metric_name, labels_raw, value_raw = sample.groups()
        field = METRIC_NAMES.get(metric_name)
        if not field:
            continue

        labels = parse_labels(labels_raw)
        namespace = labels.get("namespace", "")
        pod = labels.get("pod", "")
        container = labels.get("container") or "pod"

        if namespace not in namespaces or not pod:
            continue
        if metric_name == "container_cpu_usage_seconds_total" and labels.get("cpu", "total") != "total":
            continue

        try:
            value = float(value_raw)
        except ValueError:
            continue

        key = f"{namespace}/{pod}/{container}"
        row = metrics.setdefault(
            key,
            {
                "namespace": namespace,
                "pod": pod,
                "container": container,
                "metrics": {},
            },
        )
        row["metrics"][field] = value

    return metrics


def pod_status_by_key(pods_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for item in pods_json.get("items", []):
        metadata = item.get("metadata", {})
        status = item.get("status", {})
        namespace = metadata.get("namespace", "")
        pod = metadata.get("name", "")
        if not namespace or not pod:
            continue

        container_statuses = status.get("containerStatuses", []) or []
        restarts = sum(int(s.get("restartCount", 0)) for s in container_statuses)
        waiting_reasons = [
            s.get("state", {}).get("waiting", {}).get("reason", "")
            for s in container_statuses
            if s.get("state", {}).get("waiting", {}).get("reason")
        ]
        terminated_reasons = [
            s.get("lastState", {}).get("terminated", {}).get("reason", "")
            for s in container_statuses
            if s.get("lastState", {}).get("terminated", {}).get("reason")
        ]
        statuses[f"{namespace}/{pod}"] = {
            "phase": status.get("phase", ""),
            "restarts": restarts,
            "waiting_reasons": waiting_reasons,
            "last_terminated_reasons": terminated_reasons,
        }
    return statuses


def pod_resources(pods_json: dict[str, Any], namespaces: set[str]) -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for item in pods_json.get("items", []):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        namespace = metadata.get("namespace", "")
        pod = metadata.get("name", "")
        if namespace not in namespaces or not pod:
            continue

        requests_cpu = 0.0
        limits_cpu = 0.0
        requests_memory = 0.0
        limits_memory = 0.0
        for container in spec.get("containers", []) or []:
            container_resources = container.get("resources", {})
            requests = container_resources.get("requests", {})
            limits = container_resources.get("limits", {})
            requests_cpu += parse_cpu_cores(requests.get("cpu"))
            limits_cpu += parse_cpu_cores(limits.get("cpu"))
            requests_memory += parse_memory_mib(requests.get("memory"))
            limits_memory += parse_memory_mib(limits.get("memory"))

        resources[f"{namespace}/{pod}"] = {
            "namespace": namespace,
            "pod": pod,
            "cpu_request_cores": round(requests_cpu, 4),
            "cpu_limit_cores": round(limits_cpu, 4),
            "memory_request_mib": round(requests_memory, 1),
            "memory_limit_mib": round(limits_memory, 1),
        }
    return resources


def node_capacity(nodes_json: dict[str, Any], node: str) -> dict[str, Any]:
    for item in nodes_json.get("items", []):
        if item.get("metadata", {}).get("name") != node:
            continue
        status = item.get("status", {})
        capacity = status.get("capacity", {})
        allocatable = status.get("allocatable", {})
        return {
            "capacity_cpu_cores": round(parse_cpu_cores(capacity.get("cpu")), 4),
            "allocatable_cpu_cores": round(parse_cpu_cores(allocatable.get("cpu")), 4),
            "capacity_memory_mib": round(parse_memory_mib(capacity.get("memory")), 1),
            "allocatable_memory_mib": round(parse_memory_mib(allocatable.get("memory")), 1),
            "capacity_pods": int(capacity.get("pods", 0)),
            "allocatable_pods": int(allocatable.get("pods", 0)),
        }
    return {}


def snapshot(args: argparse.Namespace) -> None:
    namespaces = set(args.namespaces.split(","))
    node = args.node
    if not node:
        nodes = json.loads(run_kubectl(["get", "nodes", "-o", "json"]))
        node = nodes["items"][0]["metadata"]["name"]
    else:
        nodes = json.loads(run_kubectl(["get", "nodes", "-o", "json"]))

    cadvisor = run_kubectl(["get", "--raw", f"/api/v1/nodes/{node}/proxy/metrics/cadvisor"])
    pods = json.loads(run_kubectl(["get", "pods", "-A", "-o", "json"]))
    resources = pod_resources(pods, namespaces)

    output = {
        "captured_at_epoch": time.time(),
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "node": node,
        "node_capacity": node_capacity(nodes, node),
        "namespaces": sorted(namespaces),
        "metrics": parse_cadvisor(cadvisor, namespaces),
        "pod_resources": resources,
        "pod_status": pod_status_by_key(pods),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(out_path)


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def metric_delta(start_metrics: dict[str, float], end_metrics: dict[str, float], name: str) -> float:
    if name not in start_metrics or name not in end_metrics:
        return 0.0
    return max(0.0, float(end_metrics[name]) - float(start_metrics[name]))


def summarize_rows(start: dict[str, Any], end: dict[str, Any]) -> list[dict[str, Any]]:
    started = start.get("metrics", {})
    ended = end.get("metrics", {})
    duration = max(1.0, float(end["captured_at_epoch"]) - float(start["captured_at_epoch"]))
    rows: list[dict[str, Any]] = []

    for key in sorted(set(started) | set(ended)):
        start_row = started.get(key, {})
        end_row = ended.get(key, {})
        labels = end_row or start_row
        start_values = start_row.get("metrics", {})
        end_values = end_row.get("metrics", {})

        periods = metric_delta(start_values, end_values, "cfs_periods")
        throttled_periods = metric_delta(start_values, end_values, "throttled_periods")
        throttled_seconds = metric_delta(start_values, end_values, "throttled_seconds")
        cpu_seconds = metric_delta(start_values, end_values, "cpu_usage_seconds")
        memory_bytes = end_values.get("memory_working_set_bytes", start_values.get("memory_working_set_bytes", 0.0))

        throttled_ratio = throttled_periods / periods if periods > 0 else 0.0
        pod_key = f"{labels.get('namespace', '')}/{labels.get('pod', '')}"
        start_status = start.get("pod_status", {}).get(pod_key, {})
        end_status = end.get("pod_status", {}).get(pod_key, {})
        restart_delta = int(end_status.get("restarts", 0)) - int(start_status.get("restarts", 0))
        resources = end.get("pod_resources", {}).get(pod_key, start.get("pod_resources", {}).get(pod_key, {}))

        rows.append(
            {
                "namespace": labels.get("namespace", ""),
                "pod": labels.get("pod", ""),
                "container": labels.get("container", ""),
                "duration_seconds": round(duration, 3),
                "cpu_cores_avg": round(cpu_seconds / duration, 4),
                "cpu_seconds_delta": round(cpu_seconds, 4),
                "cfs_periods_delta": int(periods),
                "throttled_periods_delta": int(throttled_periods),
                "throttled_period_ratio": round(throttled_ratio, 4),
                "throttled_seconds_delta": round(throttled_seconds, 4),
                "memory_working_set_mib": round(float(memory_bytes) / 1024 / 1024, 1),
                "cpu_request_cores": float(resources.get("cpu_request_cores", 0.0)),
                "cpu_limit_cores": float(resources.get("cpu_limit_cores", 0.0)),
                "memory_request_mib": float(resources.get("memory_request_mib", 0.0)),
                "memory_limit_mib": float(resources.get("memory_limit_mib", 0.0)),
                "restart_delta": restart_delta,
                "phase": end_status.get("phase", ""),
                "waiting_reasons": ",".join(end_status.get("waiting_reasons", [])),
                "last_terminated_reasons": ",".join(end_status.get("last_terminated_reasons", [])),
            }
        )

    rows.sort(key=lambda row: (row["throttled_period_ratio"], row["cpu_cores_avg"]), reverse=True)
    return rows


def write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "namespace",
        "pod",
        "container",
        "duration_seconds",
        "cpu_cores_avg",
        "cpu_seconds_delta",
        "cfs_periods_delta",
        "throttled_periods_delta",
        "throttled_period_ratio",
        "throttled_seconds_delta",
        "memory_working_set_mib",
        "cpu_request_cores",
        "cpu_limit_cores",
        "memory_request_mib",
        "memory_limit_mib",
        "restart_delta",
        "phase",
        "waiting_reasons",
        "last_terminated_reasons",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: str, rows: list[dict[str, Any]], start: dict[str, Any], end: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    top_rows = rows[:20]
    total_cpu = sum(float(row["cpu_cores_avg"]) for row in rows)
    total_cpu_request = sum(float(row["cpu_request_cores"]) for row in rows)
    total_cpu_limit = sum(float(row["cpu_limit_cores"]) for row in rows)
    total_memory = sum(float(row["memory_working_set_mib"]) for row in rows)
    total_memory_request = sum(float(row["memory_request_mib"]) for row in rows)
    total_memory_limit = sum(float(row["memory_limit_mib"]) for row in rows)
    node = end.get("node_capacity") or start.get("node_capacity") or {}
    alloc_cpu = float(node.get("allocatable_cpu_cores", 0.0))
    alloc_memory = float(node.get("allocatable_memory_mib", 0.0))
    lines = [
        "# K8s Cycle Metrics",
        "",
        f"- Start: {start.get('captured_at_utc', '')}",
        f"- End: {end.get('captured_at_utc', '')}",
        f"- Node: {end.get('node', start.get('node', ''))}",
        f"- Node allocatable: {alloc_cpu:.2f} CPU / {alloc_memory:.0f} MiB memory",
        f"- Tracked actual usage: {total_cpu:.3f} CPU / {total_memory:.0f} MiB memory",
        f"- Tracked requests: {total_cpu_request:.3f} CPU / {total_memory_request:.0f} MiB memory",
        f"- Tracked limits: {total_cpu_limit:.3f} CPU / {total_memory_limit:.0f} MiB memory",
        "",
        "| Namespace | Pod | CPU avg | CPU req | CPU limit | Throttle % | Memory MiB | Mem req | Restarts |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in top_rows:
        lines.append(
            "| {namespace} | {pod} | {cpu:.3f} | {cpu_request:.3f} | {cpu_limit:.3f} | {throttle:.1f}% | {memory:.1f} | {memory_request:.1f} | {restarts} |".format(
                namespace=row["namespace"],
                pod=row["pod"],
                cpu=row["cpu_cores_avg"],
                cpu_request=row["cpu_request_cores"],
                cpu_limit=row["cpu_limit_cores"],
                throttle=row["throttled_period_ratio"] * 100,
                memory=row["memory_working_set_mib"],
                memory_request=row["memory_request_mib"],
                restarts=row["restart_delta"],
            )
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(args: argparse.Namespace) -> None:
    start = load_json(args.start)
    end = load_json(args.end)
    rows = summarize_rows(start, end)

    if args.csv:
        write_csv(args.csv, rows)
        print(args.csv)
    if args.markdown:
        write_markdown(args.markdown, rows, start, end)
        print(args.markdown)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--out", required=True)
    snapshot_parser.add_argument("--node", default="")
    snapshot_parser.add_argument("--namespaces", default=",".join(DEFAULT_NAMESPACES))
    snapshot_parser.set_defaults(func=snapshot)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--start", required=True)
    summarize_parser.add_argument("--end", required=True)
    summarize_parser.add_argument("--csv", required=True)
    summarize_parser.add_argument("--markdown", required=True)
    summarize_parser.set_defaults(func=summarize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
