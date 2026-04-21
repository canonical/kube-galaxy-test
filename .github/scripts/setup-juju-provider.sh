#!/usr/bin/env bash
# Setup script for Juju-based providers (vSphere, etc.)
#
# Called by the reusable cluster-test workflow via `pre-setup-script`.
# Expects PRE_SETUP_ARTIFACT_DIR to point to the downloaded artifact
# containing the Juju client state directory.
set -euo pipefail

# ── 1. Install Juju snap ────────────────────────────────────────────
# Use --devmode to bypass strict snap confinement entirely.
# Strictly confined juju can't access externally-restored config files.
echo "Installing juju snap..."
sudo snap install juju --channel=3/stable --devmode
juju version

# ── 2. Restore Juju client state from artifact ─────────────────────
# The juju snap uses its own default data path (~/snap/juju/common/ or
# similar), not ~/.local/share/juju.  We MUST set JUJU_DATA to tell juju
# where our restored config files are.
JUJU_DATA_DIR="${HOME}/.local/share/juju"
if [ -d "${PRE_SETUP_ARTIFACT_DIR:-}" ] && [ "$(ls -A "$PRE_SETUP_ARTIFACT_DIR")" ]; then
  echo "Restoring Juju client state from ${PRE_SETUP_ARTIFACT_DIR}..."
  mkdir -p "$JUJU_DATA_DIR"
  cp -a "${PRE_SETUP_ARTIFACT_DIR}/." "$JUJU_DATA_DIR/"
  
  # Tell juju to use this directory — critical for snap-installed juju
  export JUJU_DATA="$JUJU_DATA_DIR"
  echo "JUJU_DATA=$JUJU_DATA_DIR" >> "$GITHUB_ENV"
  echo "JUJU_DATA set to: $JUJU_DATA_DIR"
  
  # Verify contents
  echo "Restored files:"
  ls -la "$JUJU_DATA_DIR/"
  
  # Debug: what does juju think its data dir is?
  echo ""
  echo "=== Juju environment debug ==="
  echo "HOME=$HOME"
  echo "USER=$(whoami)"
  echo "JUJU_DATA=$JUJU_DATA"
  
  # Check if controllers.yaml is valid YAML
  echo ""
  echo "=== Validating controllers.yaml ==="
  if python3 -c "import yaml; yaml.safe_load(open('$JUJU_DATA_DIR/controllers.yaml'))" 2>&1; then
    echo "  ✅ Valid YAML"
  else
    echo "  ❌ Invalid YAML"
  fi
else
  echo "WARNING: PRE_SETUP_ARTIFACT_DIR is empty or unset — skipping state restore"
fi

# ── 3. Configure SSH for vSphere VMs ───────────────────────────────
# SSH doesn't respect HTTPS_PROXY, so we configure ProxyCommand for
# connections to vSphere subnets.
JUJU_CONTROLLERS="$JUJU_DATA_DIR/controllers.yaml"
if [ -f "$JUJU_CONTROLLERS" ]; then
  echo ""
  echo "=== controllers.yaml ==="
  cat "$JUJU_CONTROLLERS"
  echo ""

  CONTROLLER_SUBNETS=""
  ENDPOINTS=$(grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_CONTROLLERS" | sort -u)
  for endpoint in $ENDPOINTS; do
    IP="${endpoint%%:*}"
    CONTROLLER_SUBNETS="$CONTROLLER_SUBNETS ${IP%.*}"
  done

  if [ -n "$CONTROLLER_SUBNETS" ]; then
    mkdir -p ~/.ssh
    for prefix in $(echo "$CONTROLLER_SUBNETS" | tr ' ' '\n' | sort -u); do
      cat >> ~/.ssh/config <<EOF
Host ${prefix}.*
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
      echo "SSH config added for ${prefix}.*"
    done
    chmod 600 ~/.ssh/config
  fi
fi

# ── 4. Verify controller connectivity ──────────────────────────────
if [ -f "$JUJU_DATA_DIR/controllers.yaml" ]; then
  echo ""
  echo "=== Juju controller connectivity test ==="
  echo "JUJU_DATA=${JUJU_DATA:-<not set>}"
  echo "Juju data dir contents:"
  ls -la "$JUJU_DATA_DIR/" || true

  # What does juju see? (runs after proxy is configured)
  echo ""
  echo "=== juju controllers (list all known controllers) ==="
  juju controllers --format yaml 2>&1 || echo "  (command failed)"

  echo ""
  echo "=== juju show-controller (detailed view) ==="
  timeout 60 juju show-controller --format yaml 2>&1 || echo "  (command failed)"

  echo ""
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
