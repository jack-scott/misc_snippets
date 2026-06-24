#!/bin/sh
set -e

CONFIG_DIR=/config
DATA_DIR=/data
API_KEY="${SYNCTHING_API_KEY:-syncthing-api-key}"
ROLE="${ROLE:-drone}"

mkdir -p "$CONFIG_DIR" "$DATA_DIR/organised"

# ── SSH (drone only) ──────────────────────────────────────────────────────────
if [ "$ROLE" = "drone" ]; then
    # Generate SSH host keys on first start
    ssh-keygen -A

    # Write sshd config — key auth only, no passwords, root allowed
    cat > /etc/ssh/sshd_config << 'EOF'
Port 22
PermitRootLogin prohibit-password
PasswordAuthentication no
ChallengeResponseAuthentication no
AuthorizedKeysFile /root/.ssh/authorized_keys
PrintMotd no
EOF

    # Install the test public key
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    cp /tmp/test_key.pub /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys

    echo "[$ROLE] Starting sshd..."
    /usr/sbin/sshd
fi

# ── Syncthing ─────────────────────────────────────────────────────────────────
# First run: let Syncthing generate its config and device cert, then stop it
if [ ! -f "$CONFIG_DIR/config.xml" ]; then
    echo "[$ROLE] Generating initial syncthing config..."
    syncthing --home="$CONFIG_DIR" --no-browser &
    ST_PID=$!
    i=0
    while [ $i -lt 60 ]; do
        [ -f "$CONFIG_DIR/config.xml" ] && break
        sleep 1
        i=$((i+1))
    done
    kill $ST_PID 2>/dev/null || true
    wait $ST_PID 2>/dev/null || true
    sleep 1
fi

# Patch config: role-aware listen address, known API key, no insecureSkipHostcheck
python3 /scripts/patch_config.py "$CONFIG_DIR/config.xml"

# Start Syncthing
echo "[$ROLE] Starting syncthing..."
syncthing --home="$CONFIG_DIR" --no-browser &

# Wait for API
echo "[$ROLE] Waiting for syncthing API..."
i=0
while [ $i -lt 60 ]; do
    if curl -sf http://localhost:8384/rest/system/ping \
            -H "X-API-Key: $API_KEY" > /dev/null 2>&1; then
        break
    fi
    sleep 1
    i=$((i+1))
done
echo "[$ROLE] Syncthing API ready"

# Register the organised folder
python3 /scripts/setup_folder.py

# Fake log generator on drone nodes only
if [ "$ROLE" = "drone" ]; then
    echo "[$ROLE] Starting fake log generator..."
    python3 /scripts/fake_log_generator.py &
fi

wait
