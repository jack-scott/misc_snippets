FROM alpine:3.20

RUN apk add --no-cache \
    syncthing \
    python3 \
    py3-requests \
    curl \
    openssh \
    && rm -rf /var/cache/apk/*

COPY docker/drone/scripts/ /scripts/
RUN chmod +x /scripts/*.sh

# Dev-only test public key — baked in for passwordless SSH from the backend.
# NOT for use on real drone hardware.
COPY docker/keys/test_key.pub /tmp/test_key.pub

VOLUME ["/config", "/data"]
EXPOSE 8384 22000 22

ENTRYPOINT ["/scripts/entrypoint.sh"]
