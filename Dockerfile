FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y sqlite3 gosu && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 -U -s /bin/bash appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app /home/appuser && \
    chmod +x /app/scripts/entrypoint.sh
ENV DATA_DIR=/app/data \
    DATABASE_PATH=/app/data/planner.db \
    PORT=5000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_THREADS=1
EXPOSE 5000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
# Railway injects $PORT; locally it defaults to 5000. WEB_CONCURRENCY=2 fits the 0.5 GB Free plan.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY} --threads ${GUNICORN_THREADS} --timeout 120 app:app"]
