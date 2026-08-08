"""Environment-based configuration for the SuperBrain dashboard.

The backend may run on a different machine than this dashboard, so the base
URL and API key always come from this dashboard's own .env — never from
anything under backend/.
"""

from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    request_timeout: float = 15.0


def get_settings() -> Settings:
    api_url = os.getenv("SUPERBRAIN_API_URL", "").strip().rstrip("/")
    api_key = os.getenv("SUPERBRAIN_API_KEY", "").strip()
    if not api_url or not api_key:
        raise RuntimeError(
            "SUPERBRAIN_API_URL and SUPERBRAIN_API_KEY must both be set in "
            "superbrain-dashboard/.env (copy .env.example to get started)."
        )
    return Settings(api_url=api_url, api_key=api_key)
