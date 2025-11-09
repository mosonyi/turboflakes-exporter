FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY exporter/app.py /app/exporter.py

EXPOSE 9101
CMD ["python", "/app/exporter.py"]
