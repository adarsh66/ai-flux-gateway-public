FROM python:3.11-slim-bookworm
LABEL com.azure.containerizationassist.createdby="containerization-assist"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Metadata freshness is independent of the persistent POC's no-expiry policy.
# Operators must refresh real deployment evidence; never restamp old evidence.
ENV AIFLUX_FOUNDRY_INVENTORY_PATH=/app/gateway/catalog/foundry-inventory-20261026.json \
    AIFLUX_EXTERNAL_INVENTORY_PATH=/app/gateway/catalog/external-inventory.json \
    AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS=86400 \
    AIFLUX_GATEWAY_MAX_COMPLETION_TOKENS=1024
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unixodbc \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /app/ms.deb \
    && dpkg -i /app/ms.deb && rm /app/ms.deb \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY services/control-plane ./services/control-plane
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home aiflux
COPY gateway/catalog ./gateway/catalog
COPY gateway/policies/settings-unconfigured.xml ./gateway/policies/settings-unconfigured.xml
USER aiflux
EXPOSE 8000
HEALTHCHECK CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "aiflux.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
