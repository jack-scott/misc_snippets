FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir foxglove-sdk requests protobuf

COPY server.py .

EXPOSE 8765 9090

CMD ["python", "-u", "server.py"]
