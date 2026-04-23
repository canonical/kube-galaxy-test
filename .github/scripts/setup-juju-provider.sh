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
  
  # Compare config checksums for debugging transfer issues
  echo ""
  echo "=== Config file checksums (for comparison with prepare job) ==="
  for f in accounts.yaml controllers.yaml credentials.yaml models.yaml; do
    if [ -f "$JUJU_DATA_DIR/$f" ]; then
      MD5=$(md5sum "$JUJU_DATA_DIR/$f" | awk '{print $1}')
      SIZE=$(stat -c%s "$JUJU_DATA_DIR/$f")
      echo "  $f: $MD5 ($SIZE bytes)"
    fi
  done
  
  echo ""
  echo "=== cookies/ directory ==="
  ls -la "$JUJU_DATA_DIR/cookies/" 2>/dev/null || echo "  (no cookies dir)"
  for f in "$JUJU_DATA_DIR/cookies/"*.json; do
    [ -f "$f" ] && echo "  $(basename "$f"): $(wc -c < "$f") bytes" || true
  done
  
  echo ""
  echo "=== accounts.yaml content ==="
  cat "$JUJU_DATA_DIR/accounts.yaml" 2>/dev/null || echo "  (not found)"
  
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

# ── 3. Configure proxy for vSphere access ──────────────────────────
# PS7 runners have no direct route to vSphere — traffic must go through
# squid proxy. HTTPS_PROXY is respected by Go clients (juju) for HTTPS.
export HTTPS_PROXY="http://egress.ps7.internal:3128"
export NO_PROXY="localhost,127.0.0.1,::1"
echo "HTTPS_PROXY=http://egress.ps7.internal:3128" >> "$GITHUB_ENV"
echo "NO_PROXY=localhost,127.0.0.1,::1" >> "$GITHUB_ENV"
echo "Configured HTTPS_PROXY for vSphere access"

# Debug: which squid backend are we hitting?
echo ""
echo "=== Squid backend debug ==="
echo "Runner IP: $(hostname -I | awk '{print $1}')"
echo "Squid DNS resolution:"
getent hosts egress.ps7.internal || echo "  DNS lookup failed"
echo "Testing squid connectivity:"
curl -s -o /dev/null -w "Squid backend IP: %{remote_ip}\n" --proxy http://egress.ps7.internal:3128 http://httpbin.org/ip 2>&1 || echo "  (test failed)"

# SSH ProxyCommand for connections to controller/worker VMs.
# Configure the FULL vSphere /21 subnet range (10.246.152.0/21) to match
# what actions-operator sets up during bootstrap.
JUJU_CONTROLLERS="$JUJU_DATA_DIR/controllers.yaml"
if [ -f "$JUJU_CONTROLLERS" ]; then
  echo ""
  echo "=== controllers.yaml ==="
  cat "$JUJU_CONTROLLERS"
  echo ""

  # Configure SSH proxy for entire vSphere subnet, not just controller's /24
  mkdir -p ~/.ssh
  cat >> ~/.ssh/config <<EOF
Host 10.246.152.* 10.246.153.* 10.246.154.* 10.246.155.* 10.246.156.* 10.246.157.* 10.246.158.* 10.246.159.*
  ProxyCommand nc -X connect -x egress.ps7.internal:3128 %h %p
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
EOF
  chmod 600 ~/.ssh/config
  echo "SSH ProxyCommand configured for vSphere subnet 10.246.152.0/21"
fi

# ── 4. Verify controller connectivity ──────────────────────────────
if [ -f "$JUJU_DATA_DIR/controllers.yaml" ]; then
  echo ""
  echo "=== Juju controller connectivity test ==="
  echo "JUJU_DATA=${JUJU_DATA:-<not set>}"
  echo "Juju data dir contents:"
  ls -la "$JUJU_DATA_DIR/" || true

  # Extract controller endpoint for direct testing
  CTRL_ENDPOINT=$(grep -oP '\d+\.\d+\.\d+\.\d+:\d+' "$JUJU_DATA_DIR/controllers.yaml" | head -1 || true)
  CTRL_IP="${CTRL_ENDPOINT%:*}"
  CTRL_PORT="${CTRL_ENDPOINT#*:}"
  echo ""
  echo "Controller endpoint: $CTRL_ENDPOINT"

  # Test BOTH squid IPs to rule out squid-specific issues
  echo ""
  echo "=== Testing BOTH squid backends to controller ==="
  for SQUID in 10.151.41.5 10.151.41.6 10.151.41.7; do
    echo ""
    echo "--- Testing via squid $SQUID ---"
    if curl -s --max-time 8 --proxy "http://$SQUID:3128" \
         --connect-timeout 5 "https://$CTRL_IP:$CTRL_PORT/" -o /dev/null -w "HTTP %{http_code}, time %{time_total}s\n" 2>&1; then
      echo "  ✅ squid $SQUID: connection succeeded"
    else
      EXIT=$?
      if [ $EXIT -eq 28 ]; then
        echo "  ❌ squid $SQUID: TIMEOUT (exit $EXIT)"
      else
        echo "  ❌ squid $SQUID: failed (exit $EXIT)"
      fi
    fi
  done

  # What does juju see? (runs after proxy is configured)
  echo ""
  echo "=== juju controllers (list all known controllers) ==="
  juju controllers --format yaml 2>&1 || echo "  (command failed)"

  echo ""
  echo "=== juju show-controller (detailed view) ==="
  timeout 60 juju show-controller --format yaml 2>&1 || echo "  (command failed)"

  # Retry juju status with exponential backoff
  echo ""
  echo "=== juju status with retry ==="
  RETRY_COUNT=0
  MAX_RETRIES=3
  JUJU_OK=false
  while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Attempt $((RETRY_COUNT + 1))/$MAX_RETRIES: juju status (timeout 60s)..."
    if timeout 60 juju status 2>&1; then
      echo "✅ juju status succeeded"
      JUJU_OK=true
      break
    else
      EXIT_CODE=$?
      echo "  ❌ failed (exit code $EXIT_CODE)"
      RETRY_COUNT=$((RETRY_COUNT + 1))
      if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        WAIT=$((10 * RETRY_COUNT))
        echo "  Waiting ${WAIT}s before retry..."
        sleep $WAIT
      fi
    fi
  done

  if [ "$JUJU_OK" = false ]; then
    echo ""
    echo "=== Diagnostic info ==="
    echo "Runner IP: $(hostname -I | awk '{print $1}')"
    echo "Squid DNS: $(getent hosts egress.ps7.internal | head -1)"
    echo "Route to controller:"
    [ -n "$CTRL_IP" ] && ip route get "$CTRL_IP" 2>/dev/null || true
    echo ""
    echo "ERROR: juju status failed after $MAX_RETRIES attempts"
    echo "This suggests the controller is not reachable from this runner."
    echo "The prepare job ran on a different runner that could reach the controller."
  fi
fi
