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
# producing a TLS ClientHello with no SNI.  aproxy can't form a valid
# CONNECT request → the connection hangs indefinitely.
#
# Additionally, Juju's API client uses a custom TLS dialer for
# controller websocket connections — it does NOT honor HTTPS_PROXY.
# So setting HTTPS_PROXY alone doesn't help for `juju status` etc.
#
# Fix: insert nftables ACCEPT rules for the controller IP(s) so
# traffic bypasses aproxy entirely and goes direct.  HTTPS_PROXY is
# still set for other Go/HTTP traffic (e.g. cloud API calls).
APROXY_PORT=$(ps aux | grep -oP 'aproxy.*--listen :\K[0-9]+' | head -1 || true)
if [ -n "$APROXY_PORT" ]; then
  echo "PS7 runner detected (aproxy port $APROXY_PORT)"

  # 3a. Extract controller API IPs from restored client state and
  #     bypass aproxy for direct connectivity.
  if [ -f "$JUJU_DATA_DIR/controllers.yaml" ]; then
    # api-endpoints entries look like:  - 10.246.152.x:443
    CONTROLLER_IPS=$(grep -oP '\d+\.\d+\.\d+\.\d+(?=:\d+)' "$JUJU_DATA_DIR/controllers.yaml" | sort -u)
    for ip in $CONTROLLER_IPS; do
      echo "nftables: ACCEPT for controller $ip:443 (bypass aproxy)"
      sudo nft insert rule ip nat OUTPUT ip daddr "$ip" tcp dport 443 counter accept
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
