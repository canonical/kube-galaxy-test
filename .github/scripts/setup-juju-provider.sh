#!/usr/bin/env bash
# Setup script for Juju-based providers (vSphere, etc.)
#
# Called by the reusable cluster-test workflow via `pre-setup-script`.
# Expects PRE_SETUP_ARTIFACT_DIR to point to the downloaded artifact
# containing the Juju client state directory.
set -euo pipefail

# ── 1. Install Juju snap ────────────────────────────────────────────
echo "Installing juju snap..."
sudo snap install juju --channel=3/stable --classic
juju version

# ── 2. Restore Juju client state from artifact ─────────────────────
JUJU_DATA_DIR="${HOME}/.local/share/juju"
if [ -d "${PRE_SETUP_ARTIFACT_DIR:-}" ] && [ "$(ls -A "$PRE_SETUP_ARTIFACT_DIR")" ]; then
  echo "Restoring Juju client state from ${PRE_SETUP_ARTIFACT_DIR}..."
  mkdir -p "$JUJU_DATA_DIR"
  cp -a "${PRE_SETUP_ARTIFACT_DIR}/." "$JUJU_DATA_DIR/"
else
  echo "WARNING: PRE_SETUP_ARTIFACT_DIR is empty or unset — skipping state restore"
fi

# ── 3. Configure network for Juju controller (PS7 runners) ─────────
# On PS7 runners, aproxy intercepts outbound TLS via nftables REDIRECT
# and SNI peek.  Juju connects to the controller by IP (no hostname),
# so TLS ClientHello has no SNI → aproxy hangs.  Juju also ignores
# HTTPS_PROXY (custom TLS dialer).  And PS7 runners have no direct
# route to the vSphere network.
#
# Fix: for each controller API endpoint in controllers.yaml:
#   1. Start a socat TCP listener on localhost that tunnels through
#      squid via HTTP CONNECT to the real controller.
#   2. Patch controllers.yaml to point at the local tunnel endpoint.
#
# This bypasses aproxy entirely (juju connects to localhost, not the
# remote IP) and needs zero nftables rules.
APROXY_PORT=$(ps aux | grep -oP 'aproxy.*--listen :\K[0-9]+' | head -1 || true)
if [ -n "$APROXY_PORT" ]; then
  echo "PS7 runner detected (aproxy port $APROXY_PORT)"

  # Install socat for TCP-to-CONNECT tunnelling
  sudo apt-get install -y -qq socat >/dev/null 2>&1 || true

  # 3a. Create local TCP tunnels for each controller API endpoint,
  #     then patch controllers.yaml so juju connects locally.
  JUJU_CONTROLLERS="$JUJU_DATA_DIR/controllers.yaml"
  TUNNEL_PORT=19443
  CONTROLLER_SUBNETS=""

  if [ -f "$JUJU_CONTROLLERS" ]; then
    echo "=== controllers.yaml endpoints (before patching) ==="
    grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" || true

    # Each endpoint is ip:port (e.g. 10.246.154.178:443)
    ENDPOINTS=$(grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" | sort -u)
    for endpoint in $ENDPOINTS; do
      IP="${endpoint%%:*}"
      PORT="${endpoint##*:}"

      # Verify squid allows CONNECT to this endpoint
      CONNECT_RESP=$(echo -e "CONNECT ${endpoint} HTTP/1.1\r\nHost: ${endpoint}\r\n\r\n" \
        | nc -w 5 egress.ps7.internal 3128 | head -1 || true)
      echo "squid CONNECT test ($endpoint): $CONNECT_RESP"

      # Start socat: localhost:TUNNEL_PORT → squid CONNECT → IP:PORT
      socat TCP-LISTEN:${TUNNEL_PORT},fork,reuseaddr,bind=127.0.0.1 \
        PROXY:egress.ps7.internal:${IP}:${PORT},proxyport=3128 &
      SOCAT_PID=$!

      # Wait for socat to start accepting connections
      for _ in $(seq 1 20); do
        if ss -tln | grep -q ":${TUNNEL_PORT} "; then break; fi
        sleep 0.1
      done

      if ss -tln | grep -q ":${TUNNEL_PORT} "; then
        echo "✅ socat PID $SOCAT_PID: localhost:$TUNNEL_PORT → squid → $endpoint"
      else
        echo "❌ socat failed to start on port $TUNNEL_PORT"
      fi

      # Patch controllers.yaml: juju will now connect to localhost
      sed -i "s|${endpoint}|127.0.0.1:${TUNNEL_PORT}|g" "$JUJU_CONTROLLERS"

      # Track subnet for SSH ProxyCommand
      CONTROLLER_SUBNETS="$CONTROLLER_SUBNETS ${IP%.*}"

      TUNNEL_PORT=$((TUNNEL_PORT + 1))
    done

    echo "=== controllers.yaml endpoints (after patching) ==="
    grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" || true
  fi

  # 3b. SSH ProxyCommand — route SSH through squid for the controller
  #     subnet (machines provisioned by Juju live on the same network).
  if [ -n "$CONTROLLER_SUBNETS" ]; then
    mkdir -p ~/.ssh
    for prefix in $(echo "$CONTROLLER_SUBNETS" | tr ' ' '\n' | sort -u); do
      cat >> ~/.ssh/config <<EOF
Host ${prefix}.*
  ProxyCommand nc -X connect -x egress.ps7.internal:3128 %h %p
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
      echo "SSH ProxyCommand configured for ${prefix}.*"
    done
    chmod 600 ~/.ssh/config
  fi

  # 3c. HTTPS_PROXY for general Go/HTTP traffic (cloud APIs, etc.)
  export HTTPS_PROXY="http://egress.ps7.internal:3128"
  export NO_PROXY="localhost,127.0.0.1,::1"
  echo "HTTPS_PROXY=http://egress.ps7.internal:3128" >> "$GITHUB_ENV"
  echo "NO_PROXY=localhost,127.0.0.1,::1" >> "$GITHUB_ENV"
else
  echo "No aproxy detected — assuming direct connectivity"
fi

# ── 4. Verify controller connectivity ──────────────────────────────
if [ -d "$JUJU_DATA_DIR" ]; then
  echo "Verifying juju controller connectivity..."
  timeout 30 juju status --format json 2>&1 | head -5 || echo "WARNING: juju status failed — controller may not be reachable"
fi
