"""Thin HTTP client for the SuperBrain backend API."""

import requests

from .config import Settings


class ApiError(Exception):
    """Raised for any non-2xx response or connection failure, with a
    user-facing message ready to hand to st.error()."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, settings: Settings):
        self._base = settings.api_url
        self._headers = {"X-API-Key": settings.api_key}
        self._timeout = settings.request_timeout

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base}{path}"
        try:
            resp = requests.request(
                method, url, headers=self._headers, timeout=self._timeout, **kwargs
            )
        except requests.exceptions.ConnectionError as e:
            raise ApiError(
                f"Could not reach the SuperBrain backend at {self._base}. "
                "Check that it's running and that SUPERBRAIN_API_URL is correct."
            ) from e
        except requests.exceptions.Timeout as e:
            raise ApiError(f"Request to {url} timed out after {self._timeout}s.") from e

        if resp.status_code == 401:
            raise ApiError(
                "Backend rejected the API key (401). Check SUPERBRAIN_API_KEY.", 401
            )
        if resp.status_code == 503:
            raise ApiError(
                "Backend could not generate an embedding (503) — is OPENAI_API_KEY "
                "configured on the backend? Semantic search is unavailable.",
                503,
            )
        if not resp.ok:
            raise ApiError(
                f"Backend error {resp.status_code} calling {path}: {resp.text[:300]}",
                resp.status_code,
            )
        return resp.json()

    def export(self, limit: int = 50000, offset: int = 0) -> dict:
        return self._request(
            "GET", "/export", params={"limit": limit, "offset": offset, "format": "json"}
        )

    def search_semantic(self, q: str, limit: int = 20, min_similarity: float = 0.0) -> dict:
        return self._request(
            "GET",
            "/search/semantic",
            params={"q": q, "limit": limit, "min_similarity": min_similarity},
        )

    def update_post(self, shortcode: str, updates: dict) -> dict:
        return self._request("PUT", f"/post/{shortcode}", json=updates)

    def hide_post(self, shortcode: str) -> dict:
        return self._request("DELETE", f"/post/{shortcode}")
