"""
Translation utilities.

This repo supports a "Gemini-first" workflow. When you want deterministic
translation as a separate step, you can use Google Cloud Translation API.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import List, Optional

import httpx


TRANSLATE_V2_URL = "https://translation.googleapis.com/language/translate/v2"


@dataclass
class TranslationResult:
    translated_text: str
    detected_source_language: Optional[str] = None


class GoogleTranslateV2:
    """
    Minimal Google Cloud Translation API (v2) client using an API key.

    Env:
      - GOOGLE_CLOUD_API_KEY (preferred)
      - GOOGLE_API_KEY (alias)
    """

    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 30.0):
        self.api_key = api_key or os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.timeout_s = timeout_s

    def configured(self) -> bool:
        return bool(self.api_key)

    async def translate_batch(
        self,
        texts: List[str],
        target: str,
        source: Optional[str] = None,
    ) -> List[TranslationResult]:
        if not self.api_key:
            raise RuntimeError("GoogleTranslateV2 not configured (missing GOOGLE_CLOUD_API_KEY/GOOGLE_API_KEY)")
        if not texts:
            return []

        # API allows multiple q=... entries; httpx will serialize list values as repeated keys.
        payload = {
            "q": texts,
            "target": target,
            "format": "text",
        }
        if source:
            payload["source"] = source

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(TRANSLATE_V2_URL, params={"key": self.api_key}, json=payload)
            resp.raise_for_status()
            data = resp.json()

        translations = (data.get("data") or {}).get("translations") or []
        out: List[TranslationResult] = []
        for t in translations:
            # API may return HTML-escaped entities.
            translated = html.unescape((t.get("translatedText") or "").strip())
            detected = t.get("detectedSourceLanguage")
            out.append(TranslationResult(translated_text=translated, detected_source_language=detected))
        return out

