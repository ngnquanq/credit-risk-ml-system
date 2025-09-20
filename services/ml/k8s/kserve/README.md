# KServe Quickstart (Pinned, minimal)

This folder contains minimal manifests to deploy models with KServe using MinIO/S3 for model storage. It assumes you use the `model-serving` namespace.

## Prerequisites
- Kubernetes cluster with `kubectl` and `helm`.
- `cert-manager` installed (e.g., v1.13.x).
- Knative Serving with Kourier or Istio as ingress.
- KServe core + runtimes.

## Recommended pinned versions
- Knative Operator/Serving: v1.13.x
- net-kourier: v1.13.x
- KServe: v0.12.x (or the version matching your cluster)

## Install steps (copy/paste)

1) Install cert-manager (if not already):

```
helm repo add jetstack https://charts.jetstack.io && helm repo update
kubectl create ns cert-manager || true
helm upgrade --install cert-manager jetstack/cert-manager -n cert-manager \
  --version v1.13.5 --set installCRDs=true
```

2) Install Knative Operator and Serving (Kourier ingress):

```
# Operator
kubectl apply -f https://github.com/knative/operator/releases/download/knative-v1.13.0/operator.yaml

# Knative Serving CR (uses Kourier)
kubectl create ns knative-serving || true
kubectl apply -f - <<'EOF'
apiVersion: operator.knative.dev/v1beta1
kind: KnativeServing
metadata:
  name: knative-serving
  namespace: knative-serving
spec:
  ingress:
    kourier:
      enabled: true
  config:
    network:
      ingress-class: "kourier.ingress.networking.knative.dev"
EOF

# net-kourier (data plane)
kubectl apply -f https://github.com/knative/net-kourier/releases/download/knative-v1.13.0/kourier.yaml

# Point Knative to Kourier service as external ingress
kubectl -n knative-serving patch configmap/config-network \
  --type merge -p '{"data":{"ingress.class":"kourier.ingress.networking.knative.dev"}}'
```

3) Install KServe core and runtimes (pin a version):

```
# Core
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.12.1/kserve.yaml
# Model runtimes (SKLearn/XGBoost/TensorFlow/PyTorch/Triton)
kubectl apply -f https://github.com/kserve/kserve/releases/download/v0.12.1/kserve-runtimes.yaml
```

4) Configure S3/MinIO credentials (edit before applying):

- Edit `secret-s3.example.yaml` with your MinIO endpoint and credentials.
- Apply the Secret and ServiceAccount:

```
kubectl apply -f services/ml/k8s/kserve/secret-s3.example.yaml
kubectl apply -f services/ml/k8s/kserve/serviceaccount.example.yaml
```

5) Deploy a model (edit storageUri):

- Edit `inferenceservice.sklearn.example.yaml` and set `storageUri` to your S3 path.
- Apply:

```
kubectl apply -f services/ml/k8s/kserve/inferenceservice.sklearn.example.yaml
```

6) Access the service

- Get the URL:
```
kubectl get ksvc -n model-serving
```
- For local clusters without LoadBalancer, port-forward Kourier:
```
kubectl -n kourier-system port-forward svc/kourier 8080:80
```
- Then call the predictor: `curl -v http://localhost:8080/v1/models/<name>:predict`

## Vendor-locking
To vendor-lock upstream manifests, download the exact release YAMLs above into `services/ml/k8s/kserve/vendor/` and install from files instead of remote URLs.

