FROM mcr.microsoft.com/azure-functions/python:4.1055.150-0-python3.11
# checkov:skip=CKV_DOCKER_3:Scoped compatibility exception preserving the existing pinned Functions base runtime user; non-root startup for this exact base is not verified. See docs/finops-functions-container-security-20261027.md. No new privileges or SSH.
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /home/site/wwwroot
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unixodbc \
    && . /etc/os-release \
    && curl -fsSL "https://packages.microsoft.com/config/debian/${VERSION_ID}/packages-microsoft-prod.deb" -o /tmp/ms.deb \
    && dpkg -i /tmp/ms.deb && rm /tmp/ms.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY services/control-plane ./services/control-plane
RUN pip install --no-cache-dir .
RUN python -c "import pyodbc; assert 'ODBC Driver 18 for SQL Server' in pyodbc.drivers()"
COPY services/usage-ingestion/handlers.py services/usage-ingestion/runtime_check.py services/usage-ingestion/host.json ./
COPY services/usage-ingestion/ingest_usage ./ingest_usage
COPY services/usage-ingestion/ingestion_ready ./ingestion_ready
COPY services/usage-ingestion/ingestion-approved.json ./gateway/catalog/dev-models.json
COPY services/usage-ingestion/ingestion-approved.json ./gateway/catalog/ingestion-approved.json
COPY gateway/catalog/foundry-inventory-20261026.json gateway/catalog/project-routes.json gateway/catalog/external-inventory.json ./gateway/catalog/
COPY gateway/catalog/fireworks-candidate-routes.json ./gateway/catalog/
COPY services/usage-ingestion/approved_catalog.py services/usage-ingestion/catalog-bindings.json ./services/usage-ingestion/
RUN python services/usage-ingestion/approved_catalog.py \
    && python -c "import azure.functions, azure.identity, azure.monitor.query, psycopg; from aiflux.ingestion import extract_usage; from aiflux.config import Settings; s=Settings(_env_file=None, environment='development', ingestion_start_at='2026-10-27T00:00:00Z'); assert s.ingestion_start_at.tzinfo"
# Listener liveness only: no authentication material, database or ingestion claim.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 80), timeout=3).close()"
# Exercise the exact probe primitive on Linux without starting a timer or using MI.
RUN python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',80)); s.listen(1); socket.create_connection(('127.0.0.1',80),timeout=3).close(); s.close(); print('TCP_HEALTHCHECK_LINUX_CONTRACT=passed')"
