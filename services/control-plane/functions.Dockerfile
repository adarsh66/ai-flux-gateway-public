FROM mcr.microsoft.com/azure-functions/python:4.1055.150-0-python3.11
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GATEWAY_PUBLICATION_WORKER_ENABLED=false
WORKDIR /home/site/wwwroot
COPY pyproject.toml ./
COPY services/control-plane/src ./services/control-plane/src
RUN pip install --no-cache-dir .
COPY services/control-plane/functions/ ./
COPY gateway/policies/settings-unconfigured.xml ./gateway/policies/settings-unconfigured.xml
# Verify real imports, binding entry points and PostgreSQL driver during the build.
RUN python -c "import handlers, psycopg; from aiflux.publication_worker import reconcile_pending; assert callable(handlers.gateway_publication)"