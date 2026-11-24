# Feast apply job and stream materialiser. Build context: this folder.
#   docker build -t ngnquanq/feast-repo:<tag> services/feature-store/feast_repo
#
# Libraries go into the system Python (not a venv) so a login shell (`sh -lc`, used by the apply job)
# finds them: a login shell resets PATH.

FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt \
    # SQLAlchemy[mypy] (a Feast dependency) pulls in mypy, which is only a type checker.
    && rm -rf /install/lib/python3.11/site-packages/mypy /install/lib/python3.11/site-packages/mypyc \
              /install/lib/python3.11/site-packages/mypy-* /install/lib/python3.11/site-packages/mypy_extensions* \
              /install/lib/python3.11/site-packages/*__mypyc*.so \
    && find /install -name '__pycache__' -type d -prune -exec rm -rf {} +

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/work
# Build tools are not needed at run time.
RUN pip uninstall -y pip setuptools wheel >/dev/null 2>&1; useradd --system --uid 10001 --no-create-home feast
COPY --from=builder /install /usr/local
WORKDIR /work
# Only the files the two commands use. feature_store.yaml comes from the feast-store-config ConfigMap.
COPY --chown=feast:feast entities.py feature_views.py feature_services.py schema_loaders.py repository.py stream_processor.py redis_coordination.lua ./
COPY --chown=feast:feast feature_schema/ ./feature_schema/
USER feast
CMD ["python", "repository.py"]
