FROM continuumio/miniconda3:latest

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/opt/conda/envs/ifc-export-service/bin:$PATH

# Copy environment.yml first to leverage Docker cache
COPY environment.yml .

# Install system deps, create conda env, then clean up build tools in a single layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && conda env create -f environment.yml \
    && conda clean -afy \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && find /opt/conda -name '*.a' -delete \
    && find /opt/conda -name '*.pyc' -delete \
    && find /opt/conda -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /opt/conda/pkgs/*

# Copy only production files
COPY app/ ./app/
COPY run.py .
COPY VERSION .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8004
ENV PORT=8004

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

SHELL ["/bin/bash", "-c"]
CMD source activate ifc-export-service && gunicorn app.main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT} \
    --forwarded-allow-ips='*' \
    --timeout 300
