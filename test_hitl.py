"""
=============================================================================
         UNIT & INTEGRATION TESTS: HUMAN-IN-THE-LOOP (HITL) WORKFLOW
=============================================================================
Tests both approval and rejection branches of critical tools, ensuring:
  1. High-risk actions (e.g. execute_refund) trigger approval callbacks.
  2. If APPROVED: tool executes, ledger is updated, audit events logged.
  3. If REJECTED: tool is blocked, NO execution occurs, agent explains why.
  4. Non-critical tools (calculate, weather) run autonomously without prompt.
  5. Deterministic offline tests run inside sandbox without network dependency.
=============================================================================
"""

import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

from memory import SQLiteMemory
from tools import TOOL_MAP, TOOL_SCHEMAS, CRITICAL_TOOLS, execute_refund
from agent import ReActAgent

load_dotenv()


def test_hitl_critical_tools_registry():
    """Verify tool classification and risk levels."""
    assert "execute_refund" in CRITICAL_TOOLS
    assert CRITICAL_TOOLS["execute_refund"]["requires_approval"] is True
    assert "get_weather" not in CRITICAL_TOOLS
    assert "calculate" not in CRITICAL_TOOLS


def test_execute_refund_tool_direct():
    """Verify tool output formatting and validation."""
    # Valid call
    res = execute_refund(order_id="ORD-9988", amount=75.50, reason="Damaged box")
    assert "SUCCESS [Refund Processed]" in res
    assert "ORD-9988" in res
    assert "$75.50" in res

    # Invalid amount
    res_err = execute_refund(order_id="ORD-9988", amount=-10, reason="Test")
    assert "Error:" in res_err


def create_mock_completion(content=None, tool_name=None, tool_args=None, tool_call_id="call_mock_1"):
    """Helper to generate mock LLM responses for offline deterministic testing."""
    if tool_name:
        tool_call = SimpleNamespace(
            id=tool_call_id,
            function=SimpleNamespace(
                name=tool_name,
                arguments=tool_args if isinstance(tool_args, str) else str(tool_args).replace("'", '"')
            )
        )
        msg = SimpleNamespace(
            content=None,
            tool_calls=[tool_call],
            model_dump=lambda exclude_none=True: {
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_args if isinstance(tool_args, str) else str(tool_args).replace("'", '"')
                    }
                }]
            }
        )
    else:
        msg = SimpleNamespace(
            content=content,
            tool_calls=None,
            model_dump=lambda exclude_none=True: {
                "role": "assistant",
                "content": content
            }
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_hitl_approval_flow_offline():
    """Offline test: Agent proposes refund -> Supervisor APPROVES -> Tool runs."""
    test_db = "test_hitl_approve.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    memory = SQLiteMemory(db_path=test_db)
    mock_client = MagicMock()

    approval_calls = []

    def mock_supervisor_approves(session_id, tool_name, tool_args):
        approval_calls.append((tool_name, tool_args))
        return True, None

    agent = ReActAgent(
        client=mock_client,
        memory=memory,
        tools=TOOL_MAP,
        tool_schemas=TOOL_SCHEMAS,
        approval_handler=mock_supervisor_approves,
    )

    # Step 1: Model calls execute_refund
    comp1 = create_mock_completion(
        tool_name="execute_refund",
        tool_args='{"order_id": "ORD-1234", "amount": 45.0, "reason": "Size too small"}'
    )
    # Step 2: Model outputs final answer after receiving tool execution result
    comp2 = create_mock_completion(content="Your refund of $45.00 for order ORD-1234 has been processed.")

    session_id = "test_hitl_approve"
    prompt = "Please refund $45.00 for order ORD-1234."

    with patch("agent.call_groq_llm", side_effect=[comp1, comp2]):
        answer = agent.run(session_id=session_id, user_prompt=prompt)

    # 1. Assert supervisor was prompted for approval
    assert len(approval_calls) == 1
    tool_name, tool_args = approval_calls[0]
    assert tool_name == "execute_refund"
    assert tool_args["order_id"] == "ORD-1234"
    assert tool_args["amount"] == 45.0

    # 2. Assert SQLite audit trail has APPROVAL_REQUESTED, APPROVAL_GRANTED, and TOOL_EXECUTED
    events = memory.get_audit_events(session_id)
    event_types = [e["event_type"] for e in events]
    assert "APPROVAL_REQUESTED" in event_types
    assert "APPROVAL_GRANTED" in event_types
    assert "TOOL_EXECUTED" in event_types
    assert "APPROVAL_REJECTED" not in event_types

    # 3. Assert final answer
    assert "refund of $45.00" in answer

    # Cleanup
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


def test_hitl_rejection_flow_offline():
    """Offline test: Agent proposes refund -> Supervisor REJECTS -> Tool NOT run."""
    test_db = "test_hitl_reject.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    memory = SQLiteMemory(db_path=test_db)
    mock_client = MagicMock()

    approval_calls = []

    def mock_supervisor_rejects(session_id, tool_name, tool_args):
        approval_calls.append((tool_name, tool_args))
        return False, "Order exceeds 30-day return window."

    agent = ReActAgent(
        client=mock_client,
        memory=memory,
        tools=TOOL_MAP,
        tool_schemas=TOOL_SCHEMAS,
        approval_handler=mock_supervisor_rejects,
    )

    # Step 1: Model calls execute_refund
    comp1 = create_mock_completion(
        tool_name="execute_refund",
        tool_args='{"order_id": "ORD-7788", "amount": 120.0, "reason": "Late package"}'
    )
    # Step 2: Model responds after seeing the supervisor rejection observation
    comp2 = create_mock_completion(
        content="I apologize, but the supervisor rejected the refund: Order exceeds 30-day return window."
    )

    session_id = "test_hitl_reject"
    prompt = "I need a refund of $120.00 for order ORD-7788."

    with patch("agent.call_groq_llm", side_effect=[comp1, comp2]):
        answer = agent.run(session_id=session_id, user_prompt=prompt)

    # 1. Assert supervisor was prompted
    assert len(approval_calls) == 1
    tool_name, tool_args = approval_calls[0]
    assert tool_name == "execute_refund"

    # 2. Check audit trail: APPROVAL_REJECTED present, TOOL_EXECUTED strictly absent!
    events = memory.get_audit_events(session_id)
    event_types = [e["event_type"] for e in events]
    assert "APPROVAL_REQUESTED" in event_types
    assert "APPROVAL_REJECTED" in event_types
    assert "APPROVAL_GRANTED" not in event_types

    # Critical verify: Tool was NEVER executed
    tool_execs = [e for e in events if e["event_type"] == "TOOL_EXECUTED" and "execute_refund" in e["details"]]
    assert len(tool_execs) == 0

    # 3. Agent response communicates the rejection
    assert "supervisor rejected" in answer.lower()

    # Cleanup
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


def test_autonomous_tool_does_not_prompt_hitl():
    """Ensure safe tools (e.g. calculate) run autonomously without supervisor prompt."""
    test_db = "test_hitl_auto.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    memory = SQLiteMemory(db_path=test_db)
    mock_client = MagicMock()

    approval_calls = []

    def mock_handler(session_id, tool_name, tool_args):
        approval_calls.append((tool_name, tool_args))
        return True, None

    agent = ReActAgent(
        client=mock_client,
        memory=memory,
        tools=TOOL_MAP,
        tool_schemas=TOOL_SCHEMAS,
        approval_handler=mock_handler,
    )

    # Step 1: Model calls calculate
    comp1 = create_mock_completion(
        tool_name="calculate",
        tool_args='{"expression": "45 * 2"}'
    )
    # Step 2: Model finishes
    comp2 = create_mock_completion(content="45 * 2 = 90")

    session_id = "test_hitl_auto"
    prompt = "What is 45 * 2?"

    with patch("agent.call_groq_llm", side_effect=[comp1, comp2]):
        answer = agent.run(session_id=session_id, user_prompt=prompt)

    # 1. Assert supervisor was NEVER prompted for safe tool
    assert len(approval_calls) == 0

    # 2. Check audit trail
    events = memory.get_audit_events(session_id)
    event_types = [e["event_type"] for e in events]
    assert "APPROVAL_REQUESTED" not in event_types
    assert "TOOL_EXECUTED" in event_types
    assert "90" in answer

    # Cleanup
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


if __name__ == "__main__":
    print("1. Testing HITL Tool Classification...")
    test_hitl_critical_tools_registry()
    print("   ✓ Registry & risk classifications verified.")

    print("\n2. Testing execute_refund tool directly...")
    test_execute_refund_tool_direct()
    print("   ✓ Direct execution and validation verified.")

    print("\n3. Testing Approval Flow (Agent -> Supervisor Approves -> Tool Runs)...")
    test_hitl_approval_flow_offline()
    print("   ✓ Approval flow verified: APPROVAL_GRANTED logged, tool executed.")

    print("\n4. Testing Rejection Flow (Agent -> Supervisor Rejects -> Tool Blocked)...")
    test_hitl_rejection_flow_offline()
    print("   ✓ Rejection flow verified: APPROVAL_REJECTED logged, tool NEVER executed.")

    print("\n5. Testing Autonomous Flow (Safe tools run without supervisor prompt)...")
    test_autonomous_tool_does_not_prompt_hitl()
    print("   ✓ Autonomous execution verified: calculate ran with zero interruption.")

    print("\n=======================================================")
    print("🎉 ALL 5 HUMAN-IN-THE-LOOP (HITL) TESTS PASSED SAFELY!")
    print("=======================================================")
