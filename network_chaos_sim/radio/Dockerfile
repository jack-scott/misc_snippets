FROM python:3.11-alpine

RUN apk add --no-cache \
    iproute2 \
    iputils \
    iptables

RUN pip install --no-cache-dir pyyaml

WORKDIR /app
COPY radio.py .

EXPOSE 8080 9000 9001

CMD ["python", "-u", "radio.py"]
