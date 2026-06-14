#!/usr/bin/env python3
"""Capture effective lag for the Knative Sequence KafkaChannel backing topic."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


GROUP_PREFIX = "kafka.kserve.scoring-pipeline-kn-sequence-0"
DEFAULT_TOPIC_PATTERN = r"^knative-messaging-kafka\.kserve\.scoring-pipeline-kn-sequence-.*"


def run(cmd: list[str], check: bool = True) -> str:
    proc = subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def kubectl(args: list[str], check: bool = True) -> str:
    return run(["kubectl", *args], check=check)


def kafka_exec(namespace: str, timeout_seconds: int, args: list[str], check: bool = True) -> str:
    return kubectl(
        [
            "-n",
            namespace,
            "exec",
            "kafka-broker-0",
            "--",
            "timeout",
            str(timeout_seconds),
            *args,
        ],
        check=check,
    )


def maybe_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not re.fullmatch(r"-?\d+", text):
        return None
    parsed = int(text)
    return parsed if parsed >= 0 else None


def partition_lag(earliest: int, latest: int, committed: int | None) -> dict[str, int | None]:
    """Return effective lag and stale committed-offset accounting for one partition."""
    normalized_committed = committed if committed is not None else earliest
    stale_lag = max(0, earliest - normalized_committed)
    effective_floor = max(normalized_committed, earliest)
    effective_lag = max(0, latest - effective_floor)
    raw_lag = max(0, latest - normalized_committed)
    return {
        "earliest": earliest,
        "latest": latest,
        "committed": committed,
        "raw_lag": raw_lag,
        "stale_lag": stale_lag,
        "effective_lag": effective_lag,
    }


def parse_offsets(text: str) -> dict[int, int]:
    offsets: dict[int, int] = {}
    for line in text.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 3:
            continue
        partition = maybe_int(parts[-2])
        offset = maybe_int(parts[-1])
        if partition is not None and offset is not None:
            offsets[partition] = offset
    return offsets


def parse_group_describe(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("GROUP "):
            continue
        parts = stripped.split()
        if len(parts) < 6:
            continue
        partition = maybe_int(parts[2])
        current = maybe_int(parts[3])
        log_end = maybe_int(parts[4])
        cli_lag = maybe_int(parts[5])
        if partition is None:
            continue
        rows.append(
            {
                "group": parts[0],
                "topic": parts[1],
                "partition": partition,
                "current_offset": current,
                "log_end_offset": log_end,
                "reported_lag": cli_lag,
                "consumer_id": parts[6] if len(parts) > 6 else "",
                "host": parts[7] if len(parts) > 7 else "",
                "client_id": parts[8] if len(parts) > 8 else "",
            }
        )
    return rows


def resolve_backing_topic(kserve_namespace: str, data_namespace: str, timeout_seconds: int) -> str:
    channel_json = kubectl(
        [
            "-n",
            kserve_namespace,
            "get",
            "kafkachannel",
            "scoring-pipeline-kn-sequence-0",
            "-o",
            "json",
        ],
        check=False,
    )
    if channel_json:
        try:
            channel = json.loads(channel_json)
            annotations = channel.get("status", {}).get("annotations", {}) or {}
            topic = annotations.get("default.topic")
            if topic:
                return topic
        except json.JSONDecodeError:
            pass

    topics = kafka_exec(
        data_namespace,
        timeout_seconds,
        ["kafka-topics", "--bootstrap-server", "localhost:9092", "--list"],
        check=False,
    )
    pattern = re.compile(DEFAULT_TOPIC_PATTERN)
    matches = sorted(t for t in topics.splitlines() if pattern.match(t))
    if not matches:
        raise RuntimeError("could not resolve scoring Sequence KafkaChannel backing topic")
    return matches[-1]


def matching_groups(data_namespace: str, timeout_seconds: int) -> list[str]:
    text = kafka_exec(
        data_namespace,
        timeout_seconds,
        ["kafka-consumer-groups", "--bootstrap-server", "localhost:9092", "--list"],
        check=False,
    )
    return sorted(g for g in text.splitlines() if g.startswith(GROUP_PREFIX))


def capture(args: argparse.Namespace) -> dict[str, Any]:
    topic = args.topic or resolve_backing_topic(args.kserve_namespace, args.data_namespace, args.timeout_seconds)
    earliest = parse_offsets(
        kafka_exec(
            args.data_namespace,
            args.timeout_seconds,
            [
                "kafka-get-offsets",
                "--bootstrap-server",
                "localhost:9092",
                "--topic",
                topic,
                "--time",
                "earliest",
            ],
        )
    )
    latest = parse_offsets(
        kafka_exec(
            args.data_namespace,
            args.timeout_seconds,
            [
                "kafka-get-offsets",
                "--bootstrap-server",
                "localhost:9092",
                "--topic",
                topic,
                "--time",
                "latest",
            ],
        )
    )

    groups: dict[str, Any] = {}
    selected_group = ""
    selected_rows: list[dict[str, Any]] = []
    for group in matching_groups(args.data_namespace, args.timeout_seconds):
        described = kafka_exec(
            args.data_namespace,
            args.timeout_seconds,
            [
                "kafka-consumer-groups",
                "--bootstrap-server",
                "localhost:9092",
                "--describe",
                "--group",
                group,
            ],
            check=False,
        )
        rows = [row for row in parse_group_describe(described) if row["topic"] == topic]
        groups[group] = {"assignments": rows}
        if rows and not selected_group:
            selected_group = group
            selected_rows = rows

    committed_by_partition = {
        int(row["partition"]): row["current_offset"] for row in selected_rows if row["current_offset"] is not None
    }
    partitions = []
    for partition in sorted(set(earliest) | set(latest) | set(committed_by_partition)):
        row = partition_lag(
            earliest=earliest.get(partition, 0),
            latest=latest.get(partition, earliest.get(partition, 0)),
            committed=committed_by_partition.get(partition),
        )
        row["partition"] = partition
        partitions.append(row)

    totals = {
        "raw_lag": sum(int(row["raw_lag"]) for row in partitions),
        "stale_lag": sum(int(row["stale_lag"]) for row in partitions),
        "effective_lag": sum(int(row["effective_lag"]) for row in partitions),
        "partitions": len(partitions),
    }
    return {
        "phase": args.phase,
        "captured_at_epoch": time.time(),
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kserve_namespace": args.kserve_namespace,
        "data_namespace": args.data_namespace,
        "channel": "scoring-pipeline-kn-sequence-0",
        "topic": topic,
        "selected_group": selected_group,
        "groups": groups,
        "partitions": partitions,
        "totals": totals,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    totals = payload["totals"]
    lines = [
        f"## KafkaChannel Offsets: {payload['phase']}",
        "",
        f"- Captured: {payload['captured_at_utc']}",
        f"- Topic: `{payload['topic']}`",
        f"- Selected group: `{payload.get('selected_group') or 'none'}`",
        f"- Effective lag: {totals['effective_lag']}",
        f"- Stale lag: {totals['stale_lag']}",
        f"- Raw lag: {totals['raw_lag']}",
        "",
        "| Partition | Earliest | Latest | Committed | Raw lag | Stale lag | Effective lag |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["partitions"]:
        lines.append(
            "| {partition} | {earliest} | {latest} | {committed} | {raw_lag} | {stale_lag} | {effective_lag} |".format(
                **{**row, "committed": row["committed"] if row["committed"] is not None else ""}
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown")
    parser.add_argument("--phase", default="snapshot")
    parser.add_argument("--topic", default="")
    parser.add_argument("--kserve-namespace", default="kserve")
    parser.add_argument("--data-namespace", default="data-services")
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--max-effective-lag", type=int)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = capture(args)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        write_markdown(Path(args.markdown), payload)

    effective_lag = int(payload["totals"]["effective_lag"])
    print(f"{payload['phase']}: topic={payload['topic']} effective_lag={effective_lag} stale_lag={payload['totals']['stale_lag']}")
    if args.max_effective_lag is not None and effective_lag > args.max_effective_lag:
        sys.stderr.write(
            f"effective KafkaChannel lag {effective_lag} exceeds threshold {args.max_effective_lag}\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
