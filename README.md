# JARVIS (Local AI Agent & Voice Assistant)

Local-first personal AI agent designed to run autonomously on personal hardware with local LLM reasoning, local voice conversation pipeline, and strict permission-gated system control.

---

## 1. Project Overview

JARVIS is inspired by the personal assistant concept from Iron Man, engineered with privacy-first and security-first principles:
- **100% Local-first execution:** LLM inference runs locally via Ollama, speech-to-text runs locally via `faster-whisper`, and text-to-speech runs locally via Windows SAPI. Zero prompts, audio recordings, or credentials leave the machine.
- **In-Memory Audio Processing:** Audio is captured directly into NumPy float32 buffers and processed in-memory. No permanent audio files or speech recordings are persisted to disk.
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
                       │ Context           │
                       │ Reasoning         │
                       │ Orchestration     │
                       └─────────┬─────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │                          │
                    ▼                          ▼
             ┌─────────────┐           ┌──────────────┐
             │ OllamaClient│           │ ToolRegistry │
             │ Local LLM   │           └──────┬───────┘
             └─────────────┘                  │
                                              ▼
                                    ┌──────────────────┐
                                    │ PermissionManager│
                                    └────────┬─────────┘
                                             │
                                             ▼
                                      ┌────────────┐
                                      │ToolExecutor│
                                      └────────────┘
                                             │
                         ┌───────────────────┼──────────────────┐
                         ▼                   ▼                  ▼
                    WindowsApp            Browser          Filesystem
                       Tool                 Tool              Tool
                         │                   │                  │
                         └───────────────────┼──────────────────┘
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
2. **Voice Pipeline:**
   - **VoiceLoop (`voice/voice_loop.py`):** Push-to-talk orchestration loop with latency benchmarking and markdown-to-speech cleaning.
   - **Local STT (`voice/stt.py`):** 100% offline speech-to-text using `faster-whisper` (`base` model on CUDA/CPU).
   - **Local TTS (`voice/tts.py`):** Zero-latency text-to-speech powered by Windows SAPI (`win32com.client.Dispatch("SAPI.SpVoice")`).
3. **Core Reasoning & Agent:**
   - **JarvisAgent (`core/agent.py`):** Maintains conversational context history, crafts system prompts with registered tool schemas, and formats tool outputs.
   - **OllamaClient (`models/ollama_client.py`):** Communicates with local Ollama (`llama3.2:3b`) with GPU acceleration.
4. **Security & Tool Execution:**
   - **ToolRegistry (`tools/registry.py`):** Central catalog of all safe tools.
   - **PermissionManager (`core/permissions.py`):** Risk-level policy verification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), parameter inspection, and user confirmation gating.
   - **ToolExecutor (`tools/executor.py`):** Dispatches approved tool actions.
   - **AuditLogger (`security/audit.py`):** Comprehensive audit logging in `logs/audit.jsonl` with secret redaction.
5. **Tool Catalog:**
   - **WindowsApp Tool (`tools/computer/applications.py`):** Launch any installed Windows desktop application (Notepad, Calculator, Word, Chrome, etc.) with real PID verification; query host CPU/RAM/OS specs (`get_system_info`).
   - **Browser Tool (`tools/browser/browser.py`):** Safe URL navigation and web searches in default browser with scheme validation (`http`/`https`).
   - **Filesystem Tool (`tools/filesystem/filesystem.py`):** Read-only local directory browsing (`list_directory`) and safe file reading (`read_file`) with line and size limits.

---

## 4. Requirements & Hardware

- **Operating System:** Windows 10/11 (64-bit)
- **Python:** 3.12+ (tested on Python 3.14)
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

3. **Configure Environment (`.env`):**
   ```env
   JARVIS_NAME=Jarvis
   JARVIS_VERSION=0.2.0
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

4. **Ensure Local Ollama Model is Running:**
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

Execute all 60 automated unit and integration tests:

```powershell
pytest tests/ -v
```

All 60 tests run with mocked system and hardware calls, verifying:
- Speech-to-text (`faster-whisper`)
- Text-to-speech (Windows SAPI)
- Microphone audio buffer capture
- VoiceLoop interaction and latency tracking
- End-to-end voice integration and permission gating
- Windows application launcher and PID resolution
- Browser tool URL sanitization
- Filesystem directory and file reading limits
- Ollama client connectivity and fallback handling