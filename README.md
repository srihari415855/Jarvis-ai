# JARVIS (v0.1 Foundation)

Local-first personal AI agent designed to run autonomously on personal hardware with local LLM reasoning and strict permission-gated system control.

---

## 1. Project Overview

JARVIS is inspired by the personal assistant concept from Iron Man, engineered with privacy-first and security-first principles:
- **Local-first execution:** LLM inference runs locally via Ollama; no prompts or credentials leave the machine.
- **Strict least-privilege automation:** AI reasoning is strictly decoupled from tool execution. Every action passes through an explicit permission layer with default-deny policies.
- **Hardware-tailored design:** Optimized for personal workstations (AMD Ryzen 5, 24 GB DDR5 RAM, NVIDIA RTX 3050 6 GB VRAM).

---

## 2. Architecture

```
                         ┌──────────────┐
                         │     USER     │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ CLI (main.py)│
                         └──────┬───────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │     JARVIS AGENT     │
                    │   (core/agent.py)    │
                    │ Context              │
                    │ Reasoning            │
                    │ Planning             │
                    │ Orchestration        │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                                 ▼
     ┌────────────────┐                ┌─────────────────┐
     │  OLLAMA CLIENT │                │  TOOL REGISTRY  │
     │(models/        │                │(tools/          │
     │ ollama_client) │                │ registry.py)    │
     │ Local LLM      │                │ Tool discovery  │
     │ Chat           │                │ Tool schemas    │
     └────────────────┘                └────────┬────────┘
                                                │
                                                ▼
                                     ┌────────────────────┐
                                     │ PERMISSION MANAGER │
                                     │(core/permissions)  │
                                     │ Risk assessment    │
                                     │ Policy             │
                                     │ Confirmation       │
                                     │ Audit (security/)  │
                                     └─────────┬──────────┘
                                               │
                                            ALLOW
                                               │
                                               ▼
                                     ┌────────────────────┐
                                     │   TOOL EXECUTOR    │
                                     │(tools/executor.py) │
                                     └─────────┬──────────┘
                                               │
                   ┌───────────────────────────┼───────────────────────────┐
                   ▼                           ▼                           ▼
            get_system_info        list_allowed_applications       open_application
            (Safe OS/CPU/RAM)        (Strict Allowlist)         (Notepad/Calc/Explorer)
```

---

## 3. Requirements

- **Operating System:** Windows 10/11
- **Python:** 3.12+ (tested on Python 3.14)
- **Local LLM Engine:** [Ollama](https://ollama.com/) running locally (`ollama serve`)
- **Package Manager:** `pip`
- **Hardware Recommended:** >= 16 GB RAM, dedicated NVIDIA GPU (>= 6 GB VRAM) for quantized models.

---

## 4. Installation

Clone repository and initialize the Python virtual environment:

```bash
git clone <repo-url> "D:\AI Agent\Jarvis"
cd "D:\AI Agent\Jarvis"

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

---

## 5. Environment Setup

Create `.env` based on `.env.example`:

```bash
cp .env.example .env
```

Configuration variables:
```env
JARVIS_NAME=Jarvis
JARVIS_VERSION=0.1.0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:26b
LOG_LEVEL=INFO
```

---

## 6. Running JARVIS

### Interactive CLI Mode
```bash
python main.py
```

Built-in commands inside the CLI:
- `help` / `/help` - List CLI commands
- `status` / `/status` - View Ollama connection and active model
- `tools` / `/tools` - Display registered safe tools
- `audit` / `/audit` - Display recent security audit logs
- `clear` / `/clear` - Reset conversational context
- `exit` / `quit` - Terminate session cleanly

### Minimal FastAPI Server
```bash
uvicorn server.api:app --host 127.0.0.1 --port 8000
```
Health check endpoint: `GET http://127.0.0.1:8000/health`

---

## 7. Running Tests

Run the full pytest suite inside the virtual environment:

```bash
pytest tests/ -v
```

All unit tests run fully in-memory with mocked subprocess and HTTP fixtures, ensuring zero external side effects.

---

## 8. Current Capabilities (v0.1 Foundation)

- [x] **Local LLM Client:** Communicates with local Ollama instance (`/api/chat`, `/api/tags`).
- [x] **Agent Reasoning & Planner:** Constructs structured system prompts and parses JSON tool intents.
- [x] **Permission & Policy Gate:** Evaluates risks (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) with strict Default-Deny.
- [x] **Structured Security Auditing:** Logs all startup/shutdown events, permission decisions, and tool executions in `logs/audit.jsonl` with automatic credential redaction.
- [x] **3 Safe Windows Tools:**
  1. `get_system_info`: Queries CPU, OS, RAM, Python version without leaking tokens or credentials.
  2. `list_allowed_applications`: Lists common applications and notes system-wide application launching support.
  3. `open_application`: Launches any installed desktop application, browser, utility, or tool on Windows (resolving via direct paths, system PATH, Windows Registry App Paths, or Start Menu shortcuts) with live PID verification.
- [x] **FastAPI Health Endpoint:** Minimal `GET /health` returning service status.

---

## 9. Current Limitations

- **Single-turn tool execution:** Complex multi-step autonomous planning is reserved for subsequent phases.
- **Application control is restricted:** Only allowlisted executables can be opened.
- **No shell access:** Arbitrary command line or script execution is strictly forbidden in v0.1.

---

## 10. Security Model

1. **Default Deny:** Unknown tools, unregistered applications, and arbitrary paths are unconditionally blocked.
2. **Prohibited Patterns Filter:** Commands attempting destructive operations (e.g. `rmdir`, `del /`, `format`, encoded powershell) are dropped immediately.
3. **Credential Protection:** Passwords, tokens, API keys, and sensitive environment secrets are sanitized prior to logging.
4. **Decoupled Execution:** The LLM cannot directly execute code; it can only request tools from the registry.

---

## 11. Future Roadmap (NOT Yet Implemented)

The following capabilities are deliberately out of scope for Day 1 and will be introduced in subsequent phases:

- [ ] **Voice & Audio:** Wake-word, Speech-To-Text (Whisper), and Text-To-Speech (Piper/Coqui).
- [ ] **Vision & Screen Understanding:** Real-time screenshot capture and OCR/VLM reasoning.
- [ ] **Browser Automation:** Playwright automation workflows.
- [ ] **Filesystem Operations:** Safe sandboxed file reading and writing.
- [ ] **Long-term Memory:** SQLite vector/keyword database for user preferences and persistent memories.
- [ ] **Android Client:** Flutter client interfacing via local WebSocket / ADB.
- [ ] **Multi-Agent Collaboration:** Specialized subagents for planning and execution.