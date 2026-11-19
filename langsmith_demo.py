"""
=============================================================================
                  LANGSMITH OBSERVABILITY: HELLO WORLD DEMO
=============================================================================

This minimal script demonstrates how LangSmith traces pure Python agent code:
  1. Uses the `@traceable` decorator (no LangChain framework needed).
  2. Creates nested execution spans:
       [Parent Chain] -> [Tool Call] -> [LLM Call]
  3. Uploads the trace directly to your LangSmith Dashboard.

Run with: python langsmith_demo.py
=============================================================================
"""

import os
from dotenv import load_dotenv
from groq import Groq
from langsmith import traceable

# Load environment configuration (.env)
load_dotenv()


# =============================================================================
# 1. TRACED TOOL (run_type="tool")
# =============================================================================

@traceable(run_type="tool", name="lookup_weather")
def lookup_weather(city: str) -> str:
    """A simulated or real tool decorated for LangSmith tracing."""
    print(f"  -> [Tool] Fetching weather for {city}...")
    # Returns mock weather for instant demo
    return f"Weather in {city}: 15°C, Partly Cloudy, Humidity 62%"


# =============================================================================
# 2. TRACED LLM CALL (run_type="llm")
# =============================================================================

@traceable(run_type="llm", name="Groq LLM")
def call_llm(client: Groq, model: str, prompt: str) -> str:
    """Calls Groq LPU inference decorated for LangSmith tracing."""
    print(f"  -> [LLM] Calling Groq ({model})...")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


# =============================================================================
# 3. TRACED PARENT CHAIN (run_type="chain")
# =============================================================================

@traceable(run_type="chain", name="Simple Agent Workflow")
def run_agent_workflow(client: Groq, model: str, user_query: str) -> str:
    """
    Parent execution pipeline.
    LangSmith automatically nests all child @traceable calls under this parent!
    """
    print(f"\n[Workflow Started] Query: '{user_query}'")

    # Step 1: Call Tool (Child Span #1)
    weather_data = lookup_weather("Tokyo")

    # Step 2: Call LLM with Tool Output (Child Span #2)
    synthesis_prompt = (
        f"User asked: '{user_query}'.\n"
        f"Tool Result: '{weather_data}'.\n"
        f"Please provide a pleasant, 1-sentence answer to the user."
    )
    final_answer = call_llm(client, model, synthesis_prompt)

    print(f"[Workflow Finished] Output: {final_answer}\n")
    return final_answer


# =============================================================================
# 4. RUNNER & VERIFICATION
# =============================================================================

def main():
    print("=" * 68)
    print("LangSmith Tracing Demo (Pure Python + Groq)")
    print("=" * 68)

    langsmith_key = os.getenv("LANGSMITH_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    project = os.getenv("LANGSMITH_PROJECT", "agentic-arena")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Check LangSmith API key
    if not langsmith_key:
        print("\n⚠️  No LANGSMITH_API_KEY found in your .env file!")
        print("Please paste your LangSmith API key (starts with 'lsv2_pt_...'):")
        try:
            user_key = input("LangSmith Key > ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not user_key:
            print("Exiting. Add LANGSMITH_API_KEY to your .env to continue.")
            return
        os.environ["LANGSMITH_API_KEY"] = user_key
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = project

    if not groq_key:
        print("\n⚠️  No GROQ_API_KEY found in your .env file!")
        return

    client = Groq(api_key=groq_key)

    print(f"\nTracing enabled:")
    print(f"  • Project Name: '{project}'")
    print(f"  • Endpoint:     'https://api.smith.langchain.com'")
    print(f"  • Tracing:      ACTIVE (via @traceable)\n")

    # Execute the workflow
    result = run_agent_workflow(
        client=client,
        model=model,
        user_query="What is the weather in Tokyo?",
    )

    print("=" * 68)
    print("🎉 SUCCESS! Trace uploaded to LangSmith.")
    print("View your trace in your LangSmith dashboard:")
    print("👉 https://smith.langchain.com")
    print(f"   (Select Project: '{project}')")
    print("=" * 68)


if __name__ == "__main__":
    main()
