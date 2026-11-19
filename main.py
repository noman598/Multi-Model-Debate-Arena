"""
=============================================================================
             PRODUCTION AI AGENT CLI: WITH AUDIT & LOOP PROTECTION
=============================================================================

Interactive CLI for the production agent.
Run with: python main.py
=============================================================================
"""

import os
from dotenv import load_dotenv
from groq import Groq

from logger import log
from memory import SQLiteMemory
from tools import TOOL_MAP, TOOL_SCHEMAS
from agent import ReActAgent

# Load environment configuration
load_dotenv()


def print_banner(session_id: str, memory: SQLiteMemory, model: str):
    print("=" * 68)
    print("Production Agentic AI (Powered by Groq, SQLite & 4-Layer Loop Guard)")
    print(f"Model: {model}")
    print(f"Session: '{session_id}' | Audit Log: agent_audit.log | Database: agent_memory.db")
    print("=" * 68)

    summary = memory.get_summary(session_id)
    total_msgs = memory.get_total_count(session_id)

    if summary:
        print("\n[Memory] Resumed existing session from disk:")
        print(f"  • Total Messages in Database: {total_msgs}")
        print(f"  • Active Running Summary:\n    \"{summary}\"")
    elif total_msgs > 0:
        print(f"\n[Memory] Resumed existing session with {total_msgs} messages.")
    else:
        print("\n[Memory] Initialized fresh session.")

    print("\nSpecial Production Commands:")
    print("  'audit'   - View real-time telemetry (tool execution times, loop intercepts)")
    print("  'summary' - View active rolling compressed summary")
    print("  'history' - View raw SQLite conversation audit log")
    print("  'stats'   - View memory window bounds and message count")
    print("  'exit'    - Save and exit safely\n")


def display_audit_table(events):
    """Displays a clean tabular audit trail of recent operational events."""
    if not events:
        print("\n[Audit Log] No events recorded yet for this session.\n")
        return

    print("\n" + "=" * 80)
    print(f"{'ID':<4} | {'TIMESTAMP':<19} | {'EVENT TYPE':<22} | {'LATENCY':<9} | {'DETAILS'}")
    print("-" * 80)
    for e in events:
        latency = f"{e['duration_ms']:.1f}ms" if e['duration_ms'] > 0 else "-"
        details = e['details'][:35] + ("..." if len(e['details']) > 35 else "")
        print(f"{e['id']:<4} | {e['created_at']:<19} | {e['event_type']:<22} | {latency:<9} | {details}")
    print("=" * 80 + "\n")


def main():
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    if not api_key:
        print("=" * 68)
        print("No GROQ_API_KEY detected in .env!")
        print("Get your free API key at: https://console.groq.com/keys")
        print("=" * 68)
        try:
            api_key = input("\nEnter your Groq API key: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not api_key:
            return

    client = Groq(api_key=api_key)

    # Production SQLite Memory: sliding window threshold = 6, keeps latest 4 raw
    memory = SQLiteMemory(
        db_path="agent_memory.db",
        max_raw_window=6,
        keep_latest=4,
    )

    print("\nEnter a Session Name to resume or start fresh (Press Enter for 'default'):")
    try:
        session_input = input("Session ID > ").strip()
    except (KeyboardInterrupt, EOFError):
        return
    session_id = session_input if session_input else "default"

    # Instantiate production ReAct agent
    agent = ReActAgent(
        client=client,
        memory=memory,
        tools=TOOL_MAP,
        tool_schemas=TOOL_SCHEMAS,
        model=model,
    )

    print_banner(session_id, memory, model)

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            # Command: exit
            if user_input.lower() in ("exit", "quit"):
                log.info(f"User closed session '{session_id}'. State preserved in SQLite.")
                print("\nSession safely saved to SQLite database. Goodbye!")
                break

            # Command: audit telemetry viewer
            if user_input.lower() == "audit":
                events = memory.get_audit_events(session_id, limit=15)
                display_audit_table(events)
                continue

            # Command: summary viewer
            if user_input.lower() == "summary":
                cur_summary = memory.get_summary(session_id)
                print(f"\n[Active Running Summary for '{session_id}']:\n{cur_summary or 'No summary yet (conversation has not exceeded threshold).'}\n")
                continue

            # Command: raw message history viewer
            if user_input.lower() == "history":
                history = memory.get_raw_messages(session_id)
                print(f"\n[Raw SQLite History - {len(history)} messages]:")
                for m in history:
                    print(f"  [{m['role'].upper()}] (ID {m['id']}): {m['content'][:80]}...")
                print()
                continue

            # Command: stats
            if user_input.lower() == "stats":
                count = memory.get_total_count(session_id)
                has_sum = bool(memory.get_summary(session_id))
                print(f"\n[Memory Statistics]:")
                print(f"  • Total Raw Messages in DB: {count}")
                print(f"  • Max Raw Window Threshold: {memory.max_raw_window}")
                print(f"  • Verbatim Messages in Context: {min(count, memory.keep_latest)}")
                print(f"  • Compressed Summary Active: {has_sum}\n")
                continue

            # Execute agent turn
            answer = agent.run(session_id=session_id, user_prompt=user_input)
            print(f"\nAgent: {answer}\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession saved. Goodbye!")
            break
        except Exception as err:
            log.error(f"Turn execution error: {err}")
            print(f"\nError: {err}\n")


if __name__ == "__main__":
    main()
