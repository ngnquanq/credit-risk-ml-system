FROM python:3.11-slim

# Install dbt with ClickHouse adapter
RUN pip install --no-cache-dir dbt-core dbt-clickhouse

WORKDIR /dbt

# Copy the entire dbt project
COPY dbt_project.yml profiles.yml packages.yml package-lock.yml ./
COPY models/ models/
COPY macros/ macros/
COPY seeds/ seeds/
COPY snapshots/ snapshots/
COPY analyses/ analyses/
COPY tests/ tests/

# Install dbt packages (dbt_utils)
RUN dbt deps --project-dir . --profiles-dir .

# Default: run gold target
CMD ["dbt", "run", "--project-dir", ".", "--profiles-dir", ".", "--target", "gold"]
