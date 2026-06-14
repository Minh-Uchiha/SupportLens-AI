FROM python:3.12-slim
WORKDIR /app
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/api/app ./apps/api/app
COPY workers ./workers
RUN pip install --no-cache-dir -e ./apps/api
ENV PYTHONPATH=/app:/app/apps/api
CMD ["python", "-m", "workers.ingestion.main"]
