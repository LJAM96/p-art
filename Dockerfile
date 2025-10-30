FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY p_art.py .
COPY web.py .
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh

EXPOSE 5000

ENV FLASK_APP=web.py

ENTRYPOINT ["/app/entrypoint.sh"]
