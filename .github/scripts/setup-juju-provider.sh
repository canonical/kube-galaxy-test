#!/usr/bin/env bash
# Setup script for Juju-based providers (vSphere, etc.)
#
# Called by the reusable cluster-test workflow via `pre-setup-script`.
# Expects PRE_SETUP_ARTIFACT_DIR to point to the downloaded artifact
# containing the Juju client state directory.
set -euo pipefail

# ── 1. Install Juju snap ────────────────────────────────────────────
# Match actions-operator: juju 3.x is installed WITHOUT --classic
# (strict confinement). Pre-create the data dir as actions-operator does.
echo "Installing juju snap..."
sudo snap install juju --channel=3/stable
juju version

# ── 2. Restore Juju client state from artifact ─────────────────────
# Use a non-hidden path that strictly confined juju can access.
# Set JUJU_DATA to point juju at our restored state.
JUJU_DATA_DIR="${HOME}/juju-data"
if [ -d "${PRE_SETUP_ARTIFACT_DIR:-}" ] && [ "$(ls -A "$PRE_SETUP_ARTIFACT_DIR")" ]; then
  echo "Restoring Juju client state from ${PRE_SETUP_ARTIFACT_DIR}..."
  mkdir -p "$JUJU_DATA_DIR"
  cp -a "${PRE_SETUP_ARTIFACT_DIR}/." "$JUJU_DATA_DIR/"
  
  # Make juju use this directory
  export JUJU_DATA="$JUJU_DATA_DIR"
  echo "JUJU_DATA=$JUJU_DATA_DIR" >> "$GITHUB_ENV"
  echo "JUJU_DATA set to: $JUJU_DATA_DIR"
  
  # Verify contents
  echo "Restored files:"
  ls -la "$JUJU_DATA_DIR/"
else
  echo "WARNING: PRE_SETUP_ARTIFACT_DIR is empty or unset — skipping state restore"
  JUJU_DATA_DIR="${HOME}/.local/share/juju"
fi

# ── 3. Configure network (PS7 runners) ─────────────────────────────
# PS7 runners have no direct route to vSphere — all traffic must go
# through a proxy.  The prepare runner uses a nftables REDIRECT to
# route port 443 through aproxy (transparent proxy), and this works
# even for Juju's IP-only TLS connections.  We replicate the same
# setup here.  SSH uses ProxyCommand through squid.
APROXY_PORT=$(ps aux | grep -oP 'aproxy.*--listen :\K[0-9]+' | head -1 || true)
if [ -n "$APROXY_PORT" ]; then
  echo "PS7 runner detected (aproxy port $APROXY_PORT)"

  # nftables: redirect vSphere subnet port 443 through aproxy.
  # This is the same approach the prepare runner uses for bootstrap.
  sudo nft insert rule ip nat OUTPUT ip daddr 10.246.152.0/21 tcp dport 443 redirect to :"$APROXY_PORT"
  echo "nftables: 10.246.152.0/21:443 → aproxy (:$APROXY_PORT)"

  # SSH ProxyCommand for controller/worker subnet.
  JUJU_CONTROLLERS="$JUJU_DATA_DIR/controllers.yaml"
  CONTROLLER_SUBNETS=""
  if [ -f "$JUJU_CONTROLLERS" ]; then
    echo ""
    echo "=== controllers.yaml ==="
    cat "$JUJU_CONTROLLERS"
    echo ""

    ENDPOINTS=$(grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" | sort -u)
    for endpoint in $ENDPOINTS; do
      IP="${endpoint%%:*}"
      CONTROLLER_SUBNETS="$CONTROLLER_SUBNETS ${IP%.*}"
    done
  fi

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

  # HTTPS_PROXY for general Go/HTTP traffic (cloud APIs, etc.)
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
  echo "Juju data dir contents:"
  ls -la "$JUJU_DATA_DIR/" || true
  echo ""
  echo "Active controller: $(juju show-controller --format json 2>/dev/null | head -1 || echo 'unknown')"
  echo "Running: juju status (timeout 60s)..."
  if timeout 60 juju status 2>&1; then
    echo "✅ juju status succeeded"
  else
    EXIT_CODE=$?
    echo "❌ juju status failed (exit code $EXIT_CODE)"
    echo ""
    echo "=== Diagnostic info ==="
    echo "nftables OUTPUT chain:"
    sudo nft list chain ip nat OUTPUT 2>/dev/null | head -20 || echo "  cannot read"
    echo "Network identity:"
    ip -4 addr show | grep 'inet ' || true
    echo "Route to controller:"
    CTRL_IP=$(grep -oP '\d+\.\d+\.\d+\.\d+' "$JUJU_DATA_DIR/controllers.yaml" | head -1 || true)
    [ -n "$CTRL_IP" ] && ip route get "$CTRL_IP" 2>/dev/null || true
    echo ""
    echo "WARNING: juju status failed — controller may not be reachable"
  fi
fi
