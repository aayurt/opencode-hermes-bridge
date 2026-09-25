# OpenCode Hermes Bridge ⚡

High-speed, zero-token cost integration between [Hermes Agent](https://github.com/NousResearch/hermes-agent) and [OpenCode](https://opencode.ai).

Enables Hermes to delegate generation and coding tasks directly to OpenCode while keeping full session history and eliminating external LLM API token costs.

---

## Highlights

* **$0 Token Cost:** Prompts are routed directly to OpenCode; no commercial model API tokens (OpenAI, Anthropic, OpenRouter) are consumed.
* **Warm Daemon Architecture (~1.4s response):** Connects to a persistent background `opencode serve` HTTP REST instance on port `4097` instead of spawning cold CLI processes (~8s+).
* **Automatic Multi-Turn Session Continuity:** Conversation state and context are preserved seamlessly across turns in Hermes.
* **Dual Invocation Modes:**
  1. **OpenAI Provider Mode:** Select OpenCode as the active model with `/model opencode`.
  2. **Native Slash Command:** Run one-off questions anytime with `/oc <prompt>`.
* **Cross-Platform Daemon Management:**
  * **macOS:** Handled via `launchd` (`com.user.opencode-serve`, `com.user.opencode-proxy`).
  * **Linux / VPS:** Handled via `systemd` (`opencode-serve.service`, `opencode-proxy.service`).

---

## Architecture

```
User Prompt (Hermes Desktop / TUI / Telegram)
      │
      ├───────────────────────────────┬───────────────────────────────┐
      ▼                               ▼                               ▼
/model opencode                  /oc <prompt>               Direct REST Client
(OpenAI completions)            (Native Plugin)              (curl / Python)
      │                               │                               │
      └───────────────────────┬───────┴───────────────────────────────┘
                              ▼
                OpenCode OpenAI Proxy (:4098)
                  (Session routing & caching)
                              │
                    ┌─────────┴─────────┐
             (warm, ~1.4s)        (cold fallback)
                    ▼                   ▼
           opencode serve (:4097)  opencode run CLI
                    │
                    ▼
          OpenCode Engine Output
```

---

## Prerequisites

1. **Node.js & OpenCode CLI** (v1.18.0 or newer):
   ```bash
   npm install -g opencode-ai
   opencode --version
   ```
2. **Python 3.10+**
3. **Hermes Agent** (optional if using as an OpenAI-compatible server for other tools):
   ```bash
   hermes --version
   ```

---

## Quick Installation

Run the automated installer on macOS or Linux (including Ubuntu/Debian VPS):

```bash
git clone https://github.com/aayurt/opencode-hermes-bridge.git
cd opencode-hermes-bridge
chmod +x install.sh
./install.sh
```

### What `install.sh` Does:
* **macOS:** Installs `launchd` services to `~/Library/LaunchAgents/` and loads them immediately.
* **Linux (systemd):** Installs unit files to `/etc/systemd/system/`, runs `daemon-reload`, and enables `opencode-serve` and `opencode-proxy`.
* **Hermes Config:** If `hermes` is in `PATH`, registers the `/oc` plugin and `opencode-direct` model provider.

---

## Usage

### Mode 1: Hermes Model Switcher

Switch your current conversation to OpenCode:
```
/model opencode
```
Or start a Hermes CLI chat directly:
```bash
hermes -m opencode
```

Multi-turn session history is maintained automatically based on your initial conversation thread.

### Mode 2: `/oc` Slash Command

Query OpenCode at any time without switching models:
```
/oc Explain the routing architecture in this project
```

**Subcommands:**
* `/oc status` — Display the active OpenCode session ID.
* `/oc reset` — Reset conversation history and start a fresh session on the next prompt.

### Mode 3: Standard OpenAI API

The proxy provides an OpenAI-compatible endpoint at `http://127.0.0.1:4098/v1`:

```bash
curl http://127.0.0.1:4098/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "opencode",
    "messages": [
      {"role": "user", "content": "Hello OpenCode!"}
    ]
  }'
```

---

## Service Management

### Linux (systemd)
```bash
# Check service status
systemctl status opencode-serve
systemctl status opencode-proxy

# View live logs
journalctl -u opencode-proxy -f
journalctl -u opencode-serve -f

# Restart services
sudo systemctl restart opencode-serve opencode-proxy
```

### macOS (launchd)
```bash
# Check logs
tail -f ~/.hermes/profiles/mind-slayer/logs/opencode-proxy.log
tail -f ~/.hermes/profiles/mind-slayer/logs/opencode-serve.log

# Restart services
launchctl unload ~/Library/LaunchAgents/com.user.opencode-serve.plist
launchctl load ~/Library/LaunchAgents/com.user.opencode-serve.plist

launchctl unload ~/Library/LaunchAgents/com.user.opencode-proxy.plist
launchctl load ~/Library/LaunchAgents/com.user.opencode-proxy.plist
```

---

## Remote Access (SSH Tunneling)

To forward the VPS OpenCode service to your local machine:

```bash
ssh -N -L 14098:127.0.0.1:4098 SuperVPS
```

Then query the VPS OpenCode instance locally at `http://127.0.0.1:14098/v1`.

---

## License

MIT
