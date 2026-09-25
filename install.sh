#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing OpenCode Hermes Bridge..."

HERMES_PROFILE="${HERMES_PROFILE:-mind-slayer}"
HERMES_DIR="$HOME/.hermes/profiles/$HERMES_PROFILE"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure directories exist
mkdir -p "$HERMES_DIR/scripts" "$HERMES_DIR/plugins/opencode-slash" "$HERMES_DIR/logs"

# 1. Copy proxy script
echo "==> Installing OpenAI proxy script to $HERMES_DIR/scripts/..."
cp "$REPO_DIR/scripts/opencode-openai-proxy.py" "$HERMES_DIR/scripts/opencode-openai-proxy.py"
chmod +x "$HERMES_DIR/scripts/opencode-openai-proxy.py"

# 2. Copy slash plugin
echo "==> Installing /oc slash plugin to $HERMES_DIR/plugins/opencode-slash/..."
cp "$REPO_DIR/plugins/opencode-slash/plugin.yaml" "$HERMES_DIR/plugins/opencode-slash/"
cp "$REPO_DIR/plugins/opencode-slash/__init__.py" "$HERMES_DIR/plugins/opencode-slash/"

# 3. Configure Hermes (if hermes is installed)
if command -v hermes >/dev/null 2>&1; then
  echo "==> Configuring Hermes provider and plugin..."
  hermes plugins enable opencode-slash || true

  hermes config set providers.opencode-direct.name "opencode-direct" || true
  hermes config set providers.opencode-direct.base_url "http://127.0.0.1:4098/v1" || true
  hermes config set providers.opencode-direct.api_mode "chat_completions" || true
  hermes config set providers.opencode-direct.key "dummy" || true
  hermes config set providers.opencode-direct.models '["opencode"]' || true
  hermes config set model.aliases.opencode "opencode-direct/opencode" || true
else
  echo "==> Hermes CLI not detected in PATH. Skipping Hermes config step."
fi

# 4. Setup Services
if [[ "$(uname)" == "Darwin" ]]; then
  echo "==> Setting up macOS launchd daemons..."
  mkdir -p "$HOME/Library/LaunchAgents"

  # Replace user paths dynamically
  sed "s|/Users/aayurtshrestha|$HOME|g" "$REPO_DIR/launchd/com.user.opencode-serve.plist" > "$HOME/Library/LaunchAgents/com.user.opencode-serve.plist"
  sed "s|/Users/aayurtshrestha|$HOME|g" "$REPO_DIR/launchd/com.user.opencode-proxy.plist" > "$HOME/Library/LaunchAgents/com.user.opencode-proxy.plist"

  launchctl unload "$HOME/Library/LaunchAgents/com.user.opencode-serve.plist" 2>/dev/null || true
  launchctl load "$HOME/Library/LaunchAgents/com.user.opencode-serve.plist"

  launchctl unload "$HOME/Library/LaunchAgents/com.user.opencode-proxy.plist" 2>/dev/null || true
  launchctl load "$HOME/Library/LaunchAgents/com.user.opencode-proxy.plist"
elif [[ "$(uname)" == "Linux" ]]; then
  echo "==> Setting up Linux systemd daemons..."
  SUDO=""
  if [[ "$EUID" -ne 0 ]]; then
    SUDO="sudo"
  fi

  $SUDO cp "$REPO_DIR/systemd/opencode-serve.service" /etc/systemd/system/
  $SUDO cp "$REPO_DIR/systemd/opencode-proxy.service" /etc/systemd/system/
  
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now opencode-serve
  $SUDO systemctl enable --now opencode-proxy
fi

echo "==> Installation complete! Ready to use:"
echo "    - Slash command: /oc <prompt>"
echo "    - Switch model:  /model opencode"
