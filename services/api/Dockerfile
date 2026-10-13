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
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
# The server does NOT migrate on start: with several replicas that races. Run migrations once per
# release as a separate step (`python -m alembic upgrade head`, then `python -m app.cli seed`);
# /ready stays unhealthy until the database matches this image, so an unmigrated rollout never
# receives traffic. Scheduled jobs use the same image: `python -m app.cli run-job NAME`.
# Audio streaming and live partial transcripts are held in process memory, so keep ONE worker per
# container and route a recording's WebSocket and its polling to the same container
# (see docs/OPERATIONS.md, "Known scaling limits").
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
