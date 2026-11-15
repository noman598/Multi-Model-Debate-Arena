# Fundamentals of Agentic AI (Powered by Groq)

A simple, single-file prototype designed to teach **everything you need to know about Agentic AI** without frameworks like LangChain.

Powered by **Groq** for near-instant inference and high-accuracy tool calling with open-weights models (`openai/gpt-oss-120b`).

The entire system lives in a single file: **[`main.py`](file:///d:/dev/arena/main.py)** (~180 lines of well-commented Python).

---

## ⚡ Why Groq for Agentic AI?

1. **Ultra-Fast Inference**: Groq's LPUs process 250–300+ tokens/second. In an agentic loop where the agent might take 2–5 sequential steps, speed is the difference between waiting 15 seconds vs. 1 second.
2. **Generous Free Tier**: Free API keys with ample rate limits for learning and prototyping.
3. **Top-Tier Tool Calling**: `openai/gpt-oss-120b` accurately generates parallel tool calls and adheres to JSON schemas.

---

## 🧠 What Makes an AI "Agentic"?

A standard chatbot is **passive**: it takes a prompt and produces text based only on static training data.

An **AI Agent** is **active**:
1. **Perceives**: Takes your goal and reviews its conversation memory.
2. **Reasons**: Decides whether it has enough information or if it must interact with the world.
3. **Acts**: Calls external tools (APIs, calculators, databases, code execution).
4. **Observes**: Receives output from the tools.
5. **Self-Corrects**: If a tool returns an error, the agent observes the failure and tries another approach.
6. **Synthesizes**: Produces the final answer once the objective is met.

This iterative loop is known as **ReAct (Reason + Act)**.

---

## 🏛️ The 5 Fundamental Components of an AI Agent

```
                      +-------------------+
                      |    User Prompt    |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   Agent Memory    | <------------------------+
                      | (messages: list)  |                          |
                      +---------+---------+                          |
                                |                                    |
                                v                                    |
                       [ 1. REASONING ]                              |
                       Calls Groq with                               |
                      messages + tools                               |
                                |                                    |
            +-------------------+-------------------+                |
            |                                       |                |
   [ Tool Call Requested? ]                         |                |
            | YES                                   | NO             |
            v                                       v                |
     [ 2. ACTING ]                           [ 4. SYNTHESIS ]        |
   Execute matching Python                  Agent outputs final      |
     function from TOOL_MAP                     answer               |
            |                                                        |
            v                                                        |
    [ 3. OBSERVATION ]                                               |
  Append tool output back                                            |
   to Agent Memory --------------------------------------------------+
```

### 1. Tools (The Effectors)
Regular Python function in [`main.py`](file:///d:/dev/arena/main.py#L37-L135):
- `duckduckgo_search(query)`: Free web and instant answer search to find downtown venues, patios, reviews, and outdoor seating. Zero API key needed.

### 2. Tool Schemas (The Contract)
Standard JSON schemas in [`main.py`](file:///d:/dev/arena/main.py#L140-L170) telling Groq:
- What search capabilities exist.
- What query arguments and formats are expected.

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

### 3. Test Searching for Downtown Spots
Try asking:
> *"Find a place near downtown Austin with outdoor seating and great reviews."*
> *"What are top-rated restaurants near downtown Chicago with a patio?"*

Watch the terminal as Groq calls `duckduckgo_search` to find real-world options, examines review highlights, and synthesizes a curated recommendation!
