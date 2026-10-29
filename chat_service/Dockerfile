FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8001
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers ${WORKERS:-2}"]
