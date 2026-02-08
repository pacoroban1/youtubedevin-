---
name: Voice_PersonaSelector
description: Audition narrator voices and lock a stable deep cinematic channel voice (prebuilt Gemini voices).
---

## When To Use
Use before running daily automation so every upload has the same narrator identity.

## Inputs
- Optional: `voice_name` override per run
- Env default: `GEMINI_TTS_VOICE_NAME`

## Preconditions
- `GEMINI_API_KEY` set
- Runner healthy

## Steps
1. List known voices: `GET /api/tts/voices`.
1. Preview a voice: `POST /api/tts_preview` with a short test line.
1. Pick one voice as the channel default and set `GEMINI_TTS_VOICE_NAME` in `.env`.
1. Restart runner stack (compose) to apply env changes.

## Acceptance Criteria
- You have a chosen voice name recorded (e.g., `Charon` or `Fenrir`).
- Preview audio is listenable and matches the vibe (deep, calm, cinematic).

## Verification
- `curl -fsS http://localhost:8000/api/tts/voices | python3 -m json.tool`
- `curl -fsS -X POST http://localhost:8000/api/tts_preview -H 'Content-Type: application/json' -d '{\"text\":\"Voice preview. Deep cinematic male narrator.\",\"voice_name\":\"Charon\"}' | python3 -m json.tool`

## Failure Modes And Fallbacks
- Voice sounds wrong: audition another prebuilt voice.
- TTS preview fails: check `GET /api/verify/voice` and quotas.

## Notes
- "Reference voice vibe" is OK; we just use generic prebuilt voices, not copying any specific person.

