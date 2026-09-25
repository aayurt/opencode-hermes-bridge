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
* **Zero-Downtime Daemon:** Managed via macOS `launchd` for automatic startup on boot and auto-restart on crash.

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

1. **OpenCode CLI** installed and authenticated (v1.18.0 or newer):
   ```bash
   opencode --version
   ```
2. **Hermes Agent** installed:
   ```bash
   hermes --version
   ```
3. **Python 3.10+** (Python 3.14 recommended on macOS with Apple Silicon).

---

## Quick Installation

Run the automated installer:

```bash
git clone https://github.com/aayurt/opencode-hermes-bridge.git
cd opencode-hermes-bridge
chmod +x install.sh
./install.sh
```

The script will:
1. Copy the proxy service to `~/.hermes/profiles/<profile>/scripts/`.
2. Register and enable the `opencode-slash` Hermes plugin.
3. Configure Hermes provider `opencode-direct` and alias `opencode`.
4. Deploy and start background `launchd` daemons on ports `4097` (warm engine) and `4098` (OpenAI proxy).

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

## Service Management (macOS)

Both services are managed via `launchd`:

```bash
# Check status / logs
tail -f ~/.hermes/profiles/mind-slayer/logs/opencode-proxy.log
tail -f ~/.hermes/profiles/mind-slayer/logs/opencode-serve.log

# Restart services
launchctl unload ~/Library/LaunchAgents/com.user.opencode-serve.plist
launchctl load ~/Library/LaunchAgents/com.user.opencode-serve.plist

launchctl unload ~/Library/LaunchAgents/com.user.opencode-proxy.plist
launchctl load ~/Library/LaunchAgents/com.user.opencode-proxy.plist
```

---

## License

MIT
