FROM python:3.11-alpine

# Install networking tools for tc netem and probes
RUN apk add --no-cache \
    iproute2 \
    iputils \
    iptables

WORKDIR /app
COPY radio.py .

EXPOSE 8080 9000 9001

CMD ["python", "-u", "radio.py"]
