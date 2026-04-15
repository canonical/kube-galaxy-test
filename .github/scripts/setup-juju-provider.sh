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
# On PS7 runners, aproxy intercepts ALL outbound TLS (port 443) via
# nftables REDIRECT, then peeks the SNI from TLS ClientHello.
# Juju's API client connects to the controller by IP (no hostname),
# producing a TLS ClientHello with no SNI → aproxy hangs.
#
# Juju also uses a custom TLS dialer for controller websocket
# connections that does NOT honor HTTPS_PROXY — so setting the env
# var alone doesn't help.
#
# PS7 runners have NO direct route to the vSphere network.  All
# traffic must flow through the squid egress proxy.
#
# Fix: for each controller IP, start a local socat TCP listener that
# tunnels through squid via HTTP CONNECT, then nftables-redirect
# controller traffic to the local listener.  This sidesteps both
# aproxy (no SNI needed) and the lack of direct connectivity.
APROXY_PORT=$(ps aux | grep -oP 'aproxy.*--listen :\K[0-9]+' | head -1 || true)
if [ -n "$APROXY_PORT" ]; then
  echo "PS7 runner detected (aproxy port $APROXY_PORT)"

  # Install socat for TCP-to-CONNECT tunnelling
  sudo apt-get install -y -qq socat >/dev/null 2>&1 || true

  # 3a. Extract controller API IPs and create tunnels through squid
  TUNNEL_PORT=19443
  if [ -f "$JUJU_DATA_DIR/controllers.yaml" ]; then
    # api-endpoints entries look like:  - 10.246.152.x:443
    CONTROLLER_IPS=$(grep -oP '\d+\.\d+\.\d+\.\d+(?=:\d+)' "$JUJU_DATA_DIR/controllers.yaml" | sort -u)
    for ip in $CONTROLLER_IPS; do
      echo "Tunnel: $ip:443 → localhost:$TUNNEL_PORT → squid CONNECT → $ip:443"

      # Start socat in background: accepts local TCP, opens HTTP
      # CONNECT through squid to the controller, bridges both sides.
      socat TCP-LISTEN:$TUNNEL_PORT,fork,reuseaddr,bind=127.0.0.1 \
        PROXY:egress.ps7.internal:$ip:443,proxyport=3128 &

      # Redirect outbound traffic to the controller through our tunnel
      # (inserted BEFORE the default aproxy REDIRECT so it matches first)
      sudo nft insert rule ip nat OUTPUT ip daddr "$ip" tcp dport 443 redirect to :$TUNNEL_PORT

      TUNNEL_PORT=$((TUNNEL_PORT + 1))
    done
  fi

  # 3b. SSH ProxyCommand — route SSH through squid for the controller
  #     subnet (machines provisioned by Juju live on the same network).
  if [ -n "${CONTROLLER_IPS:-}" ]; then
    mkdir -p ~/.ssh
    for ip in $CONTROLLER_IPS; do
      # Derive /24 pattern for SSH config Host matching
      SUBNET_PREFIX=$(echo "$ip" | cut -d. -f1-3)
      cat >> ~/.ssh/config <<EOF
Host ${SUBNET_PREFIX}.*
  ProxyCommand nc -X connect -x egress.ps7.internal:3128 %h %p
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
      echo "SSH ProxyCommand configured for ${SUBNET_PREFIX}.*"
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
