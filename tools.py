"""
=============================================================================
                      TOOLS: REAL & ACTIONABLE REST APIS
=============================================================================

Production-grade tools implementing Layer 2 Loop Protection:
  - Every error, missing result, or edge-case returns explicit, ACTIONABLE guidance.
  - Instructs the LLM on what to do next so it never enters blind retry loops.
=============================================================================
"""

import urllib.parse
from typing import Any, Dict, List
import httpx

try:
    from langsmith import traceable
except ImportError:
    # Graceful fallback if langsmith is not installed
    def traceable(*args, **kwargs):
        def decorator(f):
            return f
        return decorator if kwargs or not args else decorator(args[0])


@traceable(run_type="tool", name="get_weather")
def get_weather(city: str) -> str:
    """
    Get live, real-time weather for any city using Open-Meteo.
    Completely free, no API key required, instant JSON response.
    """
    clean_city = city.strip()
    if not clean_city:
        return "Error: City name cannot be empty. Guidance: Ask the user to clarify which city they want weather for."

    try:
        with httpx.Client(timeout=8.0) as client:
            # Step 1: Geocoding
            geo_url = (
                f"https://geocoding-api.open-meteo.com/v1/search?"
                f"name={urllib.parse.quote(clean_city)}&count=1&language=en&format=json"
            )
            geo_resp = client.get(geo_url)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

            results = geo_data.get("results")
            if not results:
                # Layer 2 Actionable Return: Tell the model explicitly not to loop
                return (
                    f"Notice: No geographic coordinates found for '{clean_city}'. "
                    f"Guidance: The city name may be misspelled or unrecognized. "
                    f"Do NOT retry with the identical query '{clean_city}'. "
                    f"Please inform the user that the city was not found, or ask for clarification."
                )

            location = results[0]
            name = location.get("name", clean_city)
            country = location.get("country", "")
            lat = location.get("latitude")
            lon = location.get("longitude")

            # Step 2: Weather forecast
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

    except httpx.TimeoutException:
        return (
            f"Weather Service Timeout: The weather API took too long to respond for '{clean_city}'. "
            f"Guidance: Do not call this tool again right now. Inform the user of temporary network unavailability."
        )
    except Exception as err:
        return (
            f"Weather Service Notice: Unable to retrieve weather for '{clean_city}' ({err}). "
            f"Guidance: Do not retry with the same arguments. Synthesize an answer informing the user."
        )


@traceable(run_type="tool", name="get_wikipedia_summary")
def get_wikipedia_summary(topic: str) -> str:
    """
    Get a quick factual summary from Wikipedia about any topic, place, person, or landmark.
    Completely free, no API key required, official Wikipedia REST API.
    """
    clean_topic = topic.strip()
    if not clean_topic:
        return "Error: Topic cannot be blank. Guidance: Ask the user which topic or landmark they want to research."

    try:
        formatted_topic = urllib.parse.quote(clean_topic.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_topic}"
        headers = {"User-Agent": "AgentDemo/1.0 (educational-agent-bot)"}

        with httpx.Client(timeout=8.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 404:
                # Layer 2 Actionable Return: Tell the model not to retry the exact same query
                return (
                    f"Notice: No Wikipedia article found for '{clean_topic}'. "
                    f"Guidance: This exact title does not exist. Do NOT retry with the identical query '{clean_topic}'. "
                    f"You may try a broader, well-known keyword once, or conclude that no article exists."
                )
            resp.raise_for_status()
            data = resp.json()

            title = data.get("title", clean_topic)
            description = data.get("description", "")
            extract = data.get("extract", "")

            desc_line = f" ({description})" if description else ""
            return f"Wikipedia: {title}{desc_line}\n\n{extract}"

    except httpx.TimeoutException:
        return (
            f"Wikipedia Service Timeout: Request for '{clean_topic}' timed out. "
            f"Guidance: Do not retry immediately. Proceed with current knowledge."
        )
    except Exception as err:
        return (
            f"Wikipedia Service Notice: Could not fetch article for '{clean_topic}' ({err}). "
            f"Guidance: Do not retry with identical parameters. Conclude your search."
        )


@traceable(run_type="tool", name="calculate")
def calculate(expression: str) -> str:
    """
    Safely evaluate mathematical expressions or unit conversions.
    """
    clean_expr = expression.strip()
    try:
        allowed_chars = set("0123456789+-*/().,% ")
        if not all(char in allowed_chars for char in clean_expr):
            return (
                f"Error: Expression '{clean_expr}' contains unsupported symbols. "
                f"Guidance: Use only standard mathematical characters (+, -, *, /, %). Do not retry the exact same expression."
            )

        result = eval(clean_expr, {"__builtins__": None}, {})
        return f"{clean_expr} = {result}"

    except Exception as err:
        return (
            f"Calculation Error in '{clean_expr}': {err}. "
            f"Guidance: Verify arithmetic syntax. Do not repeat the same calculation."
        )


@traceable(run_type="tool", name="execute_refund")
def execute_refund(order_id: str, amount: float, reason: str) -> str:
    """
    Execute a financial refund for a customer order.
    CRITICAL: This tool performs real financial debits and ledger updates.
    It requires explicit Human-in-the-Loop (HITL) supervisor approval before running.
    """
    clean_order = order_id.strip().upper()
    try:
        amt = float(amount)
    except (ValueError, TypeError):
        return f"Error: Invalid amount '{amount}'. Guidance: Amount must be a positive numeric value."

    if amt <= 0:
        return f"Error: Refund amount ${amt:.2f} must be greater than $0.00. Guidance: Ask the user for the valid refund amount."

    if not clean_order:
        return "Error: Order ID cannot be empty. Guidance: Ask the user for the Order ID (e.g., ORD-12345)."

    # Deterministic simulation of order refund processing
    txn_ref = f"REF-{abs(hash(clean_order + str(amt))) % 1000000:06d}"
    return (
        f"SUCCESS [Refund Processed]:\n"
        f"- Order ID: {clean_order}\n"
        f"- Refund Amount: ${amt:.2f}\n"
        f"- Reason: {reason.strip()}\n"
        f"- Transaction Reference: {txn_ref}\n"
        f"- Status: Settled. Customer ledger credited."
    )


# =============================================================================
# TOOL REGISTRY & HUMAN-IN-THE-LOOP (HITL) CLASSIFICATION
# =============================================================================

# Tools classified by operational risk. Tools with requires_approval=True
# can NEVER be executed autonomously by the agent without human sign-off.
CRITICAL_TOOLS: Dict[str, Dict[str, Any]] = {
    "execute_refund": {
        "risk_level": "HIGH",
        "requires_approval": True,
        "description": "Financial operation: transfers or refunds money to a customer order.",
    }
}

TOOL_MAP: Dict[str, Any] = {
    "get_weather": get_weather,
    "get_wikipedia_summary": get_wikipedia_summary,
    "calculate": calculate,
    "execute_refund": execute_refund,
}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current real-time live weather for any city worldwide (temperature, humidity, wind).",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'Chicago', 'Tokyo', 'London', 'Paris'.",
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
                        "description": "The landmark, place, person, or concept to search for.",
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
            "description": "Evaluate mathematical expressions or conversions (e.g. Celsius to Fahrenheit, percentages, splits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression, e.g. '18.5 * 9/5 + 32' or '120 * 0.18'.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_refund",
            "description": "Process a financial refund for a customer order. HIGH-RISK ACTION: requires human supervisor approval before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The unique customer order identifier (e.g. 'ORD-94821').",
                    },
                    "amount": {
                        "type": "number",
                        "description": "The total amount in dollars to refund (e.g. 89.99).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "The customer's reason for requesting the refund.",
                    },
                },
                "required": ["order_id", "amount", "reason"],
            },
        },
    },
]
