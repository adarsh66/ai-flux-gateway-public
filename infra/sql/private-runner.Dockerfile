# Required: the reviewed existing control-plane API image (prefer an immutable digest).
# Build context is the repository root. No packages, Azure CLI or credentials added.
ARG API_IMAGE
FROM ${API_IMAGE}
WORKDIR /app
COPY --chown=10001:10001 scripts/deployment/private_sql_job.py /app/scripts/deployment/private_sql_job.py
USER 10001:10001
ENTRYPOINT ["python", "/app/scripts/deployment/private_sql_job.py"]
# Clear the API image's inherited uvicorn arguments.
CMD []