# Environments (ADR-0011)

Kustomize overlays over the manifests in `platform/<plane>/k8s/`. An environment differs from another only in its overlay: image digests, replicas, hosts and resource sizes. Secrets are never here; overlays reference Secret names created by `make k8s-secrets`, `make k8s-identity-secrets` and `make k8s-portals`.

| Overlay | Purpose |
|---|---|
| `dev/` | The Minikube stack as the Makefile deploys it today, plus identity, portals and the decision recorder |
| `uat/` | Same manifests in `uat-*` namespaces, images pinned by digest, synthetic data (E16) |

A release is a commit that changes the digests in `uat/` (and later `prod/`). Build once per commit, then promote the same digests.

```bash
kubectl kustomize platform/environments/uat | less       # review
kubectl apply -k platform/environments/uat               # deploy
```

Status: written, not yet applied. The overlays cover the components added for E5–E16; the older planes are still deployed by the Makefile targets.
