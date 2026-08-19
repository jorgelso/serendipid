#!/usr/bin/env python3
"""
AI Model Router for SuperBrain
================================
Multi-provider routing with automatic fallback, response-time ranking,
and dynamic re-ranking as models change speed or go down.

Inspired by / referencing:
  • FreeRide (Shaivpidadi/FreeRide) — dynamic OpenRouter free-model discovery,
    quality scoring (context/capabilities/recency/provider trust), 30-min
    rate-limit cooldown, 6-hour cache
  • Nexlify (dev-sufyaan/Nexlify) — route:"fallback" uptime optimizer, newer
    model IDs (QwQ-32B, DeepSeek-Chat, Dolphin-Mistral, DeepSeek-R1-Qwen-32B),
    Google + Groq + OpenRouter unified approach
  • openrouter-free-model (jomonylw) — free model detection logic

Priority order (defaults, adjusted dynamically by measured latency):
  TEXT:   OpenAI (if configured) → Groq → Gemini → OpenRouter (hardcoded best) → Dynamic free OpenRouter → Local Ollama
  VISION: OpenAI (if configured) → Gemini → Groq Vision → OpenRouter Vision → Local Ollama Vision

API keys — store in backend/.api_keys (gitignored), one per line:
    GROQ_API_KEY=gsk_...
    GEMINI_API_KEY=AIza...
    OPENROUTER_API_KEY=sk-or-...
    OPENAI_API_KEY=sk-...

Performance state persisted to backend/model_rankings.json (rankings survive restarts).
Dynamic model list cached in backend/openrouter_free_models.json (refreshed every 6 h).

CLI:
  python model_router.py                  → show rankings
  python model_router.py reset <key>      → clear cooldown for a model key
  python model_router.py refresh          → force-refresh OpenRouter free model list
"""

import os
import json
import time
import base64
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

CONFIG_DIR    = Path(__file__).resolve().parent.parent / "config"
RANKINGS_FILE = CONFIG_DIR / "model_rankings.json"
API_KEYS_FILE = CONFIG_DIR / ".api_keys"

# How long to cool-down a failing model before retrying (seconds)
MODEL_DOWN_COOLDOWN_S   = 300    # generic errors (5 min)
MODEL_RATE_LIMIT_COOLDOWN_S = 1800  # HTTP 429 rate-limit (30 min) — FreeRide approach
# Exponential moving average weight for response-time estimates
EMA_ALPHA = 0.3

# Cache file for dynamically discovered free OpenRouter models (FreeRide approach)
OPENROUTER_FREE_CACHE_FILE  = CONFIG_DIR / "openrouter_free_models.json"
OPENROUTER_FREE_CACHE_HOURS = 6   # re-fetch every 6 h
OPENROUTER_API_MODELS_URL   = "https://openrouter.ai/api/v1/models"

# Trusted providers — affects scoring weight for dynamic discovery (FreeRide)
TRUSTED_PROVIDERS = [
    "google", "meta-llama", "mistralai", "deepseek",
    "nvidia", "qwen", "microsoft", "allenai", "arcee-ai",
]

# Quality-score weights used to rank free OpenRouter models (FreeRide approach)
RANKING_WEIGHTS = {
    "context_length": 0.40,  # Longer = handle bigger payloads
    "capabilities":   0.30,  # Vision / tools / structured output
    "recency":        0.20,  # Newer models = better perf
    "provider_trust": 0.10,  # Prefer known providers
}

# The OpenAI model used for the router's primary "openai" provider slot —
# text, vision, chat, batch-mode summary requests, and importance scoring
# (see generate_importance_text()) all resolve to this one value, so
# switching models is a single config change rather than several. GPT-4.1
# and GPT-5.6 Luna are both known-good here (both support vision, both
# handled correctly by _openai_chat_params() below); other OpenAI chat
# models should work too as long as they accept the same request shape.
# Override with OPENAI_TEXT_MODEL=gpt-5.6-luna (or similar) to switch.
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1")

# ─────────────────────────────────────────────────────────────────────────────
#  MODEL REGISTRY
#  Each entry defines the key, provider, model ID, task type, and base priority.
#  base_priority: lower = preferred.  100+ = local last-resort.
# ─────────────────────────────────────────────────────────────────────────────

MODELS: List[Dict[str, Any]] = [
    # ── TEXT ─────────────────────────────────────────────────────────────────
    {
        "key": "openai_gpt41",
        "provider": "openai",
        "model_id": OPENAI_TEXT_MODEL,
        "type": "text",
        "base_priority": 0,
        "desc": f"OpenAI {OPENAI_TEXT_MODEL} — primary provider (paid, tried first when configured)",
    },
    {
        "key": "groq_gpt_oss_20b",
        "provider": "groq",
        "model_id": "openai/gpt-oss-20b",
        "type": "text",
        "base_priority": 0.5,
        "desc": "Groq GPT-OSS 20B — fastest model on Groq at 1000 t/s",
    },
    {
        "key": "groq_llama33_70b",
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "type": "text",
        "base_priority": 1,
        "desc": "Groq LLaMA-3.3 70B — strong quality, 280 t/s",
    },
    {
        "key": "groq_llama4_scout",
        "provider": "groq",
        "model_id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "type": "text",
        "base_priority": 1.5,
        "desc": "Groq Llama-4 Scout 17B — multimodal, 750 t/s (preview)",
    },
    {
        "key": "groq_llama31_8b",
        "provider": "groq",
        "model_id": "llama-3.1-8b-instant",
        "type": "text",
        "base_priority": 2,
        "desc": "Groq LLaMA-3.1 8B — ultra-fast at 560 t/s, great for summaries",
    },
    {
        "key": "groq_qwen3_32b",
        "provider": "groq",
        "model_id": "qwen/qwen3-32b",
        "type": "text",
        "base_priority": 2.5,
        "desc": "Groq Qwen3-32B — strong reasoning, 400 t/s (preview)",
    },
    {
        "key": "groq_gpt_oss_120b",
        "provider": "groq",
        "model_id": "openai/gpt-oss-120b",
        "type": "text",
        "base_priority": 3,
        "desc": "Groq GPT-OSS 120B — flagship 120B model, 500 t/s",
    },
    {
        "key": "groq_gemma2_9b",
        "provider": "groq",
        "model_id": "gemma2-9b-it",
        "type": "text",
        "base_priority": 3.5,
        "desc": "Groq Gemma-2 9B (deprecated fallback)",
    },
    {
        "key": "groq_deepseek_r1_32b",
        "provider": "groq",
        "model_id": "deepseek-r1-distill-qwen-32b",
        "type": "text",
        "base_priority": 3.8,
        "desc": "Groq DeepSeek-R1 Distill Qwen-32B — reasoning (deprecated fallback)",
    },
    {
        "key": "gemini_25_flash",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash",
        "type": "text",
        "base_priority": 4,
        "desc": "Gemini 2.5 Flash — best price-performance, low-latency with reasoning",
    },
    {
        "key": "gemini_25_flash_lite",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash-lite",
        "type": "text",
        "base_priority": 4.5,
        "desc": "Gemini 2.5 Flash-Lite — fastest & most budget-friendly in 2.5 family",
    },
    {
        "key": "gemini_25_pro",
        "provider": "gemini",
        "model_id": "gemini-2.5-pro",
        "type": "text",
        "base_priority": 5,
        "desc": "Gemini 2.5 Pro — most advanced 2.5, deep reasoning & coding",
    },
    {
        "key": "gemini_3_flash",
        "provider": "gemini",
        "model_id": "gemini-3-flash-preview",
        "type": "text",
        "base_priority": 5.5,
        "desc": "Gemini 3 Flash Preview — frontier-class, rivals larger models",
    },
    {
        "key": "gemini_3_pro",
        "provider": "gemini",
        "model_id": "gemini-3-pro-preview",
        "type": "text",
        "base_priority": 6,
        "desc": "Gemini 3 Pro Preview — state-of-the-art reasoning & multimodal",
    },
    {
        "key": "gemini_31_pro",
        "provider": "gemini",
        "model_id": "gemini-3.1-pro-preview",
        "type": "text",
        "base_priority": 6.5,
        "desc": "Gemini 3.1 Pro Preview — most advanced, agentic & vibe coding",
    },
    # ── Deprecated Gemini models (kept as deep fallbacks) ────────────────────
    {
        "key": "gemini_20_flash",
        "provider": "gemini",
        "model_id": "gemini-2.0-flash",
        "type": "text",
        "base_priority": 7,
        "desc": "Gemini 2.0 Flash (deprecated — fallback only)",
    },
    {
        "key": "gemini_20_flash_lite",
        "provider": "gemini",
        "model_id": "gemini-2.0-flash-lite",
        "type": "text",
        "base_priority": 7.5,
        "desc": "Gemini 2.0 Flash-Lite (deprecated — fallback only)",
    },
    {
        "key": "gemini_15_flash",
        "provider": "gemini",
        "model_id": "gemini-1.5-flash",
        "type": "text",
        "base_priority": 8,
        "desc": "Gemini 1.5 Flash (deprecated — fallback only)",
    },
    {
        "key": "openrouter_llama33_70b",
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3.3-70b-instruct:free",
        "type": "text",
        "base_priority": 7,
        "desc": "OpenRouter LLaMA-3.3 70B (free, 128K ctx)",
    },
    {
        "key": "openrouter_deepseek_r1_0528",
        "provider": "openrouter",
        "model_id": "deepseek/deepseek-r1-0528:free",
        "type": "text",
        "base_priority": 7.5,
        "desc": "OpenRouter DeepSeek R1-0528 (free, 163K ctx) — latest reasoning model",
    },
    {
        "key": "openrouter_qwen3_235b",
        "provider": "openrouter",
        "model_id": "qwen/qwen3-235b-a22b-thinking-2507:free",
        "type": "text",
        "base_priority": 8,
        "desc": "OpenRouter Qwen3-235B Thinking (free, 131K ctx) — frontier reasoning",
    },
    {
        "key": "openrouter_hermes3_405b",
        "provider": "openrouter",
        "model_id": "nousresearch/hermes-3-llama-3.1-405b:free",
        "type": "text",
        "base_priority": 8.5,
        "desc": "OpenRouter Hermes-3 LLaMA-3.1 405B (free, 131K ctx)",
    },
    {
        "key": "openrouter_gpt_oss_120b",
        "provider": "openrouter",
        "model_id": "openai/gpt-oss-120b:free",
        "type": "text",
        "base_priority": 9,
        "desc": "OpenRouter GPT-OSS 120B (free, 131K ctx)",
    },
    {
        "key": "openrouter_gpt_oss_20b",
        "provider": "openrouter",
        "model_id": "openai/gpt-oss-20b:free",
        "type": "text",
        "base_priority": 9.5,
        "desc": "OpenRouter GPT-OSS 20B (free, 131K ctx)",
    },
    {
        "key": "openrouter_stepfun_flash",
        "provider": "openrouter",
        "model_id": "stepfun/step-3.5-flash:free",
        "type": "text",
        "base_priority": 10,
        "desc": "OpenRouter StepFun Step-3.5 Flash (free, 256K ctx)",
    },
    {
        "key": "openrouter_nemotron_30b",
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b:free",
        "type": "text",
        "base_priority": 10.5,
        "desc": "OpenRouter NVIDIA Nemotron-3 Nano 30B (free, 256K ctx)",
    },
    {
        "key": "openrouter_qwen3_next_80b",
        "provider": "openrouter",
        "model_id": "qwen/qwen3-next-80b-a3b-instruct:free",
        "type": "text",
        "base_priority": 11,
        "desc": "OpenRouter Qwen3-Next 80B (free, 262K ctx)",
    },
    {
        "key": "openrouter_gemma3_27b",
        "provider": "openrouter",
        "model_id": "google/gemma-3-27b-it:free",
        "type": "text",
        "base_priority": 11.5,
        "desc": "OpenRouter Gemma-3 27B (free, 131K ctx) — also vision capable",
    },
    {
        "key": "openrouter_mistral_small31",
        "provider": "openrouter",
        "model_id": "mistralai/mistral-small-3.1-24b-instruct:free",
        "type": "text",
        "base_priority": 12,
        "desc": "OpenRouter Mistral Small 3.1 24B (free, 128K ctx) — also vision capable",
    },
    {
        "key": "openrouter_glm45_air",
        "provider": "openrouter",
        "model_id": "z-ai/glm-4.5-air:free",
        "type": "text",
        "base_priority": 12.5,
        "desc": "OpenRouter GLM-4.5 Air (free, 131K ctx)",
    },
    {
        "key": "openrouter_dolphin_venice",
        "provider": "openrouter",
        "model_id": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "type": "text",
        "base_priority": 13,
        "desc": "OpenRouter Dolphin Mistral 24B Venice Edition (free, 32K ctx)",
    },
    {
        "key": "local_qwen3",
        "provider": "ollama",
        "model_id": "qwen3-vl:4b",
        "type": "text",
        "base_priority": 100,
        "desc": "Local Ollama Qwen3-VL 4B — LAST RESORT (requires Ollama running)",
    },

    # ── VISION ───────────────────────────────────────────────────────────────
    {
        "key": "openai_gpt41_vision",
        "provider": "openai",
        "model_id": OPENAI_TEXT_MODEL,
        "type": "vision",
        "base_priority": 0,
        "desc": f"OpenAI {OPENAI_TEXT_MODEL} Vision — primary provider (paid, tried first when configured)",
    },
    {
        "key": "gemini_25_flash_vision",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash",
        "type": "vision",
        "base_priority": 1,
        "desc": "Gemini 2.5 Flash Vision — best price-performance multimodal",
    },
    {
        "key": "gemini_25_flash_lite_vision",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash-lite",
        "type": "vision",
        "base_priority": 1.5,
        "desc": "Gemini 2.5 Flash-Lite Vision — fastest multimodal",
    },
    {
        "key": "gemini_25_pro_vision",
        "provider": "gemini",
        "model_id": "gemini-2.5-pro",
        "type": "vision",
        "base_priority": 2,
        "desc": "Gemini 2.5 Pro Vision — advanced multimodal understanding",
    },
    {
        "key": "gemini_3_flash_vision",
        "provider": "gemini",
        "model_id": "gemini-3-flash-preview",
        "type": "vision",
        "base_priority": 2.5,
        "desc": "Gemini 3 Flash Preview Vision — frontier-class multimodal",
    },
    {
        "key": "gemini_3_pro_vision",
        "provider": "gemini",
        "model_id": "gemini-3-pro-preview",
        "type": "vision",
        "base_priority": 3,
        "desc": "Gemini 3 Pro Preview Vision — state-of-the-art multimodal reasoning",
    },
    {
        "key": "gemini_31_pro_vision",
        "provider": "gemini",
        "model_id": "gemini-3.1-pro-preview",
        "type": "vision",
        "base_priority": 3.5,
        "desc": "Gemini 3.1 Pro Preview Vision — most advanced multimodal",
    },
    # ── Deprecated Gemini vision models (kept as deep fallbacks) ─────────────
    {
        "key": "gemini_20_flash_vision",
        "provider": "gemini",
        "model_id": "gemini-2.0-flash",
        "type": "vision",
        "base_priority": 4,
        "desc": "Gemini 2.0 Flash Vision (deprecated — fallback only)",
    },
    {
        "key": "gemini_20_flash_lite_vision",
        "provider": "gemini",
        "model_id": "gemini-2.0-flash-lite",
        "type": "vision",
        "base_priority": 4.5,
        "desc": "Gemini 2.0 Flash-Lite Vision (deprecated — fallback only)",
    },
    {
        "key": "gemini_15_flash_vision",
        "provider": "gemini",
        "model_id": "gemini-1.5-flash",
        "type": "vision",
        "base_priority": 4.8,
        "desc": "Gemini 1.5 Flash Vision (deprecated — fallback only)",
    },
    {
        "key": "groq_llama4_scout_vision",
        "provider": "groq",
        "model_id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "type": "vision",
        "base_priority": 5,
        "desc": "Groq Llama-4 Scout 17B Vision — multimodal, 750 t/s (preview)",
    },
    {
        "key": "groq_vision_11b",
        "provider": "groq",
        "model_id": "llama-3.2-11b-vision-preview",
        "type": "vision",
        "base_priority": 5.5,
        "desc": "Groq LLaMA-3.2 11B Vision (deprecated fallback)",
    },
    {
        "key": "groq_vision_90b",
        "provider": "groq",
        "model_id": "llama-3.2-90b-vision-preview",
        "type": "vision",
        "base_priority": 6,
        "desc": "Groq LLaMA-3.2 90B Vision — highest quality Groq vision (deprecated fallback)",
    },
    {
        "key": "openrouter_qwen3_vl_235b",
        "provider": "openrouter",
        "model_id": "qwen/qwen3-vl-235b-a22b-thinking:free",
        "type": "vision",
        "base_priority": 7,
        "desc": "OpenRouter Qwen3-VL 235B Vision (free, 131K ctx) — flagship vision model",
    },
    {
        "key": "openrouter_qwen3_vl_30b",
        "provider": "openrouter",
        "model_id": "qwen/qwen3-vl-30b-a3b-thinking:free",
        "type": "vision",
        "base_priority": 7.5,
        "desc": "OpenRouter Qwen3-VL 30B Vision (free, 131K ctx)",
    },
    {
        "key": "openrouter_nvidia_vl",
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-nano-12b-v2-vl:free",
        "type": "vision",
        "base_priority": 8,
        "desc": "OpenRouter NVIDIA Nemotron-Nano 12B VL (free, 128K ctx) — supports video",
    },
    {
        "key": "openrouter_gemma3_vision",
        "provider": "openrouter",
        "model_id": "google/gemma-3-27b-it:free",
        "type": "vision",
        "base_priority": 8.5,
        "desc": "OpenRouter Gemma-3 27B Vision (free, 131K ctx)",
    },
    {
        "key": "openrouter_mistral_vision",
        "provider": "openrouter",
        "model_id": "mistralai/mistral-small-3.1-24b-instruct:free",
        "type": "vision",
        "base_priority": 9,
        "desc": "OpenRouter Mistral Small 3.1 24B Vision (free, 128K ctx)",
    },
    {
        "key": "local_qwen3_vl",
        "provider": "ollama",
        "model_id": "qwen3-vl:4b",
        "type": "vision",
        "base_priority": 100,
        "desc": "Local Ollama Qwen3-VL 4B — LAST RESORT (requires Ollama running)",
    },

    # ── CHAT (RAG chatbot answer generation) ────────────────────────────────
    # Deliberately separate from the "text" task's provider order/keys above
    # — the chatbot always tries Gemini, then OpenAI (its own dedicated
    # OPENAI_CHAT_API_KEY, kept independent from OPENAI_API_KEY which is used
    # for analysis summaries and embeddings), then local Ollama.
    {
        "key": "chat_gemini_flash",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash",
        "type": "chat",
        "base_priority": 0,
        "desc": "Gemini 2.5 Flash — primary provider for RAG chatbot answers",
    },
    {
        "key": "chat_openai_gpt41",
        "provider": "openai",
        "model_id": OPENAI_TEXT_MODEL,
        "type": "chat",
        "base_priority": 1,
        "key_name": "OPENAI_CHAT_API_KEY",
        "desc": f"OpenAI {OPENAI_TEXT_MODEL} (dedicated chatbot key) — second fallback for RAG chatbot",
    },
    {
        "key": "chat_local_qwen3",
        "provider": "ollama",
        "model_id": "qwen3-vl:4b",
        "type": "chat",
        "base_priority": 2,
        "desc": "Local Ollama — LAST RESORT for RAG chatbot (requires Ollama running)",
    },
]

MODELS_BY_KEY: Dict[str, Dict] = {m["key"]: m for m in MODELS}


def _has_image_input(m: Dict) -> bool:
    """Return True if an OpenRouter model object supports image (vision) input."""
    arch = m.get("architecture", {})
    # OpenRouter returns input_modalities as a list, e.g. ["text", "image"]
    mods: Any = arch.get("input_modalities") or arch.get("modality") or ""
    if isinstance(mods, list):
        return "image" in mods
    return "image" in str(mods)


class RateLimitError(Exception):
    pass

# ─────────────────────────────────────────────────────────────────────────────
#  MODEL ROUTER
# ─────────────────────────────────────────────────────────────────────────────

class ModelRouter:
    """
    Routes AI requests to the best available model.
    - Tries models in order of effective priority (base + response-time penalty)
    - Marks failed models as 'down' for MODEL_DOWN_COOLDOWN_S seconds
    - Updates EMA response-time estimates after each successful call
    - Saves state to model_rankings.json so rankings persist across restarts
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._api_keys: Dict[str, str] = {}
        self._state: Dict[str, Dict] = {}
        # Model key of the most recent successful generate_*/analyze_images
        # call on this instance — callers that need to know which model
        # actually produced a given result (e.g. main.py stamping
        # analyses.model_used) read this right after the call returns.
        self.last_model_used: Optional[str] = None
        # Dynamically discovered free OpenRouter models (FreeRide approach)
        self._dynamic_models: Dict[str, Dict] = {}
        self._dynamic_models_lock = threading.Lock()
        self._load_api_keys()
        self._load_state()
        self._print_startup_status()
        # Background: discover & rank free OpenRouter models, auto-refreshes every OPENROUTER_FREE_CACHE_HOURS
        threading.Thread(target=self._auto_refresh_loop, daemon=True).start()

    # ── Configuration ─────────────────────────────────────────────────────────

    def _load_api_keys(self):
        """Load API keys from environment and .api_keys file."""
        for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_CHAT_API_KEY"):
            v = os.environ.get(k)
            if v:
                self._api_keys[k] = v

        if API_KEYS_FILE.exists():
            with open(API_KEYS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        self._api_keys[k.strip()] = v.strip()

    def _key(self, name: str) -> Optional[str]:
        return self._api_keys.get(name) or None

    def reload_api_keys(self):
        """Reload API keys from environment and .api_keys file."""
        self._api_keys.clear()
        self._load_api_keys()
        logger.info("🔑 API keys reloaded")

    def get_available_providers(self) -> Dict[str, bool]:
        """Return dict of provider -> has_key."""
        return {
            "groq": bool(self._key("GROQ_API_KEY")),
            "gemini": bool(self._key("GEMINI_API_KEY")),
            "openrouter": bool(self._key("OPENROUTER_API_KEY")),
            "openai": bool(self._key("OPENAI_API_KEY")),
            "ollama": True,  # Always available
        }

    def set_api_key(self, provider: str, api_key: str) -> bool:
        """Set an API key for a provider and persist to file."""
        key_name = f"{provider.upper()}_API_KEY"
        valid_providers = ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]
        
        if key_name not in valid_providers:
            return False
        
        # Update in-memory
        self._api_keys[key_name] = api_key
        
        # Persist to file
        self._persist_api_key(key_name, api_key)
        return True

    def delete_api_key(self, provider: str) -> bool:
        """Delete an API key for a provider."""
        key_name = f"{provider.upper()}_API_KEY"
        valid_providers = ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]
        
        if key_name not in valid_providers:
            return False
        
        # Remove from memory
        self._api_keys.pop(key_name, None)
        
        # Remove from file
        self._remove_api_key(key_name)
        return True

    def _persist_api_key(self, key_name: str, api_key: str):
        """Persist an API key to the .api_keys file."""
        lines = []
        updated = False
        
        if API_KEYS_FILE.exists():
            with open(API_KEYS_FILE, "r") as f:
                for line in f:
                    if line.strip().startswith(f"{key_name}="):
                        lines.append(f"{key_name}={api_key}\n")
                        updated = True
                    else:
                        lines.append(line)
        
        if not updated:
            lines.append(f"{key_name}={api_key}\n")
        
        with open(API_KEYS_FILE, "w") as f:
            f.writelines(lines)

    def _remove_api_key(self, key_name: str):
        """Remove an API key from the .api_keys file."""
        if not API_KEYS_FILE.exists():
            return
        
        lines = []
        with open(API_KEYS_FILE, "r") as f:
            for line in f:
                if not line.strip().startswith(f"{key_name}="):
                    lines.append(line)
        
        with open(API_KEYS_FILE, "w") as f:
            f.writelines(lines)

    # ── Dynamic OpenRouter free-model discovery (FreeRide approach) ────────────

    def _default_model_state_dynamic(self, key: str, base_priority: float = 50) -> Dict:
        """Create a default state dict for any model key (static or dynamic)."""
        m = MODELS_BY_KEY.get(key) or self._dynamic_models.get(key) or {}
        bp = m.get("base_priority", base_priority)
        return {
            "key": key,
            "avg_response_s": None,
            "success_count": 0,
            "fail_count": 0,
            "down_until": None,
            "last_used": None,
            "last_error": None,
            "base_priority": bp,
        }

    def _score_openrouter_model(self, m: Dict) -> float:
        """
        Score an OpenRouter model 0-1 for quality ranking.
        Factors: context length (40%), capabilities (30%), recency (20%), provider trust (10%).
        Based on FreeRide's ranking algorithm.
        """
        score = 0.0
        # Context length: normalise to 1M tokens
        ctx = m.get("context_length", 0)
        score += min(ctx / 1_000_000, 1.0) * RANKING_WEIGHTS["context_length"]
        # Capabilities: normalise to 10 supported parameters
        caps = m.get("supported_parameters", [])
        score += min(len(caps) / 10, 1.0) * RANKING_WEIGHTS["capabilities"]
        # Recency: newer = better (scores 1 at launch, decays to 0 over 1 year)
        created = m.get("created", 0)
        if created:
            days_old = (time.time() - created) / 86400
            score += max(0.0, 1.0 - days_old / 365) * RANKING_WEIGHTS["recency"]
        # Provider trust
        model_id = m.get("id", "")
        provider = model_id.split("/")[0] if "/" in model_id else ""
        if provider in TRUSTED_PROVIDERS:
            trust_idx = TRUSTED_PROVIDERS.index(provider)
            score += (1 - trust_idx / len(TRUSTED_PROVIDERS)) * RANKING_WEIGHTS["provider_trust"]
        return score

    def _auto_refresh_loop(self):
        """Run _refresh_openrouter_models once immediately, then repeat every OPENROUTER_FREE_CACHE_HOURS."""
        while True:
            try:
                self._refresh_openrouter_models()
            except Exception as e:
                print(f"??  OpenRouter auto-refresh error: {e}")
            time.sleep(OPENROUTER_FREE_CACHE_HOURS * 3600)

    def _refresh_openrouter_models(self):
        """
        Fetch free models from OpenRouter API, score & rank them, cache to disk,
        and inject the top models into self._dynamic_models for routing.
        Called by _auto_refresh_loop every OPENROUTER_FREE_CACHE_HOURS; safe to call manually.
        Based on FreeRide's fetch_all_models + filter_free_models + rank_free_models.
        """
        api_key = self._key("OPENROUTER_API_KEY")
        if not api_key:
            return  # No key → skip

        # Check cache freshness
        try:
            if OPENROUTER_FREE_CACHE_FILE.exists():
                cache = json.loads(OPENROUTER_FREE_CACHE_FILE.read_text())
                cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
                if (datetime.utcnow() - cached_at).total_seconds() < OPENROUTER_FREE_CACHE_HOURS * 3600:
                    models = cache.get("models", [])
                    self._inject_dynamic_models(models)
                    vision_count = sum(1 for m in models if _has_image_input(m))
                    next_refresh_m = int(
                        (OPENROUTER_FREE_CACHE_HOURS * 3600
                         - (datetime.utcnow() - cached_at).total_seconds()) / 60
                    )
                    print(f"🔄 OpenRouter free models: loaded {len(models)} from cache "
                          f"({vision_count} vision-capable) — next refresh in ~{next_refresh_m}m")
                    return
        except Exception:
            pass

        # Fetch from API
        try:
            import requests as _req
            resp = _req.get(
                OPENROUTER_API_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            all_models = resp.json().get("data", [])
        except Exception as e:
            # if "429" in str(e) or "quota" in str(e).lower():
            #     raise RateLimitError("Quota limit hit")
            # raise e
            print(f"⚠️  OpenRouter free model discovery failed: {e}")
            return

        # Filter for free models (pricing.prompt == 0 or :free suffix)
        free_models = []
        for m in all_models:
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            try:
                if float(pricing.get("prompt", 1)) == 0:
                    free_models.append(m)
                    continue
            except (TypeError, ValueError):
                pass
            if ":free" in mid and m not in free_models:
                free_models.append(m)

        # Score and rank
        scored = sorted(free_models, key=self._score_openrouter_model, reverse=True)
        # Take top 30 across all types (text + vision-capable)
        top = scored[:30]

        # Persist cache
        try:
            OPENROUTER_FREE_CACHE_FILE.write_text(json.dumps({
                "cached_at": datetime.utcnow().isoformat(),
                "models": top,
            }, indent=2))
        except Exception:
            pass

        self._inject_dynamic_models(top)
        vision_count = sum(
            1 for m in top
            if _has_image_input(m)
        )
        print(f"🔄 OpenRouter free models: discovered & ranked {len(top)} models ({vision_count} vision-capable) — next refresh in {OPENROUTER_FREE_CACHE_HOURS}h")

    def _inject_dynamic_models(self, raw_models: List[Dict]):
        """
        Convert raw OpenRouter API model objects into routing entries and
        add them to self._dynamic_models with priorities starting at 20
        (after all hardcoded models, so they serve as additional fallbacks).
        Models already in the static MODELS_BY_KEY are skipped.
        Vision-capable models get an additional entry with type='vision'.
        """
        static_model_ids = {mm["model_id"] for mm in MODELS_BY_KEY.values()}
        with self._dynamic_models_lock:
            self._dynamic_models.clear()
            for i, m in enumerate(raw_models):
                mid = m.get("id", "")
                if not mid:
                    continue
                safe_id = mid.replace("/", "_").replace(":", "_").replace(".", "_")
                model_id_free = mid if ":free" in mid else f"{mid}:free"
                score = self._score_openrouter_model(m)
                is_vision = _has_image_input(m)
                base_p = 20 + i

                # Text entry — skip if already a static entry
                if mid not in static_model_ids:
                    key = f"dyn_{safe_id}"
                    entry = {
                        "key": key,
                        "provider": "openrouter",
                        "model_id": model_id_free,
                        "type": "text",
                        "base_priority": base_p,
                        "desc": f"[Dynamic] {mid} — score={score:.3f}",
                    }
                    self._dynamic_models[key] = entry
                    if key not in self._state:
                        self._state[key] = self._default_model_state_dynamic(key, base_p)

                # Vision entry — inject if vision-capable and not already in static vision models
                if is_vision:
                    static_vision_ids = {
                        mm["model_id"] for mm in MODELS_BY_KEY.values() if mm["type"] == "vision"
                    }
                    if mid not in static_vision_ids:
                        vkey = f"dyn_v_{safe_id}"
                        ventry = {
                            "key": vkey,
                            "provider": "openrouter",
                            "model_id": model_id_free,
                            "type": "vision",
                            "base_priority": base_p,
                            "desc": f"[Dynamic-Vision] {mid} — score={score:.3f}",
                        }
                        self._dynamic_models[vkey] = ventry
                        if vkey not in self._state:
                            self._state[vkey] = self._default_model_state_dynamic(vkey, base_p)

    # ── State persistence ──────────────────────────────────────────────────────

    def _default_model_state(self, model_key: str) -> Dict:
        """Backward-compat wrapper — delegates to _default_model_state_dynamic."""
        return self._default_model_state_dynamic(model_key)

    def _load_state(self):
        if RANKINGS_FILE.exists():
            try:
                with open(RANKINGS_FILE, "r") as f:
                    saved = json.load(f)
                for key in MODELS_BY_KEY:
                    self._state[key] = saved.get(key, self._default_model_state(key))
                return
            except Exception:
                pass
        for key in MODELS_BY_KEY:
            self._state[key] = self._default_model_state(key)

    def _save_state(self):
        try:
            with open(RANKINGS_FILE, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
        except Exception:
            pass

    # ── Availability & ranking ─────────────────────────────────────────────────

    def _is_available(self, model_key: str) -> bool:
        """True if the model has an API key (or is local) and is not in cooldown."""
        # Look up in static registry first, then dynamic
        m = MODELS_BY_KEY.get(model_key) or self._dynamic_models.get(model_key)
        if m is None:
            return False
        prov = m["provider"]

        if prov == "groq" and not self._key("GROQ_API_KEY"):
            return False
        if prov == "gemini" and not self._key("GEMINI_API_KEY"):
            return False
        if prov == "openrouter" and not self._key("OPENROUTER_API_KEY"):
            return False
        # "key_name" lets a model entry use a dedicated key instead of the
        # default OPENAI_API_KEY (e.g. the chat task's own OPENAI_CHAT_API_KEY,
        # kept independent from the key used for analysis/embeddings).
        if prov == "openai" and not self._key(m.get("key_name", "OPENAI_API_KEY")):
            return False

        s = self._state.get(model_key, self._default_model_state_dynamic(model_key))
        if s.get("down_until"):
            try:
                if datetime.utcnow() < datetime.fromisoformat(s["down_until"]):
                    return False
            except Exception:
                pass
        return True

    def _effective_priority(self, model_key: str) -> float:
        """
        Compute sort key (lower = better).
        = base_priority + response_time_penalty (0–10)
        Unmeasured models keep their exact base_priority.
        """
        m = MODELS_BY_KEY.get(model_key) or self._dynamic_models.get(model_key) or {}
        s = self._state.get(model_key) or {}
        base = s.get("base_priority", m.get("base_priority", 50))
        avg_t = s.get("avg_response_s")
        if avg_t is None:
            return float(base)
        # Each extra 3 s above a 2 s baseline adds 1 point of penalty (max 10)
        penalty = min(10.0, max(0.0, (avg_t - 2.0) / 3.0))
        return float(base) + penalty

    def _ranked_models(self, task_type: str) -> List[str]:
        """Return available model keys for task_type, best first (static + dynamic)."""
        static_candidates = [
            k for k, m in MODELS_BY_KEY.items()
            if m["type"] == task_type and self._is_available(k)
        ]
        # Add dynamic OpenRouter models (text only; no vision discovery yet)
        dynamic_candidates = []
        if task_type == "text":
            with self._dynamic_models_lock:
                dynamic_candidates = [
                    k for k, m in self._dynamic_models.items()
                    if m["type"] == task_type and self._is_available(k)
                    and k not in MODELS_BY_KEY  # don't double-count
                ]
        all_candidates = static_candidates + dynamic_candidates
        return sorted(all_candidates, key=self._effective_priority)

    # ── State recording ────────────────────────────────────────────────────────

    def _record_success(self, model_key: str, elapsed: float):
        # Ensure state exists (dynamic models may not be pre-seeded)
        if model_key not in self._state:
            self._state[model_key] = self._default_model_state_dynamic(model_key)
        self.last_model_used = model_key
        with self._lock:
            s = self._state[model_key]
            prev = s["avg_response_s"]
            s["avg_response_s"] = (
                elapsed if prev is None
                else EMA_ALPHA * elapsed + (1 - EMA_ALPHA) * prev
            )
            s["success_count"] = s.get("success_count", 0) + 1
            s["down_until"] = None
            s["last_used"] = datetime.utcnow().isoformat()
            s["last_error"] = None
            self._save_state()

    def _record_failure(self, model_key: str, error: str, status_code: int = 0):
        """
        Mark a model as down after failure.
        HTTP 429 rate-limit uses a longer cooldown (30 min, FreeRide approach).
        Other errors use the short cooldown (5 min).
        """
        is_rate_limit = (status_code == 429) or ("429" in str(error)) or ("rate" in str(error).lower() and "limit" in str(error).lower())
        cooldown = MODEL_RATE_LIMIT_COOLDOWN_S if is_rate_limit else MODEL_DOWN_COOLDOWN_S
        reason  = "rate-limited" if is_rate_limit else "error"

        # Ensure state exists for dynamically discovered models too
        if model_key not in self._state:
            self._state[model_key] = self._default_model_state_dynamic(model_key)

        with self._lock:
            s = self._state[model_key]
            s["fail_count"] = s.get("fail_count", 0) + 1
            s["last_error"] = str(error)[:200]
            s["down_until"] = (
                datetime.utcnow() + timedelta(seconds=cooldown)
            ).isoformat()
            self._save_state()
        print(
            f"  ⚠️  [{model_key}] {reason} — DOWN for {cooldown}s — {str(error)[:80]}"
        )

    # ── Provider implementations ───────────────────────────────────────────────

    def _groq_text(self, model_id: str, prompt: str) -> str:
        from groq import Groq
        client = Groq(api_key=self._key("GROQ_API_KEY"))
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7,
        )
        return r.choices[0].message.content.strip()

    def _groq_vision(self, model_id: str, prompt: str, images_b64: List[str]) -> str:
        from groq import Groq
        client = Groq(api_key=self._key("GROQ_API_KEY"))
        # Groq vision: send up to 1 image (11b model limit)
        content: List[Dict] = []
        for b64 in images_b64[:1]:  # Groq supports 1 image per request
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        content.append({"type": "text", "text": prompt})
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": content}],
            max_tokens=4000,
            temperature=0.7,
        )
        return r.choices[0].message.content.strip()

    def _gemini_text(self, model_id: str, prompt: str) -> str:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=self._key("GEMINI_API_KEY"))
        r = client.models.generate_content(
            model=model_id,
            contents=[prompt],
            config=gtypes.GenerateContentConfig(max_output_tokens=4000, temperature=0.7),
        )
        return r.text.strip()

    def _gemini_vision(self, model_id: str, prompt: str, images_b64: List[str]) -> str:
        from google import genai
        from google.genai import types as gtypes
        import base64
        client = genai.Client(api_key=self._key("GEMINI_API_KEY"))
        parts: List[Any] = [
            gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type="image/jpeg")
            for b64 in images_b64
        ]
        parts.append(prompt)
        r = client.models.generate_content(
            model=model_id,
            contents=parts,
            config=gtypes.GenerateContentConfig(max_output_tokens=4000, temperature=0.7),
        )
        return r.text.strip()

    def _openrouter_text(self, model_id: str, prompt: str) -> str:
        import requests
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._key('OPENROUTER_API_KEY')}",
                "HTTP-Referer": "https://github.com/superbrain",
                "X-Title": "SuperBrain",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.7,
                "route": "fallback",  # Nexlify uptime-optimizer: auto-fallback on provider failures
            },
            timeout=60,
        )
        if resp.status_code == 429:
            raise Exception(f"429 rate limit: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _openrouter_vision(self, model_id: str, prompt: str, images_b64: List[str]) -> str:
        import requests
        content: List[Dict] = []
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        content.append({"type": "text", "text": prompt})
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._key('OPENROUTER_API_KEY')}",
                "HTTP-Referer": "https://github.com/superbrain",
                "X-Title": "SuperBrain",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 4000,
                "temperature": 0.7,
                "route": "fallback",  # Nexlify uptime-optimizer: auto-fallback on provider failures
            },
            timeout=90,
        )
        if resp.status_code == 429:
            raise Exception(f"429 rate limit: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _openai_chat_params(model_id: str, max_tokens: int = 4000) -> Dict:
        """
        Build the token-limit/temperature portion of an OpenAI chat-completions
        request body, accounting for the GPT-5.x family's stricter API surface:
        those models reject the legacy 'max_tokens' param (need
        'max_completion_tokens' instead) and reject any non-default
        'temperature' value. GPT-4.1 and earlier accept 'max_completion_tokens'
        too, so it's used unconditionally; 'temperature' is only sent for
        pre-GPT-5 models.
        """
        params: Dict[str, Any] = {"max_completion_tokens": max_tokens}
        if not model_id.startswith("gpt-5"):
            params["temperature"] = 0.7
        return params

    def _openai_text(self, model_id: str, prompt: str, api_key: Optional[str] = None) -> str:
        import requests
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key or self._key('OPENAI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                **self._openai_chat_params(model_id),
            },
            timeout=60,
        )
        if resp.status_code == 429:
            raise Exception(f"429 rate limit: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _openai_vision(self, model_id: str, prompt: str, images_b64: List[str]) -> str:
        import requests
        content: List[Dict] = []
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        content.append({"type": "text", "text": prompt})
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._key('OPENAI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": content}],
                **self._openai_chat_params(model_id),
            },
            timeout=90,
        )
        if resp.status_code == 429:
            raise Exception(f"429 rate limit: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _ollama_text(self, model_id: str, prompt: str) -> str:
        import ollama
        r = ollama.generate(
            model=model_id,
            prompt=prompt,
            options={"temperature": 0.7, "num_predict": 4000},
        )
        return r.get("response", "").strip()

    def _ollama_vision(self, model_id: str, prompt: str, images_b64: List[str]) -> str:
        import ollama
        r = ollama.generate(
            model=model_id,
            prompt=prompt,
            images=images_b64,
            options={"temperature": 0.7, "num_predict": 4000},
        )
        return r.get("response", "").strip()

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_text(self, prompt: str) -> str:
        """
        Generate text using the best available model.
        Falls back through the ranked list until one succeeds.
        Raises RuntimeError if all fail.
        """
        ranked = self._ranked_models("text")
        if not ranked:
            raise RuntimeError(
                "No text models available. Add API keys to backend/config/.api_keys"
            )

        for key in ranked:
            m = MODELS_BY_KEY.get(key) or self._dynamic_models.get(key)
            if not m:
                continue
            print(f"  🤖 [{m['provider'].upper()}] {m['model_id']} ...", flush=True)
            t0 = time.time()
            try:
                prov = m["provider"]
                if prov == "groq":
                    result = self._groq_text(m["model_id"], prompt)
                elif prov == "gemini":
                    result = self._gemini_text(m["model_id"], prompt)
                elif prov == "openrouter":
                    result = self._openrouter_text(m["model_id"], prompt)
                elif prov == "openai":
                    result = self._openai_text(m["model_id"], prompt)
                elif prov == "ollama":
                    result = self._ollama_text(m["model_id"], prompt)
                else:
                    continue

                elapsed = time.time() - t0
                self._record_success(key, elapsed)
                print(f"  ✓ {elapsed:.1f}s", flush=True)
                return result

            except Exception as e:
                # Do not immediately abort on quota, try next model
                # if "429" in str(e) or "quota" in str(e).lower():
                #     raise RateLimitError("Quota limit hit")
                status = 429 if "429" in str(e) else 0
                self._record_failure(key, str(e), status_code=status)
                print(f"  ✗ Failed ({type(e).__name__}), trying next …", flush=True)

        raise RuntimeError("All text models failed.")

    def generate_importance_text(self, prompt: str) -> str:
        """
        Score a post's importance using OPENAI_TEXT_MODEL specifically,
        bypassing the latency-ranked fallback order that generate_text() uses.
        Importance needs *consistent* judgment across posts more than it needs
        speed — letting the provider drift to whichever model answers fastest
        at that moment (as happens for every other field in the combined
        summary prompt) produced visibly inconsistent scores between posts of
        comparable depth. Falls back to the standard ranked text order only if
        OpenAI is unavailable or fails, so scoring doesn't hard-break for
        setups without an OpenAI key.
        """
        if self._is_available("openai_gpt41"):
            t0 = time.time()
            try:
                result = self._openai_text(OPENAI_TEXT_MODEL, prompt)
                self._record_success("openai_gpt41", time.time() - t0)
                return result
            except Exception as e:
                status = 429 if "429" in str(e) else 0
                self._record_failure("openai_gpt41", str(e), status_code=status)
                print("  ✗ [openai_gpt41] importance scoring failed, falling back to ranked order …", flush=True)
        return self.generate_text(prompt)

    def generate_chat_text(self, prompt: str) -> str:
        """
        Generate a RAG chatbot answer using the "chat" task's own provider
        order (Gemini → OpenAI[dedicated OPENAI_CHAT_API_KEY] → local Ollama)
        — deliberately separate from generate_text()'s "text" task, so the
        chatbot's provider/key choice never depends on what's configured for
        analysis/summary generation.
        Raises RuntimeError if all fail.
        """
        ranked = self._ranked_models("chat")
        if not ranked:
            raise RuntimeError(
                "No chat models available. Add GEMINI_API_KEY, OPENAI_CHAT_API_KEY, "
                "or run local Ollama."
            )

        for key in ranked:
            m = MODELS_BY_KEY.get(key) or self._dynamic_models.get(key)
            if not m:
                continue
            print(f"  💬 [{m['provider'].upper()}] {m['model_id']} ...", flush=True)
            t0 = time.time()
            try:
                prov = m["provider"]
                if prov == "gemini":
                    result = self._gemini_text(m["model_id"], prompt)
                elif prov == "openai":
                    result = self._openai_text(
                        m["model_id"], prompt, api_key=self._key(m.get("key_name", "OPENAI_API_KEY"))
                    )
                elif prov == "ollama":
                    result = self._ollama_text(m["model_id"], prompt)
                else:
                    continue

                elapsed = time.time() - t0
                self._record_success(key, elapsed)
                print(f"  ✓ {elapsed:.1f}s", flush=True)
                return result

            except Exception as e:
                status = 429 if "429" in str(e) else 0
                self._record_failure(key, str(e), status_code=status)
                print(f"  ✗ Failed ({type(e).__name__}), trying next …", flush=True)

        raise RuntimeError("All chat models failed.")

    def analyze_images(self, prompt: str, images_b64: List[str]) -> str:
        """
        Analyze one or more images using the best available vision model.
        images_b64: list of base64-encoded JPEG strings.
        Falls back through the ranked list until one succeeds.
        Raises RuntimeError if all fail.
        """
        ranked = self._ranked_models("vision")
        if not ranked:
            raise RuntimeError(
                "No vision models available. Add API keys to backend/config/.api_keys"
            )

        for key in ranked:
            m = MODELS_BY_KEY.get(key) or self._dynamic_models.get(key)
            if not m:
                continue
            print(f"  🔭 [{m['provider'].upper()}] {m['model_id']} ...", flush=True)
            t0 = time.time()
            try:
                prov = m["provider"]
                if prov == "groq":
                    result = self._groq_vision(m["model_id"], prompt, images_b64)
                elif prov == "gemini":
                    result = self._gemini_vision(m["model_id"], prompt, images_b64)
                elif prov == "openrouter":
                    result = self._openrouter_vision(m["model_id"], prompt, images_b64)
                elif prov == "openai":
                    result = self._openai_vision(m["model_id"], prompt, images_b64)
                elif prov == "ollama":
                    result = self._ollama_vision(m["model_id"], prompt, images_b64)
                else:
                    continue

                elapsed = time.time() - t0
                self._record_success(key, elapsed)
                print(f"  ✓ {elapsed:.1f}s", flush=True)
                return result

            except Exception as e:
                # Do not immediately abort on quota, try next model
                # if "429" in str(e) or "quota" in str(e).lower():
                #     raise RateLimitError("Quota limit hit")
                status = 429 if "429" in str(e) else 0
                self._record_failure(key, str(e), status_code=status)
                print(f"  ✗ Failed ({type(e).__name__}), trying next …", flush=True)

        raise RuntimeError("All vision models failed.")

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate a text embedding via OpenAI's text-embedding-3-small.
        Used for semantic search / similarity over analyzed posts.
        Returns None (not an exception) if no OpenAI key is configured or
        the call fails — embeddings are a nice-to-have, not required for a
        post to be considered successfully analyzed.
        """
        api_key = self._key("OPENAI_API_KEY")
        if not api_key or not text.strip():
            return None
        import requests
        try:
            resp = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": "text-embedding-3-small", "input": text[:8000]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception as e:
            print(f"  ⚠️  Embedding generation failed: {e}", flush=True)
            return None

    # ── OpenAI Batch API (ANALYSIS_MODE=batch) ───────────────────────────────────
    # Batch mode is OpenAI-only by construction — no other configured provider
    # (Groq/Gemini/OpenRouter/Ollama) has an equivalent async batch endpoint —
    # so, like generate_importance_text() above, these bypass _ranked_models()
    # entirely rather than trying to generalize across providers that don't
    # support this. One JSONL line per submission (one shortcode's request),
    # not accumulated multi-item batches — simpler, and OpenAI's ~50% batch
    # discount applies per-request regardless of how many requests share a job.

    def build_batch_chat_request(self, custom_id: str, prompt: str, model_id: str = OPENAI_TEXT_MODEL) -> Dict:
        """One /v1/chat/completions batch request line, body mirrors _openai_text()."""
        return {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                **self._openai_chat_params(model_id),
            },
        }

    def build_batch_embedding_request(self, custom_id: str, text: str,
                                       model_id: str = "text-embedding-3-small") -> Dict:
        """One /v1/embeddings batch request line, body mirrors generate_embedding()."""
        return {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/embeddings",
            "body": {"model": model_id, "input": text[:8000]},
        }

    def submit_openai_batch(self, requests_list: List[Dict], endpoint: str) -> str:
        """
        Upload `requests_list` (each built by build_batch_chat_request /
        build_batch_embedding_request) as a JSONL file and submit it as an
        OpenAI Batch API job targeting `endpoint` (exactly one of
        "/v1/chat/completions" or "/v1/embeddings" — a batch job is
        single-endpoint, mixed request types must be submitted separately).
        Returns the batch id. Raises RuntimeError on failure — batch mode has
        no fallback provider to try next.
        """
        import requests
        api_key = self._key("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured — batch mode requires OpenAI.")

        jsonl_body = "\n".join(json.dumps(r) for r in requests_list).encode("utf-8")
        file_resp = requests.post(
            "https://api.openai.com/v1/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("batch_input.jsonl", jsonl_body, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=60,
        )
        file_resp.raise_for_status()
        input_file_id = file_resp.json()["id"]

        batch_resp = requests.post(
            "https://api.openai.com/v1/batches",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input_file_id": input_file_id,
                "endpoint": endpoint,
                "completion_window": "24h",
            },
            timeout=30,
        )
        batch_resp.raise_for_status()
        return batch_resp.json()["id"]

    def get_batch_status(self, batch_id: str) -> Dict:
        """GET /v1/batches/{id} — raw response so callers branch on `status`
        themselves (validating|in_progress|finalizing|completed|failed|expired|cancelled)."""
        import requests
        resp = requests.get(
            f"https://api.openai.com/v1/batches/{batch_id}",
            headers={"Authorization": f"Bearer {self._key('OPENAI_API_KEY')}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_batch_results(self, batch_id: str) -> List[Dict]:
        """
        For a batch whose status is terminal, fetch and parse its output file
        (successful requests) and, if present, its error file (per-request
        failures within an otherwise-completed batch). Returns the raw parsed
        JSONL rows — each {"custom_id": ..., "response": {...}} or
        {"custom_id": ..., "error": {...}}. Callers extract endpoint-specific
        content via extract_batch_chat_text()/extract_batch_embedding().
        """
        import requests
        api_key = self._key("OPENAI_API_KEY")
        status = self.get_batch_status(batch_id)
        rows: List[Dict] = []
        for file_field in ("output_file_id", "error_file_id"):
            file_id = status.get(file_field)
            if not file_id:
                continue
            resp = requests.get(
                f"https://api.openai.com/v1/files/{file_id}/content",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60,
            )
            resp.raise_for_status()
            for line in resp.text.strip().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def extract_batch_chat_text(self, result_row: Dict) -> Optional[str]:
        """Pull the chat-completion content out of one get_batch_results() row, or None on error."""
        try:
            return result_row["response"]["body"]["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return None

    def extract_batch_embedding(self, result_row: Dict) -> Optional[List[float]]:
        """Pull the embedding vector out of one get_batch_results() row, or None on error."""
        try:
            return result_row["response"]["body"]["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError):
            return None

    # ── Utilities ──────────────────────────────────────────────────────────────

    def print_rankings(self):
        """Print a full ranked table of all models with performance stats (static + dynamic)."""
        print("\n" + "=" * 80)
        print("🏆  AI MODEL RANKINGS  (auto-sorted by speed + reliability)")
        print("=" * 80)
        for task_type in ("text", "vision"):
            print(f"\n{'─' * 80}")
            print(f"  {task_type.upper()} MODELS  (rank 1 = currently preferred)")
            print(f"{'─' * 80}")
            static_keys = [k for k, m in MODELS_BY_KEY.items() if m["type"] == task_type]
            dyn_keys    = [k for k, m in self._dynamic_models.items() if m["type"] == task_type]
            all_keys    = static_keys + [k for k in dyn_keys if k not in MODELS_BY_KEY]
            sorted_keys = sorted(all_keys, key=self._effective_priority)
            for i, key in enumerate(sorted_keys, 1):
                m = MODELS_BY_KEY.get(key) or self._dynamic_models.get(key)
                if not m:
                    continue
                s     = self._state.get(key, self._default_model_state_dynamic(key))
                avail = "✓ UP  " if self._is_available(key) else "✗ DOWN"
                avg_t = s["avg_response_s"]
                avg_str = f"{avg_t:5.1f}s" if avg_t is not None else "  new "
                n_ok  = s.get("success_count", 0)
                n_err = s.get("fail_count", 0)
                tag   = "[dyn]" if key.startswith("dyn_") else "     "
                print(
                    f"  {i:2}. [{avail}] {tag} "
                    f"{m['provider']:<12} "
                    f"{m['model_id']:<48} "
                    f"avg={avg_str}  ok={n_ok}  fail={n_err}"
                )
        dyn_count = len(self._dynamic_models)
        print(f"\n  ({dyn_count} additional free models discovered dynamically from OpenRouter)")
        print()

    def reset_model(self, model_key: str):
        """Manually clear the down-cooldown for a specific model key."""
        if model_key in self._state:
            with self._lock:
                self._state[model_key]["down_until"] = None
                self._state[model_key]["fail_count"] = 0
                self._save_state()
            print(f"✓ Reset model: {model_key}")
        else:
            print(f"Unknown model key: {model_key}")

    def refresh_models(self):
        """Force-refresh the OpenRouter free model list (ignores cache)."""
        # Remove stale cache so _refresh_openrouter_models fetches fresh data
        try:
            OPENROUTER_FREE_CACHE_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        self._refresh_openrouter_models()
        print(f"✓ Refreshed: {len(self._dynamic_models)} dynamic models loaded")

    def _print_startup_status(self):
        parts = []
        parts.append("Groq ✓"        if self._key("GROQ_API_KEY")        else "Groq ✗")
        parts.append("Gemini ✓"      if self._key("GEMINI_API_KEY")      else "Gemini ✗")
        parts.append("OpenRouter ✓"  if self._key("OPENROUTER_API_KEY")  else "OpenRouter ✗")
        parts.append("OpenAI ✓"      if self._key("OPENAI_API_KEY")      else "OpenAI ✗")
        parts.append("Ollama (fallback)")
        print(f"🌐 Model Router initialised: {' | '.join(parts)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton
# ─────────────────────────────────────────────────────────────────────────────

_router_instance: Optional[ModelRouter] = None
_router_lock = threading.Lock()


def get_router() -> ModelRouter:
    """Get or create the shared ModelRouter instance."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = ModelRouter()
    return _router_instance


# ─────────────────────────────────────────────────────────────────────────────
#  CLI — run this file directly to inspect rankings or reset a model
#  Usage:
#    python model_router.py                  → show rankings
#    python model_router.py reset <key>      → clear cooldown for model key
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    router = get_router()
    import time as _time; _time.sleep(1)  # give background thread a moment
    if len(_sys.argv) >= 3 and _sys.argv[1] == "reset":
        router.reset_model(_sys.argv[2])
    elif len(_sys.argv) >= 2 and _sys.argv[1] == "refresh":
        router.refresh_models()
    else:
        router.print_rankings()


