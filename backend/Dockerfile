FROM python:3.12.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; pip install --require-hashes -r /app/requirements.lock
COPY backend /app/backend
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; pip install --no-deps /app/backend && useradd --uid 10001 --create-home atlasops && chown -R atlasops:atlasops /app
USER atlasops
EXPOSE 8000
CMD ["uvicorn", "atlasops.main:app", "--host", "0.0.0.0", "--port", "8000"]
