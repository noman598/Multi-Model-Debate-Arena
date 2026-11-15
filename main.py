"""
=============================================================================
           MINIMAL AGENTIC AI PROTOTYPE (POWERED BY GROQ)
=============================================================================

This file is designed for learning the core fundamentals of AI Agents.
No LangChain or framework bloat. Just pure Python + Groq LPU inference.

An AI Agent consists of 5 fundamental components:
  1. TOOLS: Plain Python functions that perform actions or call real APIs.
  2. TOOL SCHEMAS: JSON schemas telling the LLM what tools exist and their arguments.
  3. STATE & MEMORY: A message list tracking conversation and tool execution history.
  4. THE ReAct LOOP (Reason + Act):
       - LLM receives context -> Decides whether to call a tool or give an answer.
       - If tool call: Execute tool -> Send result (Observation) back to LLM.
       - Repeat until the LLM decides it has enough information to answer.
  5. ENVIRONMENT FEEDBACK & SELF-CORRECTION:
       - Returning tool errors to the LLM allows it to self-correct and retry.
=============================================================================
"""

import json
import os
import urllib.parse
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import httpx
from groq import Groq, BadRequestError

# Load environment variables (GROQ_API_KEY, GROQ_MODEL, etc.)
load_dotenv()


# =============================================================================
# 1. TOOLS: Real, free, lightweight REST APIs via httpx
# =============================================================================

def get_weather(city: str) -> str:
    """
    Get live, real-time weather for any city using Open-Meteo.
    Completely free, no API key required, instant JSON response.
    """
    try:
        with httpx.Client(timeout=8.0) as client:
            # Step 1: Geocode the city name to latitude and longitude
            geo_url = (
                f"https://geocoding-api.open-meteo.com/v1/search?"
                f"name={urllib.parse.quote(city)}&count=1&language=en&format=json"
            )
            geo_resp = client.get(geo_url)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

            results = geo_data.get("results")
            if not results:
                return f"Could not find coordinates for city: '{city}'"

            location = results[0]
            name = location.get("name", city)
            country = location.get("country", "")
            lat = location.get("latitude")
            lon = location.get("longitude")

            # Step 2: Fetch current weather metrics
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m"
                f"&temperature_unit=celsius&wind_speed_unit=kmh"
            )
            w_resp = client.get(weather_url)
            w_resp.raise_for_status()
            w_data = w_resp.json()
            current = w_data.get("current", {})

            temp = current.get("temperature_2m")
            feels_like = current.get("apparent_temperature")
            humidity = current.get("relative_humidity_2m")
            wind = current.get("wind_speed_10m")

            return (
                f"Live Weather in {name}, {country}:\n"
                f"- Temperature: {temp}°C (feels like {feels_like}°C)\n"
                f"- Humidity: {humidity}%\n"
                f"- Wind Speed: {wind} km/h"
            )

    except Exception as err:
        return f"Weather API error: {err}"


def get_wikipedia_summary(topic: str) -> str:
    """
    Get a quick factual summary from Wikipedia about any topic, place, person, or landmark.
    Completely free, no API key required, official Wikipedia REST API.
    """
    try:
        formatted_topic = urllib.parse.quote(topic.strip().replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_topic}"
        headers = {"User-Agent": "AgentDemo/1.0 (educational-agent-bot)"}

        with httpx.Client(timeout=8.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 404:
                return f"No Wikipedia article found for '{topic}'."
            resp.raise_for_status()
            data = resp.json()

            title = data.get("title", topic)
            description = data.get("description", "")
            extract = data.get("extract", "")

            desc_line = f" ({description})" if description else ""
            return f"Wikipedia: {title}{desc_line}\n\n{extract}"

    except Exception as err:
        return f"Wikipedia API error: {err}"


def calculate(expression: str) -> str:
    """
    Safely evaluate a mathematical expression or unit conversion.
    Examples: '25 * 9/5 + 32', '150 * 0.18', '(450 / 4)'.
    """
    try:
        # Security: Allow only numbers and basic mathematical operators
        allowed_chars = set("0123456789+-*/().,% ")
        if not all(char in allowed_chars for char in expression):
            return "Error: Expression contains unsupported characters. Only basic arithmetic (+, -, *, /, %) is allowed."

        result = eval(expression, {"__builtins__": None}, {})
        return f"{expression} = {result}"

    except Exception as err:
        return f"Calculation error: {err}"


# Dispatch table: maps tool names from LLM to actual Python functions
TOOL_MAP = {
    "get_weather": get_weather,
    "get_wikipedia_summary": get_wikipedia_summary,
    "calculate": calculate,
}


# =============================================================================
# 2. TOOL SCHEMAS: The contract sent to the Groq LLM
# =============================================================================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current real-time live weather for any city in the world (temperature, humidity, wind).",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The name of the city, e.g. 'Chicago', 'Tokyo', 'London', 'Austin'.",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wikipedia_summary",
            "description": "Look up factual summaries, history, or background on any landmark, city, person, or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The landmark, place, person, or concept to look up, e.g. 'Millennium Park', 'Eiffel Tower', 'Chicago'.",
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate mathematical expressions or conversions (e.g. Celsius to Fahrenheit, tip percentages, price splits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate, e.g. '18.5 * 9/5 + 32' or '120 * 0.18'.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]


# =============================================================================
# 3. AGENT: State & The ReAct (Reason + Act) Loop
# =============================================================================

class SimpleAgent:
    """
    A minimal, framework-free AI Agent using Groq and lightweight API tools.
    """

    def __init__(self, client: Groq, model: str = "openai/gpt-oss-120b"):
        self.client = client
        self.model = model
        # Agent State / Working Memory: conversation history
        self.messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful and versatile AI Assistant with access to real tools.\n\n"
                    "Available Tools:\n"
                    "1. `get_weather(city)`: Fetch live current weather for any city worldwide.\n"
                    "2. `get_wikipedia_summary(topic)`: Look up verified factual overviews for places, landmarks, or people.\n"
                    "3. `calculate(expression)`: Perform math calculations or unit conversions.\n\n"
                    "Guidelines:\n"
                    "- When the user asks about weather, places, landmarks, or math, call the appropriate tool.\n"
                    "- Only call the tools listed above. Do not invent undeclared tools.\n"
                    "- Synthesize observations into a clear, direct, and pleasant response for the user."
                ),
            }
        ]

    def run(self, user_prompt: str, max_steps: int = 5) -> str:
        """
        Executes the ReAct loop:
          Step 1 (Reason): Groq LLM decides what to do based on messages + tool schemas.
          Step 2 (Act): If LLM requests a tool, execute the Python function.
          Step 3 (Observe): Pass the tool result back to the LLM.
          Repeat until LLM produces a final answer.
        """
        # Append user message to memory
        self.messages.append({"role": "user", "content": user_prompt})

        step = 0
        while step < max_steps:
            step += 1
            print(f"\n[Step {step}] Asking Groq ({self.model})...")

            # 1. Reason: Call Groq with current history and available tools
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except BadRequestError as err:
                # If the model attempted an unsupported tool or format error, fallback cleanly
                print(f"  [Notice] Model request validation note: {err.message}")
                print("  [Notice] Requesting direct answer from gathered observations...")
                try:
                    fallback_response = self.client.chat.completions.create(
                        model=self.model,
                        messages=self.messages + [{
                            "role": "user",
                            "content": "Please answer the request directly based on the context above. Do not call any tools."
                        }],
                    )
                    final_answer = fallback_response.choices[0].message.content or ""
                    self.messages.append({"role": "assistant", "content": final_answer})
                    return final_answer
                except Exception as inner_err:
                    return f"Agent stopped due to API error: {inner_err}"

            response_msg = response.choices[0].message

            # Check if LLM decided to call any tools
            tool_calls = response_msg.tool_calls

            if tool_calls:
                # Append assistant message with its tool calls to memory
                self.messages.append(response_msg.model_dump(exclude_none=True))

                # 2. Act: Execute each requested tool call
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args_str = tool_call.function.arguments

                    # Parse arguments safely
                    try:
                        func_args = json.loads(func_args_str) if func_args_str else {}
                    except json.JSONDecodeError:
                        func_args = {}

                    print(f"  -> [Tool Call] {func_name}({func_args})")

                    # Dispatch to real Python function
                    if func_name in TOOL_MAP:
                        try:
                            observation = str(TOOL_MAP[func_name](**func_args))
                        except Exception as err:
                            # Self-correction: return error so LLM can adapt
                            observation = f"Error executing {func_name}: {err}"
                    else:
                        observation = f"Error: Tool '{func_name}' does not exist. Available tools: {list(TOOL_MAP.keys())}"

                    print(f"  <- [Observation] {observation}")

                    # 3. Observe: Feed result back into conversation memory
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": observation,
                    })

                # Loop back to let the LLM inspect the observation!
                continue

            else:
                # 4. Final Answer: LLM completed reasoning and responded directly
                final_answer = response_msg.content or ""
                self.messages.append({"role": "assistant", "content": final_answer})
                return final_answer

        return "Agent stopped: Reached maximum reasoning steps."


# =============================================================================
# 4. RUNNER & INTERACTIVE CHAT
# =============================================================================

def main():
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # If no Groq API key is found, prompt the user
    if not api_key:
        print("=" * 60)
        print("No GROQ_API_KEY detected!")
        print("You can get a free API key at: https://console.groq.com/keys")
        print("\nEither add it to your .env file:")
        print("  GROQ_API_KEY=gsk_your_key_here")
        print("=" * 60)
        try:
            user_key = input("\nEnter your Groq API key now (or press Enter to exit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return
        if not user_key:
            return
        api_key = user_key

    client = Groq(api_key=api_key)
    agent = SimpleAgent(client=client, model=model)

    print("=" * 60)
    print("AI Agent Prototype (Powered by Groq)")
    print(f"Model: {model}")
    print("Real & Free API Tools (via httpx):")
    print("  1. get_weather            - Live global weather (Open-Meteo REST API)")
    print("  2. get_wikipedia_summary  - Instant facts & places (Wikipedia REST API)")
    print("  3. calculate              - Safe math & unit conversions")
    print("=" * 60)
    print("Try asking things like:")
    print("  - 'What is the weather in Chicago right now, and what is that in Fahrenheit?'")
    print("  - 'Tell me about Millennium Park and what the current weather is there.'")
    print("  - 'If a hotel room in Tokyo costs 18,500 Yen per night for 4 nights, what is the total?'")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Exiting.")
                break

            answer = agent.run(user_input)
            print(f"\nAgent: {answer}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
