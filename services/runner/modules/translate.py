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


class LibreTranslate:
    """
    LibreTranslate (open-source) client.

    This is intentionally light: it supports pointing at a self-hosted
    LibreTranslate instance on your LAN/VPS, so you can avoid paid APIs.

    Env:
      - LIBRETRANSLATE_URL (preferred), e.g. http://localhost:5000 or http://libretranslate:5000
      - LIBRETRANSLATE_API_KEY (optional)
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout_s: float = 30.0):
        self.base_url = (base_url or os.getenv("LIBRETRANSLATE_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("LIBRETRANSLATE_API_KEY")
        self.timeout_s = timeout_s

    def configured(self) -> bool:
        return bool(self.base_url)

    async def translate_batch(
        self,
        texts: List[str],
        target: str,
        source: Optional[str] = None,
    ) -> List[TranslationResult]:
        if not self.base_url:
            raise RuntimeError("LibreTranslate not configured (missing LIBRETRANSLATE_URL)")
        if not texts:
            return []

        out: List[TranslationResult] = []
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for text in texts:
                payload = {
                    "q": text,
                    "target": target,
                    "format": "text",
                }
                if source:
                    payload["source"] = source
                if self.api_key:
                    payload["api_key"] = self.api_key

                resp = await client.post(f"{self.base_url}/translate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                translated = html.unescape((data.get("translatedText") or "").strip())
                out.append(TranslationResult(translated_text=translated, detected_source_language=None))
        return out
