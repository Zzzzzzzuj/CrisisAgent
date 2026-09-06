FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AGENT_MODE=mock
ENV CHECKPOINT_STORAGE=json
ENV RUNTIME_MODE=sync
ENV TASK_QUEUE_BACKEND=inprocess
ENV EMBEDDING_MODEL=hash
ENV VECTOR_BACKEND=json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY cases ./cases
COPY evaluation ./evaluation
COPY scripts ./scripts

RUN mkdir -p /app/backend/core/data

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
