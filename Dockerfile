FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

RUN useradd -m myuser
USER myuser

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
