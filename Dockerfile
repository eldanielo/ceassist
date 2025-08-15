FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

RUN useradd -m myuser && chown -R myuser:myuser /app
USER myuser

CMD uvicorn main:app --host 0.0.0.0 --port 8080
