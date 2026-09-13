# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY src/ ./src/
COPY assets/ /app/assets/
COPY locales/ ./locales/
COPY .env.example ./.env.example

RUN mkdir -p /app/data && chown -R app:app /app

USER app

VOLUME ["/app/data"]

CMD ["python", "main.py"]
