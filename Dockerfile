FROM continuumio/miniconda3:latest

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/opt/conda/envs/ifc-export-service/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY environment.yml /app/
RUN conda env create -f environment.yml && conda clean -afy

COPY app/ /app/app/
COPY run.py /app/
COPY tests/ /app/tests/
COPY pytest.ini /app/

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
