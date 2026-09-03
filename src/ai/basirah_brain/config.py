"""Basirah Brain's own model-provider configuration -- deliberately
separate from `src.analysis.analyst.config` (the narration-only LLM
config), since Stage 1's provider selection is an independent product
decision, not tied to the analyst-report rephrasing feature.

Low temperature / no creative sampling by design (financial analysis
needs reproducibility, not creative variance) -- see module docstring
of `providers/openai_provider.py` for how `seed` is used when the
underlying model supports it.
"""

import os


def get_basirah_brain_model_name() -> str:
    return os.getenv("BASIRAH_BRAIN_MODEL_NAME", "gpt-4o-mini")


def get_basirah_brain_timeout_seconds() -> float:
    return float(os.getenv("BASIRAH_BRAIN_TIMEOUT_SECONDS", "30"))


def get_basirah_brain_temperature() -> float:
    return float(os.getenv("BASIRAH_BRAIN_TEMPERATURE", "0.1"))


def get_basirah_brain_seed() -> int:
    return int(os.getenv("BASIRAH_BRAIN_SEED", "7"))


def get_basirah_brain_max_output_tokens() -> int:
    return int(os.getenv("BASIRAH_BRAIN_MAX_OUTPUT_TOKENS", "1500"))
