FROM python:3.9-slim

WORKDIR /app


# Install cron
RUN apt-get update && apt-get -y install cron

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY p_art.py .
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
