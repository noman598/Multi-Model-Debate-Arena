"""
=============================================================================
           MINIMAL AGENTIC AI PROTOTYPE (POWERED BY GROQ)
=============================================================================

This file is designed for learning the core fundamentals of AI Agents.
No LangChain or framework bloat. Just pure Python + Groq LPU inference.

An AI Agent consists of 5 fundamental components:
  1. TOOLS: Plain Python functions that perform actions or retrieve data.
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

import html
import json
import os
import re
from typing import Any, Dict, List
from dotenv import load_dotenv
from groq import Groq
import httpx

# Load environment variables (GROQ_API_KEY, GROQ_MODEL, etc.)
load_dotenv()


# =============================================================================
# 1. TOOLS: Real actions the agent can perform in the environment
# =============================================================================

def duckduckgo_search(query: str) -> str:
    """
    Search DuckDuckGo using the free Instant Answer API with web search fallback.
    Completely free, no API key required.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    results = []

    # 1. Primary: DuckDuckGo Instant Answer API (Free, JSON)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "0",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    results.append(
                        f"Instant Answer: {abstract} (Source: {data.get('AbstractURL', '')})"
                    )

                # Collect related topics if available
                for topic in data.get("RelatedTopics", []):
                    if isinstance(topic, dict):
                        if topic.get("Text"):
                            results.append(f"- {topic['Text']} ({topic.get('FirstURL', '')})")
                        elif "Topics" in topic:
                            for subtopic in topic["Topics"][:2]:
                                if subtopic.get("Text"):
                                    results.append(f"- {subtopic['Text']} ({subtopic.get('FirstURL', '')})")
                    if len(results) >= 4:
                        break
    except Exception:
        pass

    # If the Instant Answer API returned solid answers, return them
    if results:
        return "\n".join(results[:5])

    # 2. Web search fallback via DuckDuckGo Lite (Free, no API key, reliable for local/dining searches)
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
            )
            if resp.status_code == 200:
                html_text = resp.text

                link_pattern = re.compile(
                    r"<a[^>]+class=[\"']result-link[\"'][^>]*href=[\"'](?P<url>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>",
                    re.DOTALL | re.IGNORECASE,
                )
                snippet_pattern = re.compile(
                    r"<td[^>]+class=[\"']result-snippet[\"'][^>]*>(?P<snippet>.*?)</td>",
                    re.DOTALL | re.IGNORECASE,
                )

                links = link_pattern.findall(html_text)
                snippets = snippet_pattern.findall(html_text)

                web_results = []
                for i in range(min(5, len(links))):
                    url, raw_title = links[i]
                    title = re.sub(r"<[^>]+>", "", raw_title).strip()
                    title = html.unescape(title)

                    snippet = ""
                    if i < len(snippets):
                        snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                        snippet = html.unescape(snippet)

                    web_results.append(f"[{i+1}] {title}\n    Details: {snippet}\n    Link: {url}")

                if web_results:
                    return "\n\n".join(web_results)
    except Exception as e:
        return f"Search error: {e}"

    return f"No results found on DuckDuckGo for query: '{query}'"


# Dispatch table: maps tool names from LLM to actual Python functions
TOOL_MAP = {
    "duckduckgo_search": duckduckgo_search,
}


# =============================================================================
# 2. TOOL SCHEMAS: The contract sent to the Groq LLM
# =============================================================================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "duckduckgo_search",
            "description": (
                "Search the web using DuckDuckGo. Use this to find places, restaurants, "
                "outdoor seating, patio dining, reviews, ratings, and recommendations near downtown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query. For local searches, be specific, e.g., "
                            "'restaurants downtown Seattle outdoor seating great reviews' or "
                            "'best patios downtown Austin reviews'"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    }
]


# =============================================================================
# 3. AGENT: State & The ReAct (Reason + Act) Loop
# =============================================================================

class SimpleAgent:
    """
    A minimal, framework-free AI Agent using Groq.
    """

    def __init__(self, client: Groq, model: str = "openai/gpt-oss-120b"):
        self.client = client
        self.model = model
        # Agent State / Working Memory: conversation history
        self.messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an expert local guide and dining concierge. "
                    "Your specialty is finding places near downtown areas that feature outdoor seating, "
                    "patio dining, and outstanding customer reviews. "
                    "Whenever the user asks for recommendations, use the duckduckgo_search tool to look up "
                    "real venues, check reviews, and verify outdoor seating amenities. "
                    "In your response, provide clear place names, outdoor seating highlights (e.g. heated patio, garden, rooftop), "
                    "what reviewers praise most, and why it fits their request."
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
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
                        observation = f"Error: Tool '{func_name}' does not exist."

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
    print("Downtown Places & Dining Concierge (Powered by Groq)")
    print(f"Model: {model}")
    print(f"Search Tool: duckduckgo_search (Free Instant Answer + Web Search)")
    print("=" * 60)
    print("Ask for recommendations with outdoor seating & great reviews, e.g.:")
    print("  - 'Find a place near downtown Chicago with outdoor seating and great reviews.'")
    print("  - 'What are top-rated brunch spots near downtown Austin with a patio?'")
    print("  - 'Find cozy cafes near downtown Seattle with outdoor tables.'")
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
