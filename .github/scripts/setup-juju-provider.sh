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
# HTTPS_PROXY (custom TLS dialer).  PS7 runners have no direct route
# to vSphere — all traffic must go through the squid egress proxy.
#
# Fix: for each controller API endpoint in controllers.yaml:
#   1. Start a socat+nc tunnel on localhost that proxies through squid
#      via HTTP CONNECT (nc -X connect — same method SSH uses).
#   2. Patch controllers.yaml so juju connects to localhost instead.
#
# This bypasses aproxy entirely (juju connects to localhost) and uses
# the same nc CONNECT method proven to work for SSH.
APROXY_PORT=$(ps aux | grep -oP 'aproxy.*--listen :\K[0-9]+' | head -1 || true)
if [ -n "$APROXY_PORT" ]; then
  echo "PS7 runner detected (aproxy port $APROXY_PORT)"

  # nftables: redirect vSphere subnet port 443 through aproxy.
  # Required — there is no direct route to vSphere from PS7.
  # Mirrors the prepare runner's setup for vCenter connectivity.
  sudo nft insert rule ip nat OUTPUT ip daddr 10.246.152.0/21 tcp dport 443 redirect to :"$APROXY_PORT"
  echo "nftables: 10.246.152.0/21:443 → aproxy (:$APROXY_PORT)"

  # Install socat (for TCP listener with fork support)
  sudo apt-get install -y -qq socat >/dev/null 2>&1 || true
  echo "socat version: $(socat -V 2>&1 | head -2 | tail -1 || echo 'unknown')"
  echo "nc version: $(nc -h 2>&1 | head -1 || echo 'unknown')"

  # 3a. Create local TCP tunnels for each controller API endpoint
  JUJU_CONTROLLERS="$JUJU_DATA_DIR/controllers.yaml"
  TUNNEL_PORT=19443
  CONTROLLER_SUBNETS=""

  if [ -f "$JUJU_CONTROLLERS" ]; then
    echo ""
    echo "=== Runner network identity ==="
    ip -4 addr show | grep 'inet ' || true
    echo ""

    echo "=== Squid connectivity check ==="
    SQUID_HOST="egress.ps7.internal"
    SQUID_PORT="3128"
    getent hosts "$SQUID_HOST" || echo "  ❌ DNS: cannot resolve $SQUID_HOST"
    nc -w 3 -zv "$SQUID_HOST" "$SQUID_PORT" 2>&1 || echo "  ❌ TCP: cannot connect to $SQUID_HOST:$SQUID_PORT"
    echo ""

    echo "=== nftables OUTPUT chain (before changes) ==="
    sudo nft list chain ip nat OUTPUT 2>/dev/null || echo "  cannot read nftables"
    echo ""

    # Ensure nc connections to squid bypass aproxy entirely.
    # aproxy typically only redirects 80/443 but this is cheap insurance.
    SQUID_IP=$(getent hosts "$SQUID_HOST" | awk '{print $1}' | head -1)
    if [ -n "$SQUID_IP" ]; then
      sudo nft insert rule ip nat OUTPUT ip daddr "$SQUID_IP" tcp dport "$SQUID_PORT" counter accept
      echo "nftables: ACCEPT for $SQUID_HOST ($SQUID_IP):$SQUID_PORT (bypass aproxy)"
    fi

    echo ""
    echo "=== controllers.yaml (before patching) ==="
    cat "$JUJU_CONTROLLERS"
    echo ""

    # Each endpoint is ip:port (e.g. 10.246.154.13:443)
    ENDPOINTS=$(grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" | sort -u)
    for endpoint in $ENDPOINTS; do
      IP="${endpoint%%:*}"
      PORT="${endpoint##*:}"

      echo "--- Setting up tunnel for $endpoint → localhost:$TUNNEL_PORT ---"

      # Diagnostic: test nc CONNECT directly (same method socat will use)
      echo "  Testing: nc -X connect -x $SQUID_HOST:$SQUID_PORT $IP $PORT ..."
      NC_TEST=$(echo "GET / HTTP/1.0" | timeout 5 nc -X connect -x "$SQUID_HOST:$SQUID_PORT" "$IP" "$PORT" 2>&1 | head -3 || true)
      echo "  nc -X connect result: '${NC_TEST:-(empty)}'"

      # Start socat listener with SYSTEM (avoids colon-escaping issues
      # that EXEC has with socat's address parser).
      # SYSTEM runs through /bin/sh so no special escaping needed.
      socat "TCP-LISTEN:${TUNNEL_PORT},fork,reuseaddr,bind=127.0.0.1" \
        "SYSTEM:nc -X connect -x ${SQUID_HOST}:${SQUID_PORT} ${IP} ${PORT}" &
      SOCAT_PID=$!

      # Wait for socat to start listening
      for _ in $(seq 1 30); do
        if ss -tln | grep -q ":${TUNNEL_PORT} "; then break; fi
        sleep 0.1
      done

      if ! ss -tln | grep -q ":${TUNNEL_PORT} "; then
        echo "  ❌ socat failed to listen on port $TUNNEL_PORT (PID $SOCAT_PID)"
        echo "  Skipping this endpoint"
        TUNNEL_PORT=$((TUNNEL_PORT + 1))
        continue
      fi
      echo "  ✅ socat PID $SOCAT_PID listening on localhost:$TUNNEL_PORT"

      # Patch controllers.yaml to use local tunnel
      sed -i "s|${endpoint}|127.0.0.1:${TUNNEL_PORT}|g" "$JUJU_CONTROLLERS"
      echo "  ✅ Patched controllers.yaml: $endpoint → 127.0.0.1:$TUNNEL_PORT"

      # Track subnet for SSH ProxyCommand
      CONTROLLER_SUBNETS="$CONTROLLER_SUBNETS ${IP%.*}"

      TUNNEL_PORT=$((TUNNEL_PORT + 1))
    done

    echo ""
    echo "=== controllers.yaml (after patching) ==="
    cat "$JUJU_CONTROLLERS"
    echo ""
  else
    echo "WARNING: $JUJU_CONTROLLERS not found — cannot set up tunnels"
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
if [ -f "$JUJU_DATA_DIR/controllers.yaml" ]; then
  echo ""
  echo "=== Juju controller connectivity test ==="
  echo "Active controller: $(juju show-controller --format json 2>/dev/null | head -1 || echo 'unknown')"
  echo "Running: juju status --format json (timeout 60s)..."
  if timeout 60 juju status --format json 2>&1; then
    echo "✅ juju status succeeded"
  else
    EXIT_CODE=$?
    echo "❌ juju status failed (exit code $EXIT_CODE)"
    echo ""
    echo "=== Diagnostic info ==="
    echo "socat processes:"
    ps aux | grep socat | grep -v grep || echo "  none"
    echo "Listening ports:"
    ss -tln | grep '194' || echo "  none matching 194xx"
    echo "nftables OUTPUT chain:"
    sudo nft list chain ip nat OUTPUT 2>/dev/null | head -20 || echo "  cannot read"
    echo "DNS resolution:"
    getent hosts egress.ps7.internal || echo "  cannot resolve egress.ps7.internal"
    echo ""
    echo "WARNING: juju status failed — controller may not be reachable"
  fi
fi
