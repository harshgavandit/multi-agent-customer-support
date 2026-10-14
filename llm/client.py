"""Thin wrapper around LiteLLM — the *only* place in the codebase that calls
`litellm.completion(...)`.

Concept: every model call in this POC (both the Info-Gathering node and the
Context Compaction node) goes through `complete_json`, and the model name
comes from config.py, not a string literal buried in a node. If you ever
swap providers (OpenAI -> Anthropic -> a local model via Ollama), this is
the one function whose behavior you're relying on, and config.py is the one
line you'd change.

No retries, no fallback models, no streaming — this is a POC, and adding
that machinery here would obscure the teaching point rather than help it.
"""
import json
import os

from config import LLM_MODEL, LLM_TIMEOUT_SECONDS

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
import litellm

litellm.suppress_debug_info = True
from errors import ModelUnavailable
from rate_limit import check_model_call


def complete_json(system_prompt: str, user_content: str, temperature: float = 0.0) -> dict:
    """Call the LLM and parse its reply as a JSON object.

    Both the info-gathering and compaction nodes ask the model to respond
    with *only* a JSON object (no prose, no markdown fences) — this helper
    is what turns that raw string back into a Python dict.
    """
    check_model_call()
    try:
        response = litellm.completion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=LLM_TIMEOUT_SECONDS,
            num_retries=0,
            max_retries=0,
        )
    except litellm.AuthenticationError:
        raise ModelUnavailable("The model provider rejected the API credentials. Check the API key in .env.") from None
    except litellm.RateLimitError:
        raise ModelUnavailable("The model provider's quota or rate limit was reached. Check the provider account and try again later.") from None
    except Exception:
        raise ModelUnavailable("The model request failed. Check model access, connectivity and configuration, then try again.") from None
    try:
        raw = response.choices[0].message.content
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError, IndexError):
        raise ModelUnavailable("The model returned an invalid JSON object. Please try again.") from None
