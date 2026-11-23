#!/usr/bin/env python3
"""Write the heading-only pages that mirror the project README's table of contents.

The README's detail is out of date (the flow is being reworked), so each page keeps only the
README's heading, says so, lists the planned scope and links to pages that are current.
Run once; the generated files are committed so they can be edited by hand afterwards.
"""
from pathlib import Path

B = "/credit-risk-ml-system"
OUT = Path(__file__).resolve().parents[1] / "src/content/docs/guide"

PAGES = [
    ("business-objective", "Business objective", [
        "The problem with manual credit assessment",
        "The proposed solution: an automated, explainable decision",
        "Key goals: speed, consistency, scalability, transparency, operational readiness",
    ], [("Business outcomes (current)", "delivery/business-outcomes"), ("Epics", "delivery/epics")]),
    ("results", "Results", [
        "Model quality on a held-out set, and the dataset it was measured on",
        "Load-test state of the pipeline",
        "Independent check against the public leaderboard",
    ], [("Technical report (draft)", "report")]),
    ("quick-start-ml-only", "Quick start (ML only)", [
        "Generate the merged feature dataset from the raw files",
        "Train and register the model",
        "Explore the evaluation results",
    ], [("Data definition", "ml/data-definition")]),
    ("prerequisites", "Prerequisites", ["Tools, versions and resources needed to run the project"], []),
    ("local-development-no-kubernetes", "Local development (no Kubernetes)", [
        "Install dependencies and configure the environment",
        "Start the database and run the API",
        "Run the tests",
    ], [("Threat model", "security/threat-model")]),
    ("verify-end-to-end", "Verify end to end", [
        "Check health, submit a test application, confirm the change event, read the status",
    ], [("Runtime flows", "architecture/c4/flows")]),
    ("project-structure", "Project structure", [
        "What each top-level folder owns and how it is built and deployed",
    ], [("ADR-0011 · Monorepo layout", "decisions/0011-monorepo-layout")]),
    ("testing", "Testing", [
        "Unit and integration tests, load tests, and the coverage gates in CI",
    ], [("Release checklist", "ops/release-checklist")]),
    ("performance-optimization-log", "Performance optimization log", [
        "What each load-test iteration found and what was changed",
    ], [("ADR-0008 · Load-test fixes", "decisions/0008-load-test-fixes")]),
    ("troubleshooting", "Troubleshooting", [
        "Kafka image pull timeout on first run",
        "Feast pods in CrashLoopBackOff",
        "Elasticsearch or Prometheus stuck in Pending",
        "API pods in ImagePullBackOff",
        "Minikube IP change after a restart",
        "Starting fresh",
    ], [("Runbooks", "ops/runbooks")]),
    ("operations", "Operations", [
        "Restarting, cleaning, rebuilding serving after a promotion, feature backfill",
    ], [("Runbooks", "ops/runbooks"), ("Resilience and failover (E15)", "ops/e15-resilience-failover")]),
    ("dataset", "Dataset", [
        "The source data, its tables and how they relate",
    ], [("Data definition", "ml/data-definition")]),
    ("notebooks", "Notebooks", [
        "Exploration, modelling and evaluation notebooks and what each answers",
    ], [("Modeling references", "ml/modeling-references")]),
    ("future-development", "Future development", [
        "Managed Kubernetes, rules engine, authentication, dashboards, replicas, consumers, document extraction",
    ], [("Epics", "delivery/epics"), ("Release checklist", "ops/release-checklist")]),
    ("reference", "Reference", ["Articles and sources behind the design"], [("References", "references")]),
    ("assumptions", "Assumptions", ["Processing-time target and the other assumptions the design rests on"], []),
]

PHASES = [
    ("phase-1-cluster", "Phase 1 · Cluster"),
    ("phase-2-build-images", "Phase 2 · Build application images"),
    ("phase-3-core-data-platform", "Phase 3 · Core data platform"),
    ("phase-4-stream-processing", "Phase 4 · Stream processing"),
    ("phase-5-warehouse-load", "Phase 5 · Data warehouse load"),
    ("phase-6-ml-platform", "Phase 6 · ML platform"),
    ("phase-7-training-infrastructure", "Phase 7 · Training infrastructure"),
    ("phase-8-observability", "Phase 8 · Observability (optional)"),
    ("phase-9-port-forwards", "Phase 9 · Port forwards"),
]


def page(slug, title, scope, related, extra_related=()):
    lines = ["---", f"title: {title}", "description: Draft page that keeps only the README heading; content is being rewritten.",
             "sidebar:", "  badge:", "    text: draft", "    variant: default", "---", "",
             ":::note[Draft: heading only]",
             "This page keeps the heading from the project README. The README's detail is out of date because the flow is changing "
             "(portals, identity, audit, explainability), so the content will be rewritten and reviewed before it is filled in.",
             ":::", "", "## Planned scope", ""]
    lines += [f"- {item}" for item in scope]
    rel = list(related) + list(extra_related)
    if rel:
        lines += ["", "## Current pages on this topic", ""]
        lines += [f"- [{label}]({B}/{target}/)" for label, target in rel]
    return "\n".join(lines) + "\n"


for slug, title, scope, related in PAGES:
    (OUT / f"{slug}.md").write_text(page(slug, title, scope, related))

# Full stack deployment: an overview page and one page per phase.
phase_links = [(t, f"guide/full-stack-deployment/{s}") for s, t in PHASES]
(OUT / "full-stack-deployment").mkdir(exist_ok=True)
(OUT / "full-stack-deployment" / "index.md").write_text(page(
    "full-stack-deployment", "Full stack deployment",
    ["Nine phases from an empty machine to a running platform, with the checks after each phase"],
    [("Deployment view (C4)", "architecture/c4/deployment"), ("Deployment reference", "architecture/reference/deployment")],
    phase_links))
for s, t in PHASES:
    (OUT / "full-stack-deployment" / f"{s}.md").write_text(page(s, t, ["Steps, expected pods and checks for this phase"],
                                                               [("Full stack deployment", "guide/full-stack-deployment")]))
(OUT / "license.md").write_text("""---
title: License
description: The project is released under the MIT License.
---

This project is licensed under the MIT License. See [LICENSE](https://github.com/ngnquanq/credit-risk-ml-system/blob/master/LICENSE) in the repository.
""")
print(len(PAGES) + len(PHASES) + 2, "pages written")
