FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
