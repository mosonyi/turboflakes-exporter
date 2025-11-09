FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Install wget for healthcheck (and CA certs for HTTPS)
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates \
 && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY exporter/app.py /app/exporter.py

EXPOSE 9101
CMD ["python", "/app/exporter.py"]
