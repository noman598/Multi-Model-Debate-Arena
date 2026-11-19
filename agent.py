"""
=============================================================================
             AGENT: PRODUCTION ReAct ENGINE WITH 4-LAYER LOOP PROTECTION
=============================================================================

This module houses the core AI Agent.
Production-ready features implemented:
  - Layer 1 Loop Protection: Code-level duplicate call interceptor (hash matching).
  - Layer 3 Loop Protection: Explicit exit & stopping constraints in system prompt.
  - Layer 4 Loop Protection: Hard safety floor (`max_steps` + `tool_choice="none"` fallback).
  - Telemetry & Auditing: Tool execution timing (ms) and event logging to SQLite & audit log.
=============================================================================
"""

import json
import time
from typing import Any, Dict, List, Optional, Set
from groq import Groq, BadRequestError
from memory import SQLiteMemory
from logger import log

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(f):
            return f
        return decorator if kwargs or not args else decorator(args[0])


@traceable(run_type="llm", name="Groq LLM")
def call_groq_llm(client: Groq, **kwargs):
    """Traced helper for Groq chat completions."""
    return client.chat.completions.create(**kwargs)


class ReActAgent:
    """
    A production ReAct Agent with 4-layer infinite loop protection,
    persistent SQLite memory, and operational audit telemetry.
    """

    def __init__(
        self,
        client: Groq,
        memory: SQLiteMemory,
        tools: Dict[str, Any],
        tool_schemas: List[Dict[str, Any]],
        model: str = "openai/gpt-oss-120b",
        system_prompt: Optional[str] = None,
    ):
        self.client = client
        self.memory = memory
        self.tools = tools
        self.tool_schemas = tool_schemas
        self.model = model
        self.last_run_stats: Dict[str, Any] = {}
        # Layer 3: System Prompt Exit Conditions and Anti-Loop Constraints
        self.system_prompt = system_prompt or (
            "You are a helpful, precise AI Assistant with persistent memory.\n"
            "You have access to real tools:\n"
            "- `get_weather(city)`: Live global weather data.\n"
            "- `get_wikipedia_summary(topic)`: Factual overviews on landmarks, places, and history.\n"
            "- `calculate(expression)`: Accurate math and unit conversions.\n\n"
            "Critical Operating Rules:\n"
            "1. NEVER call the same tool repeatedly with the exact same arguments.\n"
            "2. If a tool returns 'Notice' or 'No results found', do not retry blindly. "
            "Explain the situation to the user or try a different approach.\n"
            "3. Once you have gathered sufficient information, synthesize your final response immediately."
        )

    @traceable(run_type="chain", name="ReAct Agent Turn")
    def run(self, session_id: str, user_prompt: str, max_steps: int = 5) -> str:
        """
        Executes the ReAct loop for a user query with full 4-layer loop protection.
        """
        turn_start_time = time.perf_counter()

        # Step 1: Persist user prompt to SQLite
        self.memory.save_message(session_id, "user", user_prompt)

        # Step 2: Auto-compress older turns if threshold exceeded
        self.memory.compress_if_needed(session_id, self.client, self.model)

        # Step 3: Build working context ([System] + [Summary] + [Latest N turns])
        working_messages = self.memory.build_working_context(session_id, self.system_prompt)

        # Layer 1: Tracking executed tool signatures to intercept duplicate calls
        # Signature format: "tool_name:sorted_json_args"
        executed_call_signatures: Set[str] = set()
        duplicate_intercepts: int = 0
        tools_called: List[str] = []

        step = 0
        while step < max_steps:
            step += 1
            log.info(f"Agent Step {step}/{max_steps}: Reasoning with Groq ({len(working_messages)} context items)...")

            create_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": working_messages,
            }
            if self.tool_schemas:
                create_kwargs["tools"] = self.tool_schemas
                create_kwargs["tool_choice"] = "auto"

            try:
                response = call_groq_llm(self.client, **create_kwargs)
            except BadRequestError as err:
                log.warning(f"Groq API Bad Request ({err.message}). Attempting fallback without tools...")
                try:
                    fallback_response = call_groq_llm(
                        self.client,
                        model=self.model,
                        messages=working_messages + [{
                            "role": "user",
                            "content": "Please answer directly based on context. Do not call any tools."
                        }],
                    )
                    final_answer = fallback_response.choices[0].message.content or ""
                    self.memory.save_message(session_id, "assistant", final_answer)
                    return final_answer
                except Exception as inner_err:
                    log.error(f"Fallback generation failed: {inner_err}")
                    return f"Agent stopped due to API error: {inner_err}"

            response_msg = response.choices[0].message
            tool_calls = response_msg.tool_calls

            # Case A: Model requested tool execution
            if tool_calls:
                working_messages.append(response_msg.model_dump(exclude_none=True))

                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args_str = tool_call.function.arguments

                    try:
                        func_args = json.loads(func_args_str) if func_args_str else {}
                    except json.JSONDecodeError:
                        func_args = {}

                    tools_called.append(func_name)

                    # =========================================================
                    # LAYER 1: CODE-LEVEL DUPLICATE INTERCEPTOR (LOOP BREAKER)
                    # =========================================================
                    normalized_args = json.dumps(func_args, sort_keys=True)
                    call_signature = f"{func_name}:{normalized_args}"

                    if call_signature in executed_call_signatures:
                        # INTERCEPT: Tool call is an exact duplicate!
                        duplicate_intercepts += 1
                        log.warning(f"Loop Protection: Duplicate call intercepted -> {func_name}({func_args})")
                        observation = (
                            f"SYSTEM WARNING [Duplicate Call Intercepted]: You have already executed '{func_name}' "
                            f"with arguments {normalized_args} in this session and received the result above. "
                            f"DO NOT call this tool again with identical parameters. "
                            f"Either adjust your search parameters or synthesize your final response from available data."
                        )
                        self.memory.save_audit_event(
                            session_id=session_id,
                            event_type="DUPLICATE_INTERCEPTED",
                            details=f"Intercepted duplicate {func_name}({normalized_args})",
                        )

                    else:
                        # First time seeing this call signature -> Execute normally
                        executed_call_signatures.add(call_signature)
                        log.info(f"Executing Tool: {func_name}({func_args})")

                        start_t = time.perf_counter()
                        if func_name in self.tools:
                            try:
                                observation = str(self.tools[func_name](**func_args))
                            except Exception as err:
                                observation = f"Error executing {func_name}: {err}. Guidance: Do not repeat identical call."
                        else:
                            observation = f"Error: Tool '{func_name}' does not exist. Available tools: {list(self.tools.keys())}"

                        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

                        # Audit logging
                        self.memory.save_audit_event(
                            session_id=session_id,
                            event_type="TOOL_EXECUTED",
                            details=f"{func_name}({normalized_args})",
                            duration_ms=round(elapsed_ms, 2),
                        )
                        log.info(f"Tool completed in {elapsed_ms:.1f}ms: {func_name}")

                    # Feed observation back to conversation context
                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": observation,
                    })

                continue  # Loop back to reason over observations

            # Case B: Model returned a direct text response (Finished)
            else:
                final_answer = response_msg.content or ""
                self.memory.save_message(session_id, "assistant", final_answer)

                total_turn_ms = (time.perf_counter() - turn_start_time) * 1000.0
                self.last_run_stats = {
                    "steps": step,
                    "tools_called": list(tools_called),
                    "duplicates_intercepted": duplicate_intercepts,
                    "duration_ms": round(total_turn_ms, 2),
                    "max_steps_exceeded": False,
                }
                self.memory.save_audit_event(
                    session_id=session_id,
                    event_type="TURN_COMPLETED",
                    details=f"Steps: {step}, Duplicates Intercepted: {duplicate_intercepts}",
                    duration_ms=round(total_turn_ms, 2),
                )
                return final_answer

        # =====================================================================
        # LAYER 4: HARD SAFETY FLOOR & FALLBACK (tool_choice="none")
        # =====================================================================
        log.warning(f"Safety Floor Triggered: Agent reached max steps ({max_steps}). Forcing final answer...")
        self.memory.save_audit_event(
            session_id=session_id,
            event_type="MAX_STEPS_REACHED",
            details=f"Exhausted {max_steps} steps. Forcing text synthesis with tool_choice='none'.",
        )

        try:
            forced_response = call_groq_llm(
                self.client,
                model=self.model,
                messages=working_messages + [{
                    "role": "user",
                    "content": (
                        "You have reached the maximum allowed tool execution steps. "
                        "Please synthesize your best final response now based on all observations above. "
                        "Do not call any tools."
                    ),
                }],
                tool_choice="none",  # Strictly forbids calling any further tools
            )
            final_answer = forced_response.choices[0].message.content or "Reached maximum reasoning steps."
            self.memory.save_message(session_id, "assistant", final_answer)
            self.last_run_stats = {
                "steps": max_steps,
                "tools_called": list(tools_called),
                "duplicates_intercepted": duplicate_intercepts,
                "duration_ms": round((time.perf_counter() - turn_start_time) * 1000.0, 2),
                "max_steps_exceeded": True,
            }
            return final_answer
        except Exception as err:
            self.last_run_stats = {
                "steps": max_steps,
                "tools_called": list(tools_called),
                "duplicates_intercepted": duplicate_intercepts,
                "duration_ms": round((time.perf_counter() - turn_start_time) * 1000.0, 2),
                "max_steps_exceeded": True,
                "error": str(err),
            }
            return f"Agent stopped after {max_steps} steps: {err}"
