"""
=============================================================================
           AGENTIC AI EVALUATION SUITE (EVALS.PY)
=============================================================================

Automated Evaluation Runner covering the 5 critical production dimensions:
  1. Final Answer Correctness  (Factual accuracy / keyword grounding)
  2. Correct Tool Selection     (Correct tool picked vs zero tools for chat)
  3. Correct Agent Trajectory   (Step efficiency, stops within target steps)
  4. Latency / Speed            (Execution duration under benchmark threshold)
  5. Safety & Reliability       (Zero duplicate loops, safe error handling)

Run with: python evals.py
=============================================================================
"""

import os
import time
from typing import Any, Dict, List
from dotenv import load_dotenv
from groq import Groq

from memory import SQLiteMemory
from tools import TOOL_MAP, TOOL_SCHEMAS
from agent import ReActAgent

try:
    from langsmith import traceable
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(f):
            return f
        return decorator if kwargs or not args else decorator(args[0])

# Load environment variables (.env)
load_dotenv()


# =============================================================================
# 1. THE 10 SAMPLE TEST CASES
# =============================================================================

TEST_CASES: List[Dict[str, Any]] = [
    {
        "id": "TC-01",
        "category": "Weather (Tokyo)",
        "prompt": "What is the current weather in Tokyo?",
        "expected_tool": "get_weather",
        "expected_keywords": ["tokyo", "temperature"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-02",
        "category": "Weather (London)",
        "prompt": "Check the live weather in London right now.",
        "expected_tool": "get_weather",
        "expected_keywords": ["london"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-03",
        "category": "Wikipedia (Eiffel Tower)",
        "prompt": "Who designed the Eiffel Tower in Paris?",
        "expected_tool": "get_wikipedia_summary",
        "expected_keywords": ["eiffel"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-04",
        "category": "Wikipedia (Roman Empire)",
        "prompt": "Give me a brief factual summary of the Roman Empire.",
        "expected_tool": "get_wikipedia_summary",
        "expected_keywords": ["rome", "roman"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-05",
        "category": "Math (Division)",
        "prompt": "Calculate 450 divided by 6.",
        "expected_tool": "calculate",
        "expected_keywords": ["75"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-06",
        "category": "Math (Tip Percentage)",
        "prompt": "What is an 18% tip on a 150 dollar bill? Calculate it.",
        "expected_tool": "calculate",
        "expected_keywords": ["27"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-07",
        "category": "Chit-Chat (Zero Tools)",
        "prompt": "Hello there! How are you doing today?",
        "expected_tool": None,  # Must NOT call any tools!
        "expected_keywords": [],
        "max_steps": 1,
        "max_latency_ms": 5000,
    },
    {
        "id": "TC-08",
        "category": "Creative (Zero Tools)",
        "prompt": "Write a quick two-line rhyme about writing clean code.",
        "expected_tool": None,  # Must NOT call any tools!
        "expected_keywords": [],
        "max_steps": 1,
        "max_latency_ms": 5000,
    },
    {
        "id": "TC-09",
        "category": "Safety (Missing City)",
        "prompt": "What is the weather in ZzzzzCity999NotRealPlace?",
        "expected_tool": "get_weather",
        "expected_keywords": ["not found", "unrecognized", "misspelled", "sorry", "cannot", "unable"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
    {
        "id": "TC-10",
        "category": "Safety (Invalid Math)",
        "prompt": "Calculate this math: 50 +++-- invalid*",
        "expected_tool": "calculate",
        "expected_keywords": ["error", "invalid", "unsupported", "syntax", "cannot"],
        "max_steps": 2,
        "max_latency_ms": 6500,
    },
]


# =============================================================================
# 2. EVALUATION HARNESS
# =============================================================================

@traceable(name="Evaluate Single Case", run_type="chain")
def evaluate_test_case(agent: ReActAgent, tc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs a single test case through the agent and evaluates all 5 dimensions.
    """
    test_id = tc["id"]
    prompt = tc["prompt"]
    session_id = f"eval_{test_id}_{int(time.time())}"

    # Execute Agent
    try:
        final_answer = agent.run(session_id=session_id, user_prompt=prompt, max_steps=tc["max_steps"])
        stats = agent.last_run_stats
        run_error = None
    except Exception as err:
        final_answer = ""
        stats = {"steps": 0, "tools_called": [], "duplicates_intercepted": 0, "duration_ms": 0, "max_steps_exceeded": True}
        run_error = str(err)

    # ---------------------------------------------------------
    # Metric 1: Final Answer Correctness
    # ---------------------------------------------------------
    lower_ans = final_answer.lower()
    if tc["expected_keywords"]:
        # At least one required keyword must appear
        keyword_match = any(kw.lower() in lower_ans for kw in tc["expected_keywords"])
    else:
        # Non-empty meaningful response
        keyword_match = len(final_answer.strip()) > 5
    m1_correctness = keyword_match and bool(final_answer)

    # ---------------------------------------------------------
    # Metric 2: Correct Tool Selection
    # ---------------------------------------------------------
    tools_called = stats.get("tools_called", [])
    if tc["expected_tool"] is None:
        m2_tool_selection = (len(tools_called) == 0)
    else:
        m2_tool_selection = (tc["expected_tool"] in tools_called)

    # ---------------------------------------------------------
    # Metric 3: Correct Agent Trajectory
    # ---------------------------------------------------------
    steps = stats.get("steps", 0)
    max_exceeded = stats.get("max_steps_exceeded", False)
    m3_trajectory = (steps <= tc["max_steps"]) and (not max_exceeded)

    # ---------------------------------------------------------
    # Metric 4: Latency / Speed
    # ---------------------------------------------------------
    duration_ms = stats.get("duration_ms", 0.0)
    m4_latency = (duration_ms <= tc["max_latency_ms"]) and (duration_ms > 0)

    # ---------------------------------------------------------
    # Metric 5: Safety & Reliability
    # ---------------------------------------------------------
    dups = stats.get("duplicates_intercepted", 0)
    m5_safety = (dups == 0) and (run_error is None)

    # Overall Status: All 5 must PASS
    overall_pass = all([m1_correctness, m2_tool_selection, m3_trajectory, m4_latency, m5_safety])

    return {
        "id": test_id,
        "category": tc["category"],
        "prompt": prompt,
        "final_answer": final_answer,
        "tools_called": tools_called,
        "steps": steps,
        "duration_ms": duration_ms,
        "m1_correctness": m1_correctness,
        "m2_tool_selection": m2_tool_selection,
        "m3_trajectory": m3_trajectory,
        "m4_latency": m4_latency,
        "m5_safety": m5_safety,
        "overall_pass": overall_pass,
        "error": run_error,
    }


# =============================================================================
# 3. SCORECARD FORMATTER & RUNNER
# =============================================================================

@traceable(name="Agent Evaluation Suite", run_type="chain")
def run_evaluation_suite():
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    if not api_key:
        print("Error: No GROQ_API_KEY detected in .env!")
        return

    client = Groq(api_key=api_key)

    # Use a dedicated evaluation database
    eval_db = "eval_agent_memory.db"
    memory = SQLiteMemory(db_path=eval_db, max_raw_window=6, keep_latest=4)

    agent = ReActAgent(
        client=client,
        memory=memory,
        tools=TOOL_MAP,
        tool_schemas=TOOL_SCHEMAS,
        model=model,
    )

    print("=" * 82)
    print("           AGENTIC AI EVALUATION SUITE (10 BENCHMARK TESTS)")
    print(f"Model Under Test: {model}")
    print(f"Metrics: 1.Answer 2.Tool 3.Trajectory 4.Latency 5.Safety")
    print("=" * 82)

    results = []
    start_all = time.perf_counter()

    for idx, tc in enumerate(TEST_CASES, start=1):
        print(f"[{idx}/10] Running {tc['id']}: {tc['category']}...", end="", flush=True)
        res = evaluate_test_case(agent, tc)
        status = "PASSED" if res["overall_pass"] else "FAILED"
        print(f" -> {status} ({res['duration_ms']:.0f}ms)")
        results.append(res)

    total_time = time.perf_counter() - start_all

    # ---------------------------------------------------------
    # PRINT RESULTS SCORECARD TABLE
    # ---------------------------------------------------------
    print("\n" + "=" * 82)
    print(f"{'ID':<6} | {'CATEGORY':<24} | {'CORRECT':<7} | {'TOOL':<5} | {'TRAJ':<5} | {'SPEED':<7} | {'SAFE':<5} | {'OVERALL'}")
    print("-" * 82)

    passed_count = 0
    tool_acc_count = 0
    correct_count = 0
    traj_count = 0
    safe_count = 0
    lat_count = 0
    total_latency = 0.0

    for r in results:
        p_c = "PASS" if r["m1_correctness"] else "FAIL"
        p_t = "PASS" if r["m2_tool_selection"] else "FAIL"
        p_tr = "PASS" if r["m3_trajectory"] else "FAIL"
        p_l = "PASS" if r["m4_latency"] else "FAIL"
        p_s = "PASS" if r["m5_safety"] else "FAIL"
        p_all = "✔ PASS" if r["overall_pass"] else "✘ FAIL"

        if r["overall_pass"]:
            passed_count += 1
        if r["m1_correctness"]:
            correct_count += 1
        if r["m2_tool_selection"]:
            tool_acc_count += 1
        if r["m3_trajectory"]:
            traj_count += 1
        if r["m4_latency"]:
            lat_count += 1
        if r["m5_safety"]:
            safe_count += 1

        total_latency += r["duration_ms"]

        print(f"{r['id']:<6} | {r['category']:<24} | {p_c:<7} | {p_t:<5} | {p_tr:<5} | {p_l:<7} | {p_s:<5} | {p_all}")

    print("=" * 82)

    # ---------------------------------------------------------
    # AGGREGATE SUMMARY
    # ---------------------------------------------------------
    avg_latency = total_latency / len(results) if results else 0
    print("\n📊 AGGREGATE EVALUATION REPORT:")
    print(f"  • Overall Benchmark Pass Rate : {passed_count}/{len(results)} ({passed_count/len(results)*100:.1f}%)")
    print(f"  • Answer Correctness Rate     : {correct_count}/{len(results)} ({correct_count/len(results)*100:.1f}%)")
    print(f"  • Tool Selection Accuracy     : {tool_acc_count}/{len(results)} ({tool_acc_count/len(results)*100:.1f}%)")
    print(f"  • Trajectory Efficiency Rate  : {traj_count}/{len(results)} ({traj_count/len(results)*100:.1f}%)")
    print(f"  • Latency Compliance Rate     : {lat_count}/{len(results)} ({lat_count/len(results)*100:.1f}%) [Avg: {avg_latency:.0f}ms]")
    print(f"  • Safety & Reliability Score  : {safe_count}/{len(results)} ({safe_count/len(results)*100:.1f}%)")
    print(f"  • Total Suite Execution Time  : {total_time:.2f}s")
    print("=" * 82 + "\n")

    # Clean up evaluation temp database
    try:
        if os.path.exists(eval_db):
            os.remove(eval_db)
    except Exception:
        pass


if __name__ == "__main__":
    run_evaluation_suite()
