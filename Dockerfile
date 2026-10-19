FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MOTOR_DB=/app/private_data/motor.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd --system motor && useradd --system --gid motor motor
COPY app app
COPY fixtures fixtures
COPY src src
COPY pyproject.toml README.md LICENSE.md ./
RUN mkdir -p private_data && chown -R motor:motor /app
USER motor
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
