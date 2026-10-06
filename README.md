# JARVIS (Local AI Agent, Voice Assistant & GUI Control)

Local-first personal AI agent designed to run autonomously on personal hardware with local LLM reasoning, local voice conversation pipeline, computer perception, and strict permission-gated browser and desktop GUI control.

---

## 1. Project Overview

JARVIS is inspired by the personal assistant concept from Iron Man, engineered with privacy-first and security-first principles:
- **100% Local-first execution:** LLM inference runs locally via Ollama, speech-to-text runs locally via `faster-whisper`, text-to-speech runs locally via Windows SAPI, and computer control runs locally via Playwright and Windows UI Automation. Zero prompts, audio recordings, or credentials leave the machine.
- **In-Memory Audio Processing:** Audio is captured directly into NumPy float32 buffers and processed in-memory. No permanent audio files or speech recordings are persisted to disk.
- **Computer Perception & Empirical Verification:** Every browser and GUI action is observed and verified against actual system state before reporting completion. "No fabrication" is strictly enforced.
- **Strict least-privilege automation:** AI reasoning is strictly decoupled from tool execution. Every action passes through an explicit permission layer with default-deny policies.
- **Hardware-tailored design:** Optimized for personal workstations (AMD Ryzen 5, 24 GB DDR5 RAM, NVIDIA RTX 3050 6 GB VRAM).

---

## 2. Architecture

```
                         ┌───────────────┐
                         │     USER      │
                         └───────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
              ┌───────────┐             ┌────────────┐
              │ CLI Input │             │ Microphone │
              └─────┬─────┘             └──────┬─────┘
                    │                           │
                    │                           ▼
                    │                     ┌──────────┐
                    │                     │ VoiceLoop│
                    │                     └────┬─────┘
                    │                          │
                    │                          ▼
                    │                     ┌──────────┐
                    │                     │ Local STT│
                    │                     └────┬─────┘
                    │                          │
                    └────────────┬─────────────┘
                                 ▼
                       ┌───────────────────┐
                       │    JarvisAgent    │
                       │                   │
                       │ Context History   │
                       │ Multi-step Intent │
                       └─────────┬─────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │                          │
                    ▼                          ▼
             ┌─────────────┐         ┌───────────────────┐
             │ OllamaClient│         │TaskExecutionLoop  │
             │ Local LLM   │         │                   │
             └─────────────┘         │ UNDERSTAND        │
                                     │     ↓             │
                                     │ OBSERVE           │
                                     │     ↓             │
                                     │ PLAN              │
                                     │     ↓             │
                                     │ PERMISSION CHECK  │
                                     │     ↓             │
                                     │ ACT               │
                                     │     ↓             │
                                     │ OBSERVE           │
                                     │     ↓             │
                                     │ VERIFY            │
                                     └─────────┬─────────┘
                                               │
                                               ▼
                                     ┌──────────────────┐
                                     │ PermissionManager│
                                     └────────┬─────────┘
                                              │
                                              ▼
                                       ┌────────────┐
                                       │ToolExecutor│
                                       └──────┬─────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                    Browser Control    Desktop Perception     Applications
                     (Playwright)          & GUI UIA          & Filesystem
                         │                    │                    │
                         └────────────────────┼────────────────────┘
                                              │
                                              ▼
                                      ActionVerifier
                               (Empirical State Confirmation)
                                              │
                                              ▼
                                         Tool Result
                                              │
                                              ▼
                                         JarvisAgent
                                              │
                                              ▼
                                       Response Text
                                              │
                                              ▼
                                       ┌────────────┐
                                       │ Local TTS  │
                                       └─────┬──────┘
                                             │
                                             ▼
                                         🔊 Speaker
```

---

## 3. Subsystem Breakdown

1. **User Input:**
   - **CLI Input:** Direct text command line interface in terminal.
   - **Microphone:** Audio input managed via `MicrophoneManager` (`sounddevice`, 16 kHz mono float32 in-memory).
2. **Voice Pipeline (Phase 2):**
   - **VoiceLoop (`voice/voice_loop.py`):** Push-to-talk orchestration loop with latency benchmarking and markdown-to-speech cleaning.
   - **Local STT (`voice/stt.py`):** 100% offline speech-to-text using `faster-whisper` (`base` model on CUDA/CPU).
   - **Local TTS (`voice/tts.py`):** Zero-latency text-to-speech powered by Windows SAPI (`win32com.client.Dispatch("SAPI.SpVoice")`).
3. **Computer Perception & Verification (Phase 3):**
   - **ComputerPerception (`tools/computer/perception.py`):** Observes foreground window, executable name, PID, accessible UI elements via Windows UI Automation, and ephemeral on-demand screenshots without continuous surveillance.
   - **ComputerControl (`tools/computer/control.py`):** Structured desktop GUI automation (focus window, click button by accessible name, type text, send safe hotkeys). Arbitrary raw mouse coordinates and dangerous hotkeys (e.g. `Alt+F4`, `Ctrl+Alt+Del`) are blocked.
   - **PlaywrightBrowserManager (`tools/browser/browser.py`):** Automated browser session management supporting Chrome and Chromium, structured DOM queries (`get_by_role`, `get_by_text`, `locator`), typing, clicking, and page inspection.
   - **ActionVerifier (`tools/computer/verification.py`):** Validates post-execution state (URL change, search result presence, window focus) before confirming task completion.
   - **TaskExecutionLoop (`core/execution_loop.py`):** Orchestrates multi-step computer tasks adhering to the observe-plan-act-observe-verify cycle with configurable retry limits (default: 2 retries).
4. **Security & Safety Protections:**
   - **Prompt Injection Defense:** Webpage text is treated strictly as data, not authority. Untrusted injection patterns (e.g. `ignore all instructions`, `developer mode`, `system: override`) are automatically sanitized.
   - **ToolRegistry (`tools/registry.py`):** Central catalog of all registered safe tools. Unknown tools and unvalidated actions are immediately rejected.
   - **PermissionManager (`core/permissions.py`):** Centralized risk-level policy enforcement (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), destructive command pattern scanning, and explicit user confirmation gating.
   - **AuditLogger (`security/audit.py`):** Structured audit events logged to `logs/audit.jsonl` with secret redaction.

---

## 4. Requirements & Hardware

- **Operating System:** Windows 10/11 (64-bit)
- **Python:** 3.12+ (tested on Python 3.14.6)
- **Local LLM Engine:** [Ollama](https://ollama.com/) running locally (`ollama serve`)
- **GPU Acceleration:** Dedicated NVIDIA GPU (e.g. RTX 3050 6 GB VRAM) recommended for sub-second inference.
- **Audio Hardware:** Built-in or external microphone and speakers/headphones.

---

## 5. Installation & Setup

1. **Activate Virtual Environment:**
   ```powershell
   cd "D:\AI Agent\Jarvis"
   .venv\Scripts\activate
   ```

2. **Install Dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Install Playwright Browsers:**
   ```powershell
   playwright install chromium
   ```

4. **Configure Environment (`.env`):**
   ```env
   JARVIS_NAME=Jarvis
   JARVIS_VERSION=0.3.0
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2:3b
   LOG_LEVEL=INFO

   # Voice Configuration
   VOICE_ENABLED=true
   STT_MODEL=base
   STT_DEVICE=auto
   STT_COMPUTE_TYPE=auto
   TTS_ENABLED=true
   VOICE_LANGUAGE=en
   VOICE_HOTKEY=F9
   VOICE_LOG_LEVEL=INFO
   ```

5. **Ensure Local Ollama Model is Running:**
   ```powershell
   ollama run llama3.2:3b
   ```

---

## 6. Running JARVIS

### Interactive CLI Mode (Default)
```powershell
python main.py
```
Or explicitly:
```powershell
python main.py --mode cli
```

**Commands inside CLI:**
- `voice` - Switch to Push-to-Talk Voice Mode
- `status` - Check Ollama, microphone, TTS, and tool status
- `tools` - List all registered safe tools
- `audit` - View recent security events
- `clear` - Clear conversation context
- `help` - Show available commands
- `exit` - Shut down JARVIS

### Push-to-Talk Voice Mode
```powershell
python main.py --mode voice
```
- Press **[Enter]** to speak (records 4 seconds of speech).
- JARVIS transcribes speech locally, reasons via Ollama, executes tools if requested, and speaks the response aloud through your speakers.
- Type `cli` anytime to return to standard text CLI mode.

---

## 7. Running Test Suite

Execute all 120 automated unit, security, and integration tests:

```powershell
pytest tests/ -v
```

All 120 tests run with mocked system and hardware calls, verifying:
- Speech-to-text (`faster-whisper`)
- Text-to-speech (Windows SAPI)
- Microphone audio buffer capture
- VoiceLoop interaction and latency tracking
- End-to-end voice integration and permission gating
- Windows application launcher and PID resolution
- Browser navigation, interaction, inspection, and close tools
- Prompt injection filtering and webpage sanitization
- Action verification and empirical condition checking
- TaskExecutionLoop multi-step planning, retries, and failure recovery
- Computer perception active window detection and UIA tree inspection
- Computer control window focus, clicking, typing, and hotkey security
- Destructive command rejection and permission enforcement
- Filesystem directory and safe file reading limits
- Ollama client connectivity and fallback handling

---

## 8. Live Demonstration

Run the automated live end-to-end demonstration script:

```powershell
python demo_phase3.py
```

This tests:
1. **Live Search:** `"Open Chrome and search for Python tutorials."`
2. **Live URL Navigation:** `"Open Chrome and go to github.com."`
3. **Verified Search Results:** `"Open Chrome, go to Google, search for Python, and tell me whether search results appeared."`
4. **Security Enforcement:** Rejection of malicious arbitrary shell execution.