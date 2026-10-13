FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir . && useradd --system --uid 10001 aarogya
USER aarogya
EXPOSE 8000
# Migrations and reference-data sync run before the server starts.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli seed && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
