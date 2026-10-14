"""Validated, project-relative configuration; credentials stay in .env."""
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# Loads OPENAI_API_KEY (and anything else) from a local .env file at import
# time. The key itself is never read directly by our code — litellm picks it
# up from the environment when litellm.completion() is called.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if value <= 0:
            raise ValueError
        return value
    except ValueError:
        raise ValueError(f"{name} must be a positive integer.") from None


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true or false.")
    return value in {"true", "1"}

# LiteLLM model identifier, e.g. "gpt-4o-mini", "gpt-4o", "claude-sonnet-5".
# See https://docs.litellm.ai/docs/providers for the full naming scheme.
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()

# Path to the embedded SQLite database backing the mocked tools (see db/).
_db_path = Path(os.getenv("DB_PATH", "data/support.db"))
DB_PATH = str(_db_path if _db_path.is_absolute() else BASE_DIR / _db_path)

# Purely cosmetic — used in the "your refund is under review" message so the
# customer has an expectation to anchor on. Every eligible refund request
# goes through manual review now, regardless of amount.
APPROVAL_TURNAROUND_HOURS = _positive_int("APPROVAL_TURNAROUND_HOURS", 24)
LLM_TIMEOUT_SECONDS = _positive_int("LLM_TIMEOUT_SECONDS", 30)
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
RATE_LIMIT_ENABLED = _boolean("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_REQUESTS = _positive_int("RATE_LIMIT_REQUESTS", 10)
RATE_LIMIT_WINDOW_SECONDS = _positive_int("RATE_LIMIT_WINDOW_SECONDS", 60)
LLM_RATE_LIMIT_REQUESTS = _positive_int("LLM_RATE_LIMIT_REQUESTS", 60)
RATE_LIMIT_PREFIX = os.getenv("RATE_LIMIT_PREFIX", "customer-support").strip()


def configuration_problems() -> list[str]:
    problems = []
    if not LLM_MODEL:
        problems.append("Set LLM_MODEL in .env.")
    if LLM_MODEL.startswith(("gpt-", "openai/", "o1", "o3", "o4")):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or key == "your-api-key-here":
            problems.append("Set OPENAI_API_KEY in .env.")
    if RATE_LIMIT_ENABLED:
        url = urlparse(UPSTASH_REDIS_REST_URL)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            problems.append("Set UPSTASH_REDIS_REST_URL to an HTTPS endpoint without embedded credentials.")
        if not UPSTASH_REDIS_REST_TOKEN or UPSTASH_REDIS_REST_TOKEN == "your-redis-rest-token":
            problems.append("Set UPSTASH_REDIS_REST_TOKEN to a Redis token with write access.")
        if not RATE_LIMIT_PREFIX:
            problems.append("RATE_LIMIT_PREFIX must not be empty.")
    return problems
