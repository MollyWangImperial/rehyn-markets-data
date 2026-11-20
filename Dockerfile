# The cloud worker: request watcher, 15 minute news sentiment and the daily collector (ingest/worker.py).
# data/ is the service's persistent disk, mounted at /app/data.
FROM python:3.13.5-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1

# tini reaps finished child processes, so a stopped watcher never lingers as a zombie that still looks alive.
# magic-wormhole is for copying files onto the disk from the dashboard shell; ~/.ssh is needed for Render SSH and scp.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini magic-wormhole \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /root/.ssh && chmod 0700 /root/.ssh

WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
 && pip install -r requirements-worker.txt

COPY ingest ingest
COPY schema schema

ENTRYPOINT ["tini", "--"]
CMD ["python", "-I", "ingest/worker.py"]
