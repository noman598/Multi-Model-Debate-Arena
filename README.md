# Production-Grade Agentic AI: Memory, Telemetry & Loop Protection (Groq + SQLite)

A clean, modular Agentic AI system built in **pure Python** without framework bloat.

Demonstrates **what really matters in production**:
1. **Persistent & Compressed Memory**: SQLite storage + sliding-window rolling summaries.
2. **4-Layer Infinite Loop Protection**: Defense-in-depth against repetitive tool calls.
3. **Structured Telemetry & Auditing**: Latency measurement (ms), file logs (`agent_audit.log`), and SQLite audit trail.

---

## 📂 Modular Architecture

```
arena/
├── evals.py          # Automated 10-test benchmark suite (evaluates the 5 key metrics)
├── langsmith_demo.py # Minimal, standalone LangSmith tracing demo
├── logger.py         # Structured console + file logger (agent_audit.log)
├── memory.py         # SQLite persistence + Sliding-Window Auto-Summarization + Audit Logs
├── tools.py          # Live REST APIs with Layer 2 Actionable Return Guidance + LangSmith @traceable
├── agent.py          # ReAct Engine with 4-Layer Loop Protection + LangSmith @traceable
├── main.py           # Production CLI (< 130 lines) with 'audit', 'summary', 'history' commands
├── pyproject.toml    # Project configuration and dependencies (including langsmith)
└── .env              # Groq & LangSmith API configuration
```

---

## 🛡️ The 4-Layer Infinite Loop Protection

When an agent gets stuck repeatedly calling the same tool with the same arguments, this 4-layer defense intercepts and recovers:

```
[Agent Tool Call Request]
           │
           ▼
┌──────────────────────────────────────┐
│ Layer 1: Code-Level Interceptor      │  Matches hash("tool:sorted_json_args").
│ (agent.py)                           │  If duplicate: Intercepts & sends warning observation!
└──────────────────┬───────────────────┘
                   │ If new call -> Executes Tool
                   ▼
┌──────────────────────────────────────┐
│ Layer 2: Actionable Tool Outputs     │  Tools NEVER return empty strings or blank 404s.
│ (tools.py)                           │  Always returns explicit guidance: "Do not retry query X".
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ Layer 3: System Prompt Constraints   │  Explicit negative constraints in system prompt:
│ (agent.py)                           │  "Never retry identical failed queries."
└──────────────────┬───────────────────┘
                   │
                   ▼ (If step >= max_steps)
┌──────────────────────────────────────┐
│ Layer 4: Hard Safety Floor           │  Forces `tool_choice="none"` to produce text.
│ (agent.py)                           │  Guarantees zero runaway API loops.
└──────────────────────────────────────┘
```

---

## 🧠 The 3-Tier Memory Flow

```
 ┌─────────────────────────────────────────────────────────┐
 │               1. LONG-TERM STORAGE (SQLite)             │
 │  Complete, immutable log of every raw message ever sent │
 │  Stored in `agent_memory.db` (survives restarts)        │
 └────────────────────────────┬────────────────────────────┘
                              │
                    Trigger: > 6 turns
                              │
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │           2. COMPRESSED MEMORY (Auto-Summary)           │
 │  Groq condenses older turns into an evolving paragraph: │
 │  "User is Alice, lives in Chicago, planning Tokyo trip" │
 └────────────────────────────┬────────────────────────────┘
                              │
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │            3. WORKING CONTEXT (Sent to Groq)            │
 │  [System Prompt]                                        │
 │  + [Recalled Summary of Past Conversation]              │
 │  + [Only Latest 4 Raw Messages]                         │
 └─────────────────────────────────────────────────────────┘
```

---

## ⚡ Quickstart

1. Activate your virtual environment:
```powershell
.venv\Scripts\Activate.ps1
```

2. Run the interactive production agent:
```powershell
python main.py
```

3. Production inspection commands during chat:
* `audit`   - View operational telemetry table (latency in ms, duplicate intercepts).
* `summary` - View active compressed session summary.
* `history` - View raw SQLite conversation audit log.
* `stats`   - View memory window bounds and message count.
* `exit`    - Save and exit safely.

### 1. Tools (The Effectors)
Regular Python functions in [`main.py`](file:///d:/dev/arena/main.py#L38-L150):
- `get_weather(city)`: Real-time global weather from Open-Meteo REST API (free, no key required).
- `get_wikipedia_summary(topic)`: Instant encyclopedic summaries from Wikipedia REST API (free, no key required).
- `calculate(expression)`: Safe math and unit conversion evaluation.

### 2. Tool Schemas (The Contract)
Standard JSON schemas in [`main.py`](file:///d:/dev/arena/main.py#L160-L225) telling Groq:
- What tool functions exist.
- What parameter arguments and types are expected.

### 3. Agent State & Memory (The Context)
The agent's working memory is simply a Python list:
```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "What is the weather in Tokyo?"},
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "content": "Rainy, 14°C"},
]
```

### 4. The ReAct Loop (The Engine)
A `while` loop that runs until the model stops requesting tools:
```python
while step < max_steps:
    response = client.chat.completions.create(model=self.model, messages=self.messages, tools=TOOL_SCHEMAS)
    if response.choices[0].message.tool_calls:
        # Execute tools and append observations
        ...
    else:
        # Final answer reached
        return response.choices[0].message.content
```

### 5. Self-Correction
If a tool execution raises an exception, the system catches the error and sends it back to Groq as the tool observation:
```python
except Exception as err:
    observation = f"Error executing {func_name}: {err}"
```
This enables the agent to read the error message, adapt its reasoning, and retry with corrected parameters.

---

## 🚀 Quickstart

### 1. Set your Groq API Key
Get a free key from [console.groq.com/keys](https://console.groq.com/keys).

Create a `.env` file or export it:
```bash
# In .env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

### 2. Run the Agent
```bash
uv run python main.py
```

---

## 🔍 LangSmith Tracing & Observability

You can view full agent trajectories, token metrics, latency, and tool inputs/outputs in real-time in your LangSmith dashboard:

1. Add your LangSmith key to `.env`:
```env
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
LANGSMITH_API_KEY="lsv2_pt_your_key_here"
LANGSMITH_PROJECT="agentic-arena"
```

2. Run the quickstart tracing demo:
```powershell
python langsmith_demo.py
```

3. Open your dashboard at [smith.langchain.com](https://smith.langchain.com) to view nested execution traces!

---

## 📊 Agent Evaluation Suite (`evals.py`)

Run an automated 10-test benchmark suite evaluating the 5 key production metrics:
1. **Final Answer Correctness**: Factual grounding & keyword matches.
2. **Correct Tool Selection**: Verification that the right tool was selected (or zero tools for chit-chat).
3. **Correct Trajectory**: Step efficiency & verification that `max_steps` was not exceeded.
4. **Latency / Speed**: Execution duration under the benchmark threshold (< 6.5s).
5. **Safety & Reliability**: Zero duplicate tool loops and clean error recovery.

Run the evaluation suite:
```powershell
python evals.py
```
