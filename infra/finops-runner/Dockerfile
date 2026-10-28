FROM python:3.13-slim-bookworm@sha256:89c04d97d1f3f0a04ea357a27d000ba4efb18536d2d68a54611f76d5c1b5fe99
# Build context MUST be the isolated directory emitted by finops_runner_prepare.
# No application package, migrations, Azure CLI, credentials or repository copy.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /probe
COPY requirements.lock.txt ./
COPY wheels/ ./wheels/
RUN pip install --no-cache-dir --no-index --find-links=/probe/wheels --require-hashes -r requirements.lock.txt && pip check \
    && python -c "import azure.identity, psycopg, sqlalchemy; assert psycopg.pq.version() >= 120000"
COPY finops_private_probe.py entrypoint.py ./
COPY linux_contract.py ./
RUN chmod 0444 /probe/*.py && mkdir /scratch && chmod 0777 /scratch
USER 65532:65532
RUN python -I /probe/linux_contract.py
# A one-shot task has no server liveness endpoint. Never rerun the DB probe as a health check.
HEALTHCHECK NONE
ENTRYPOINT ["python", "-I", "/probe/entrypoint.py"]