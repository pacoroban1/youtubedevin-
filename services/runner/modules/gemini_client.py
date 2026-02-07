import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Tuple

from google import genai
from google.genai import types

logger = logging.getLogger("gemini_client")
logger.setLevel(logging.INFO)


def _sanitize_message(msg: str, *, max_len: int = 300) -> str:
    if not msg:
        return ""
    s = str(msg).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # Redact common Google API key pattern if it ever appears in an error.
    s = re.sub(r"AIza[0-9A-Za-z\\-_]{10,}", "[REDACTED]", s)
    return s[:max_len]

def _maybe_b64decode_media(data: bytes) -> bytes:
    """
    Some SDK responses return base64-encoded bytes instead of raw bytes.
    Detect common PNG/JPEG base64 prefixes and decode.
    """
    if not data:
        return data
    # Base64 for PNG header: iVBORw0KGgo...
    if data.startswith(b"iVBORw0KGgo"):
        try:
            return base64.b64decode(data)
        except Exception:
            return data
    # Base64 for JPEG header: /9j/
    if data.startswith(b"/9j/"):
        try:
            return base64.b64decode(data)
        except Exception:
            return data
    return data


def _extract_status_code(exc: Exception) -> Optional[int]:
    # Try the common places Google libraries stash status codes.
    for attr in ("status_code", "code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
        if callable(v):
            try:
                vv = v()
                if isinstance(vv, int):
                    return vv
            except Exception:
                pass

    resp = getattr(exc, "response", None)
    if resp is not None:
        sc = getattr(resp, "status_code", None)
        if isinstance(sc, int):
            return sc

    return None


@dataclass(frozen=True)
class GeminiAttempt:
    model: str
    operation: str
    code: Optional[int]
    message_sanitized: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "operation": self.operation,
            "code": self.code,
            "message_sanitized": self.message_sanitized,
        }


class GeminiNotConfigured(RuntimeError):
    def __init__(self, env_var: str = "GEMINI_API_KEY"):
        super().__init__(f"{env_var} missing")
        self.env_var = env_var


class GeminiCallFailed(RuntimeError):
    def __init__(self, operation: str, attempts: List[GeminiAttempt]):
        super().__init__(f"{operation} failed after {len(attempts)} attempts")
        self.operation = operation
        self.attempts = attempts

    def attempts_as_dicts(self) -> List[Dict[str, Any]]:
        return [a.as_dict() for a in self.attempts]


class GeminiClient:
    """
    Thin wrapper around the google-genai SDK that enforces:
    - API key from env only
    - hard timeouts (via HttpOptions)
    - retries with backoff
    - structured attempt reporting for JSON error responses
    """

    # Hard requirements
    TEXT_MODEL = "gemini-2.0-flash"
    TTS_MODELS = [
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    ]
    IMAGE_MODELS = [
        "imagen-4.0-fast-generate-001",
        "imagen-4.0-generate-001",
        "gemini-2.0-flash-exp-image-generation",
        "imagen-4.0-ultra-generate-001",
    ]

    def __init__(self):
        # Cache clients by (api_key, timeout) to avoid rebuilding for each call.
        self._clients: Dict[Tuple[str, float], genai.Client] = {}

    def is_configured(self) -> bool:
        return bool((os.getenv("GEMINI_API_KEY") or "").strip())

    def _api_key(self) -> str:
        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            raise GeminiNotConfigured("GEMINI_API_KEY")
        return key

    def _client(self, *, timeout_s: float) -> genai.Client:
        api_key = self._api_key()
        cache_key = (api_key, float(timeout_s))
        if cache_key in self._clients:
            return self._clients[cache_key]

        # google-genai supports passing HttpOptions(timeout=...).
        # Empirically, the SDK treats this as milliseconds (passing 90.0 resulted in ~0.09s timeouts),
        # so we convert seconds -> ms.
        try:
            timeout_ms = int(float(timeout_s) * 1000)
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))
        except TypeError:
            # Fallback for older SDKs: still better than crashing; callers also retry.
            client = genai.Client(api_key=api_key)

        self._clients[cache_key] = client
        return client

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = 90.0,
        retries: int = 2,
        temperature: float = 0.7,
    ) -> str:
        target_model = model or self.TEXT_MODEL
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )

        attempts: List[GeminiAttempt] = []
        for i in range(retries + 1):
            try:
                client = self._client(timeout_s=timeout_s)
                resp = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config,
                )
                text = getattr(resp, "text", None)
                if not text or not str(text).strip():
                    raise RuntimeError("empty_text_response")
                return str(text)
            except Exception as e:
                attempts.append(
                    GeminiAttempt(
                        model=target_model,
                        operation="generate_text",
                        code=_extract_status_code(e),
                        message_sanitized=_sanitize_message(e),
                    )
                )
                if i >= retries:
                    raise GeminiCallFailed("generate_text", attempts) from e
                time.sleep(2 ** i)

        raise GeminiCallFailed("generate_text", attempts)

    def generate_json(
        self,
        prompt: str,
        response_schema: Any = None,  # kept for backward compatibility; we validate downstream
        *,
        system_instruction: Optional[str] = None,
        timeout_s: float = 90.0,
        retries: int = 2,
        temperature: float = 0.2,
    ) -> Any:
        del response_schema

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=temperature,
        )

        attempts: List[GeminiAttempt] = []
        for i in range(retries + 1):
            try:
                client = self._client(timeout_s=timeout_s)
                resp = client.models.generate_content(
                    model=self.TEXT_MODEL,
                    contents=prompt,
                    config=config,
                )
                text = (getattr(resp, "text", None) or "").strip()
                if not text:
                    raise RuntimeError("empty_json_response")

                # Strip markdown fences if present.
                if text.startswith("```"):
                    text = re.sub(r"^```[a-zA-Z0-9]*", "", text).strip()
                if text.endswith("```"):
                    text = text[:-3].strip()

                return json.loads(text)
            except Exception as e:
                attempts.append(
                    GeminiAttempt(
                        model=self.TEXT_MODEL,
                        operation="generate_json",
                        code=_extract_status_code(e),
                        message_sanitized=_sanitize_message(e),
                    )
                )
                if i >= retries:
                    raise GeminiCallFailed("generate_json", attempts) from e
                time.sleep(2 ** i)

        raise GeminiCallFailed("generate_json", attempts)

    def generate_images_with_fallback(
        self,
        prompt: str,
        *,
        number_of_images: int = 4,
        aspect_ratio: str = "16:9",
        timeout_s: float = 60.0,
        retries_per_model: int = 2,
        models: Optional[List[str]] = None,
    ) -> Tuple[List[bytes], str, List[Dict[str, Any]]]:
        models_to_try = models or list(self.IMAGE_MODELS)
        attempts: List[GeminiAttempt] = []

        for model_name in models_to_try:
            cfg = types.GenerateImagesConfig(
                number_of_images=number_of_images,
                aspect_ratio=aspect_ratio,
                # Some Imagen tiers/models reject stricter settings; this is the most compatible.
                safety_filter_level="block_low_and_above",
            )
            for i in range(retries_per_model + 1):
                try:
                    client = self._client(timeout_s=timeout_s)
                    resp = client.models.generate_images(
                        model=model_name,
                        prompt=prompt,
                        config=cfg,
                    )
                    generated = getattr(resp, "generated_images", None) or []
                    if not generated:
                        raise RuntimeError("no_images_returned")

                    out: List[bytes] = []
                    for gi in generated:
                        img_obj = getattr(gi, "image", None)
                        b = None
                        if img_obj is not None:
                            b = getattr(img_obj, "image_bytes", None)
                        if isinstance(b, str) and b:
                            try:
                                out.append(base64.b64decode(b))
                            except Exception:
                                # As a fallback, write the raw bytes of the string.
                                out.append(b.encode("utf-8"))
                        elif isinstance(b, (bytes, bytearray)) and b:
                            out.append(_maybe_b64decode_media(bytes(b)))

                    if not out:
                        raise RuntimeError("no_image_bytes")

                    return out, model_name, [a.as_dict() for a in attempts]
                except Exception as e:
                    attempts.append(
                        GeminiAttempt(
                            model=model_name,
                            operation="generate_images",
                            code=_extract_status_code(e),
                            message_sanitized=_sanitize_message(e),
                        )
                    )
                    if i >= retries_per_model:
                        break
                    time.sleep(2 ** i)

        raise GeminiCallFailed("generate_images", attempts)

    def generate_image(self, prompt: str, output_path: str) -> Optional[str]:
        """
        Backward-compatible helper: generate 1 image and write it to output_path.
        Returns output_path on success; None on failure.
        """
        try:
            images, _, _attempts = self.generate_images_with_fallback(
                prompt,
                number_of_images=1,
                timeout_s=60.0,
                retries_per_model=2,
            )
            with open(output_path, "wb") as f:
                f.write(images[0])
            return output_path
        except Exception as e:
            logger.warning("generate_image failed: %s", _sanitize_message(e))
            return None

    def generate_speech_with_fallback(
        self,
        text: str,
        *,
        voice_name: str = "Puck",
        timeout_s: float = 60.0,
        retries_per_model: int = 2,
        models: Optional[List[str]] = None,
    ) -> Tuple[bytes, str, List[Dict[str, Any]]]:
        models_to_try = models or list(self.TTS_MODELS)
        attempts: List[GeminiAttempt] = []

        cfg = types.GenerateContentConfig(
            # Some tiers reject response_mime_type for audio. Request audio modality only.
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
        )

        for model_name in models_to_try:
            for i in range(retries_per_model + 1):
                try:
                    client = self._client(timeout_s=timeout_s)
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=text,
                        config=cfg,
                    )

                    audio_bytes = self._extract_audio_bytes(resp)
                    if not audio_bytes:
                        raise RuntimeError("no_audio_bytes")

                    return audio_bytes, model_name, [a.as_dict() for a in attempts]
                except Exception as e:
                    attempts.append(
                        GeminiAttempt(
                            model=model_name,
                            operation="generate_speech",
                            code=_extract_status_code(e),
                            message_sanitized=_sanitize_message(e),
                        )
                    )
                    if i >= retries_per_model:
                        break
                    time.sleep(2 ** i)

        raise GeminiCallFailed("generate_speech", attempts)

    def generate_speech(self, text: str, output_path: str, voice_name: str = "Puck") -> Optional[str]:
        """
        Backward-compatible helper: generate speech and write it to output_path.
        Returns output_path on success; None on failure.
        """
        try:
            audio_bytes, _model_used, _attempts = self.generate_speech_with_fallback(
                text,
                voice_name=voice_name,
                timeout_s=60.0,
                retries_per_model=2,
            )
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            return output_path
        except Exception as e:
            logger.error("generate_speech failed: %s", _sanitize_message(e))
            return None

    def _extract_audio_bytes(self, resp: Any) -> Optional[bytes]:
        # google-genai: candidates[0].content.parts[*].inline_data.data is typically bytes or base64.
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if not data:
                    continue
                if isinstance(data, bytes):
                    return data
                if isinstance(data, str):
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        continue

        # Older/alt shape: resp.parts[*].inline_data.data
        parts = getattr(resp, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if not data:
                continue
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                try:
                    return base64.b64decode(data)
                except Exception:
                    continue

        return None


gemini = GeminiClient()
