FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir foxglove-sdk eclipse-zenoh requests pyyaml

COPY . .

EXPOSE 8090

CMD ["python", "-u", "flight_controller.py"]
