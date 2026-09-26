# HQ Local Chat

The President Console now includes local conversational chat through Ollama.

## Modes
- **HQ Assistant**: general conversation and coordination.
- **Atlas · President**: executive planning and cross-project guidance.
- **Horizon · Advisor**: evidence, improvement, risk and future-readiness discussion.
- **Command HQ** remains separate: commands enter the durable Runtime v2 queue.

## Local model discovery
The dashboard calls Ollama `GET /api/tags` at `http://127.0.0.1:11434` and populates the model selector from models installed on the computer. Chat calls Ollama `POST /api/chat`. No cloud API is required for this path.

Optional environment variables:
- `OLLAMA_BASE_URL` default `http://127.0.0.1:11434`
- `HQ_OLLAMA_MODEL` preferred installed model name

## Start
1. Start Ollama.
2. Start `intelligent-agency/start_hq_dashboard.bat`.
3. Open the **Chat** tab.
4. Select HQ, Atlas or Horizon and an installed model.
5. Chat normally. `Ctrl+Enter` sends a message.

## Boundaries
The chat persona is conversational. It does not itself prove that GitHub, browser, deployment or other external work occurred. Consequential work should go through Command HQ and the governed Runtime/Horizon execution path.

Chat history currently lives only in the browser page and is reset by **New chat** or page reload. Persistent conversation memory can be added later with explicit scopes and retention controls.
