"""
pipeline/core/utils.py

Shared utility functions for the research pipeline.
"""

from __future__ import annotations


def extract_json(raw: str) -> str:
    """Extract a JSON object from a raw LLM response.

    Handles common Gemini/LLM response formats:
    1. ```json\\n{...}\\n```   - markdown fence with language tag
    2. ```\\n{...}\\n```       - plain markdown fence
    3. {...}                  - bare JSON, possibly surrounded by prose
    """
    text = raw.strip()

    # Case 1 & 2: strip any markdown code fence
    if text.startswith("```"):
        # Remove opening fence line (e.g. "```json" or "```")
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Remove closing fence
        last_fence = text.rfind("```")
        if last_fence != -1:
            text = text[:last_fence]
        return text.strip()

    # Case 3: find the outermost {...} block in free-form prose
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # Post-processing: basic "repair" for common LLM JSON mistakes.
    # LLMs (especially older or smaller ones) often use single quotes for keys/values.
    # json.loads() requires double quotes.
    # import re

    # # Try to replace single quotes with double quotes for keys: 'key' -> "key"
    # # and values: 'value' -> "value", but be careful with apostrophes in text.
    # # This regex looks for single quotes that appear to be delimiters.
    # text = re.sub(r"\'(\w+)\'\s*:", r'"\1":', text)  # keys
    # text = re.sub(r":\s*\'(.*?)\'(\s*[,}])", r': "\1"\2', text)  # values (string)

    return text
