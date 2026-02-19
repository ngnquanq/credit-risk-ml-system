# MetalLB setup for MinIO LoadBalancer on Minikube

Purpose
- Provide a routable external IP (LoadBalancer) for the MinIO Service so external systems (ClickHouse in Docker) can access it.

Steps (Minikube)
1) Enable MetalLB addon:
   minikube addons enable metallb

2) Configure address pool:
   Your addon version (v0.9.x in Minikube) uses a ConfigMap, not CRDs. Apply:

   kubectl apply -f services/ml/k8s/training-data-storage/metallb/configmap.yaml

   This allocates 192.168.49.200–192.168.49.250 on the Minikube subnet. Adjust if needed.

   Note: If you run a newer standalone MetalLB (>=0.13), use ippool.yaml (CRDs) instead.

3) Deploy/upgrade MinIO with LoadBalancer type (already configured in minio.values.yaml):
   helm upgrade --install training-minio ./services/ml/k8s/training-data-storage \
     -n training-data -f services/ml/k8s/training-data-storage/minio.values.yaml

4) Get the external IP:
   kubectl -n training-data get svc training-minio

   Use http://<EXTERNAL-IP>:9000 as the S3 endpoint from ClickHouse.

Notes
- If the EXTERNAL-IP stays pending, check that MetalLB pods are running (kubectl -n metallb-system get pods) and that the IP pool matches your Minikube subnet.
- For production clusters, configure MetalLB according to your network and security policies, or use your cloud provider’s native LoadBalancer.
