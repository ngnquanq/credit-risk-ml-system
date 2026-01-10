import os
import time
import logging
import subprocess
import tempfile
from typing import List, Set
from kubernetes import client as k8s, config as k8s_config
import yaml
import boto3

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("serving-watcher")

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://serving-minio.model-serving.svc.cluster.local:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio_user")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio_password")
BUCKET_NAME = os.getenv("BUCKET_NAME", "bentoml-bundles")
BENTO_PREFIX = os.getenv("BENTO_PREFIX", "bentos/credit_risk_model")
REGISTRY_URL = os.getenv("REGISTRY_URL", "docker-registry.model-serving.svc.cluster.local:5000")
IMAGE_NAME = os.getenv("IMAGE_NAME", "credit-risk-scoring")
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "30"))
MAX_ACTIVE_MODELS = int(os.getenv("MAX_ACTIVE_MODELS", "2"))
KSERVE_NAMESPACE = os.getenv("KSERVE_NAMESPACE", "kserve")

# Track deployed versions
deployed_versions: Set[str] = set()

def sh(cmd: str, check=True, **kwargs):
    """Execute shell command."""
    log.info(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True, **kwargs)
    if result.stdout:
        log.info(result.stdout)
    if result.stderr:
        log.error(result.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result

def list_bento_versions() -> List[str]:
    """List all Bento versions in MinIO using boto3."""
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY
        )

        prefix = f"{BENTO_PREFIX}/"
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')

        versions = []
        for common_prefix in response.get('CommonPrefixes', []):
            path = common_prefix['Prefix']
            version = path.rstrip('/').split('/')[-1]
            if version.startswith('v'):
                versions.append(version)

        versions.sort(key=lambda v: int(v[1:]) if v[1:].isdigit() else 0, reverse=True)
        return versions
    except Exception as e:
        log.error(f"Failed to list Bento versions: {e}")
        return []

def build_and_push_image(version: str) -> bool:
    """Download Bento, build Docker image, and push to registry."""
    try:
        log.info(f"Building image for version {version}")

        with tempfile.TemporaryDirectory() as tmpdir:
            bento_dir = os.path.join(tmpdir, version)
            os.makedirs(bento_dir, exist_ok=True)

            # Download Bento from MinIO using boto3
            log.info(f"Downloading Bento {version} from MinIO")
            s3 = boto3.client(
                's3',
                endpoint_url=MINIO_ENDPOINT,
                aws_access_key_id=MINIO_ACCESS_KEY,
                aws_secret_access_key=MINIO_SECRET_KEY
            )

            prefix = f"{BENTO_PREFIX}/{version}/"
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    rel_path = key[len(prefix):]
                    if not rel_path:
                        continue
                    local_file = os.path.join(bento_dir, rel_path)
                    os.makedirs(os.path.dirname(local_file), exist_ok=True)
                    s3.download_file(BUCKET_NAME, key, local_file)

            # Check if Dockerfile exists
            dockerfile_path = os.path.join(bento_dir, "env/docker/Dockerfile")
            if not os.path.exists(dockerfile_path):
                log.error(f"Dockerfile not found at {dockerfile_path}")
                return False

            # Fix BentoML Dockerfile issues
            log.info("Patching Dockerfile to fix $BENTO_PATH variable and uv command")
            with open(dockerfile_path, 'r') as f:
                dockerfile_content = f.read()

            # Replace $BENTO_PATH with the actual path
            dockerfile_content = dockerfile_content.replace('$BENTO_PATH', '/home/bentoml/bento')

            # Fix uv command - replace with regular pip install
            # Original: uv --directory $INSTALL_ROOT pip install -r /home/bentoml/bento/env/python/requirements.txt
            # New: pip install -r /home/bentoml/bento/env/python/requirements.txt
            dockerfile_content = dockerfile_content.replace(
                'uv --directory $INSTALL_ROOT pip install -r',
                'pip install --no-cache-dir -r'
            )

            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            log.info("Dockerfile patched successfully")

            # Debug: List bento directory structure and check for requirements.txt
            log.info("Bento directory structure:")
            env_python_path = os.path.join(bento_dir, "env/python")
            env_python_requirements = os.path.join(env_python_path, "requirements.txt")

            log.info(f"Checking for env/python/requirements.txt:")
            log.info(f"  env/python exists: {os.path.exists(env_python_path)}")
            log.info(f"  requirements.txt exists: {os.path.exists(env_python_requirements)}")

            if os.path.exists(env_python_path):
                log.info(f"  Contents of env/python/:")
                for item in os.listdir(env_python_path):
                    log.info(f"    - {item}")

            # If requirements.txt doesn't exist, create it from bentofile.yaml
            if not os.path.exists(env_python_requirements):
                log.info("requirements.txt not found, attempting to generate from bentofile.yaml")
                bentofile_path = os.path.join(bento_dir, "src/bentofile.yaml")
                if os.path.exists(bentofile_path):
                    import yaml
                    with open(bentofile_path, 'r') as f:
                        bentofile = yaml.safe_load(f)

                    packages = bentofile.get('python', {}).get('packages', [])
                    if packages:
                        os.makedirs(env_python_path, exist_ok=True)
                        with open(env_python_requirements, 'w') as f:
                            f.write('\n'.join(packages) + '\n')
                        log.info(f"Created requirements.txt with {len(packages)} packages")
                    else:
                        log.error("No packages found in bentofile.yaml")
                else:
                    log.error(f"bentofile.yaml not found at {bentofile_path}")

            # Login to Docker Hub if credentials provided
            username = os.getenv("DOCKER_USERNAME")
            password = os.getenv("DOCKER_PASSWORD")
            if username and password:
                log.info("Logging in to Docker Hub")
                login_result = subprocess.run(
                    f"docker login -u {username} -p {password}",
                    shell=True,
                    capture_output=True
                )
                if login_result.returncode == 0:
                    log.info("Docker Hub login successful")
                else:
                    log.warning("Docker Hub login failed, push may fail")

            # Build Docker image with both version tag and latest tag
            image_tag = f"{REGISTRY_URL}/{IMAGE_NAME}:{version}"
            image_tag_latest = f"{REGISTRY_URL}/{IMAGE_NAME}:latest"
            log.info(f"Building Docker image: {image_tag} and {image_tag_latest}")
            result = subprocess.run(
                f"docker build --no-cache -t {image_tag} -t {image_tag_latest} -f {dockerfile_path} {bento_dir}",
                shell=True,
                check=True
            )
            log.info(f"Build exit code: {result.returncode}")

            # Push both tags to Docker Hub
            log.info(f"Pushing image to Docker Hub: {image_tag}")
            sh(f"docker push {image_tag}")
            log.info(f"Pushing latest tag to Docker Hub: {image_tag_latest}")
            sh(f"docker push {image_tag_latest}")

            log.info(f"Successfully built and pushed {image_tag}")
            return True

    except Exception as e:
        log.error(f"Failed to build/push image for {version}: {e}")
        return False



def create_or_update_kafkasource(isvc_name: str, namespace: str) -> bool:
    """Create or update KafkaSource to route events to latest InferenceService."""
    try:
        k8s_config.load_incluster_config()
        custom_api = k8s.CustomObjectsApi()

        kafka_source_name = "feature-ready-source"

        kafka_source = {
            "apiVersion": "sources.knative.dev/v1beta1",
            "kind": "KafkaSource",
            "metadata": {
                "name": kafka_source_name,
                "namespace": namespace
            },
            "spec": {
                "bootstrapServers": ["host.minikube.internal:39092"],
                "topics": ["hc.feature_ready"],
                "consumerGroup": "knative-scoring-consumer",
                "consumers": 1,
                "initialOffset": "latest",
                "sink": {
                    "ref": {
                        "apiVersion": "serving.kserve.io/v1beta1",
                        "kind": "InferenceService",
                        "name": isvc_name
                    },
                    "uri": "/v1/score-by-id"
                },
                "delivery": {
                    "deadLetterSink": {
                        "ref": {
                            "apiVersion": "eventing.knative.dev/v1alpha1",
                            "kind": "KafkaSink",
                            "name": "scoring-dlq-sink"
                        }
                    },
                    "retry": 3,
                    "backoffPolicy": "exponential",
                    "backoffDelay": "PT1S"
                },
                "resources": {
                    "requests": {"cpu": "100m", "memory": "128Mi"},
                    "limits": {"cpu": "200m", "memory": "256Mi"}
                }
            }
        }

        try:
            existing = custom_api.get_namespaced_custom_object(
                group="sources.knative.dev",
                version="v1beta1",
                namespace=namespace,
                plural="kafkasources",
                name=kafka_source_name
            )
            log.info(f"Updating KafkaSource {kafka_source_name} → {isvc_name}")
            custom_api.patch_namespaced_custom_object(
                group="sources.knative.dev",
                version="v1beta1",
                namespace=namespace,
                plural="kafkasources",
                name=kafka_source_name,
                body=kafka_source
            )
        except k8s.rest.ApiException as e:
            if e.status == 404:
                log.info(f"Creating KafkaSource {kafka_source_name} → {isvc_name}")
                custom_api.create_namespaced_custom_object(
                    group="sources.knative.dev",
                    version="v1beta1",
                    namespace=namespace,
                    plural="kafkasources",
                    body=kafka_source
                )
            else:
                raise

        return True

    except Exception as e:
        log.error(f"Failed to create/update KafkaSource: {e}")
        return False


def create_or_update_inferenceservice(version: str) -> bool:
    """Create or update KServe InferenceService for a version."""
    try:
        k8s_config.load_incluster_config()
        custom_api = k8s.CustomObjectsApi()

        service_name = f"credit-risk-{version}"
        image_uri = f"{REGISTRY_URL}/{IMAGE_NAME}:latest"

        # Load InferenceService template from YAML file (serverless mode)
        template_path = os.path.join(os.path.dirname(__file__), "isvc-template-serverless.yaml")
        with open(template_path, 'r') as f:
            template_content = f.read()

        # Substitute variables
        from string import Template
        template = Template(template_content)
        yaml_content = template.substitute(
            SERVICE_NAME=service_name,
            NAMESPACE=KSERVE_NAMESPACE,
            VERSION=version,
            IMAGE_URI=image_uri
        )

        # Parse YAML to dictionary
        isvc = yaml.safe_load(yaml_content)

        # Try to get existing InferenceService
        try:
            existing = custom_api.get_namespaced_custom_object(
                group="serving.kserve.io",
                version="v1beta1",
                namespace=KSERVE_NAMESPACE,
                plural="inferenceservices",
                name=service_name
            )
            # Update existing
            log.info(f"Updating InferenceService {service_name}")
            custom_api.patch_namespaced_custom_object(
                group="serving.kserve.io",
                version="v1beta1",
                namespace=KSERVE_NAMESPACE,
                plural="inferenceservices",
                name=service_name,
                body=isvc
            )
        except k8s.rest.ApiException as e:
            if e.status == 404:
                # Create new
                log.info(f"Creating InferenceService {service_name}")
                custom_api.create_namespaced_custom_object(
                    group="serving.kserve.io",
                    version="v1beta1",
                    namespace=KSERVE_NAMESPACE,
                    plural="inferenceservices",
                    body=isvc
                )
            else:
                raise

        log.info(f"InferenceService {service_name} ready")
        return True

    except Exception as e:
        log.error(f"Failed to create/update InferenceService for {version}: {e}")
        return False

def delete_inferenceservice(version: str) -> bool:
    """Delete KServe InferenceService."""
    try:
        k8s_config.load_incluster_config()
        custom_api = k8s.CustomObjectsApi()

        service_name = f"credit-risk-{version}"

        log.info(f"Deleting InferenceService {service_name}")
        custom_api.delete_namespaced_custom_object(
            group="serving.kserve.io",
            version="v1beta1",
            namespace=KSERVE_NAMESPACE,
            plural="inferenceservices",
            name=service_name
        )
        return True
    except k8s.rest.ApiException as e:
        if e.status == 404:
            log.info(f"InferenceService {service_name} already deleted")
            return True
        log.error(f"Failed to delete InferenceService {service_name}: {e}")
        return False

def reconcile() -> None:
    """Reconcile serving state: ensure top-N versions are deployed."""
    global deployed_versions

    # Get all available Bento versions from MinIO
    available_versions = list_bento_versions()
    if not available_versions:
        log.info("No Bento versions found in MinIO")
        return

    log.info(f"Found {len(available_versions)} Bento versions: {available_versions}")

    # Determine top-N versions to deploy
    target_versions = set(available_versions[:MAX_ACTIVE_MODELS])
    log.info(f"Target versions to deploy: {target_versions}")

    # Deploy new versions
    latest_version = None
    for version in target_versions:
        if version not in deployed_versions:
            log.info(f"New version detected: {version}")
            if build_and_push_image(version):
                if create_or_update_inferenceservice(version):
                    deployed_versions.add(version)
                    latest_version = version

    # Update KafkaSource to point to latest version
    if latest_version:
        service_name = f"credit-risk-{latest_version}"
        create_or_update_kafkasource(service_name, KSERVE_NAMESPACE)

    # Remove old versions
    versions_to_remove = deployed_versions - target_versions
    for version in versions_to_remove:
        log.info(f"Removing old version: {version}")
        if delete_inferenceservice(version):
            deployed_versions.discard(version)

    log.info(f"Active deployed versions: {deployed_versions}")

def main():
    log.info(
        "Starting serving watcher: bucket=%s prefix=%s max_active=%d",
        BUCKET_NAME,
        BENTO_PREFIX,
        MAX_ACTIVE_MODELS
    )

    while True:
        try:
            reconcile()
        except Exception as e:
            log.error(f"Reconciliation error: {e}")
        time.sleep(POLL_INTERVAL_SECS)

if __name__ == "__main__":
    main()
