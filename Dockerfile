# Simulator Coretax DJP — container image
#
# Prinsip:
#  - Non-root user (uid 10001) — tidak ada akses root di dalam container
#  - Multi-stage build: builder + runtime, runtime tanpa compiler
#  - Dependency di-pin (requirements.txt) supaya build reproducible
#  - Data aplikasi di volume, bukan di dalam image
#  - Healthcheck built-in
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim AS runtime

# - no shell interaktif, no cache apt
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app.py models.py security.py tax.py seed.py reset_db.py entrypoint.sh ./
COPY static ./static
COPY docs ./docs
COPY README.md ./

# Data SQLite -> volume (bukan layer image)
RUN mkdir -p /app/data && chown -R app:app /app \
 && chmod +x /app/entrypoint.sh

USER app:app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CORETAX_MODE=demo \
    CORETAX_DATA_DIR=/app/data

VOLUME ["/app/data"]
EXPOSE 8140

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8140/healthz', timeout=3).status==200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8140"]
