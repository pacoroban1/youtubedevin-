"""
Multi-Language Engine
Auto-translate and dub content to 21+ languages with RPM optimization.
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import httpx


class MultiLanguageEngine:
    """
    Translates and dubs content to multiple languages.
    
    Features:
    - 21+ language support
    - RPM-optimized language targeting
    - Voice cloning per language
    - Automatic subtitle generation
    - Batch processing
    """
    
    # Language configurations with RPM estimates (based on industry data)
    LANGUAGES = {
        "en": {"name": "English", "rpm": 7.0, "voice": "en-US", "priority": 1},
        "de": {"name": "German", "rpm": 5.5, "voice": "de-DE", "priority": 2},
        "pl": {"name": "Polish", "rpm": 4.5, "voice": "pl-PL", "priority": 3},
        "fr": {"name": "French", "rpm": 4.0, "voice": "fr-FR", "priority": 4},
        "es": {"name": "Spanish", "rpm": 1.5, "voice": "es-ES", "priority": 5},
        "it": {"name": "Italian", "rpm": 3.5, "voice": "it-IT", "priority": 6},
        "pt": {"name": "Portuguese", "rpm": 2.0, "voice": "pt-BR", "priority": 7},
        "nl": {"name": "Dutch", "rpm": 4.0, "voice": "nl-NL", "priority": 8},
        "ru": {"name": "Russian", "rpm": 2.5, "voice": "ru-RU", "priority": 9},
        "uk": {"name": "Ukrainian", "rpm": 2.0, "voice": "uk-UA", "priority": 10},
        "hi": {"name": "Hindi", "rpm": 1.0, "voice": "hi-IN", "priority": 11},
        "id": {"name": "Indonesian", "rpm": 1.5, "voice": "id-ID", "priority": 12},
        "vi": {"name": "Vietnamese", "rpm": 1.2, "voice": "vi-VN", "priority": 13},
        "th": {"name": "Thai", "rpm": 1.5, "voice": "th-TH", "priority": 14},
        "tr": {"name": "Turkish", "rpm": 1.8, "voice": "tr-TR", "priority": 15},
        "ar": {"name": "Arabic", "rpm": 2.0, "voice": "ar-SA", "priority": 16},
        "ja": {"name": "Japanese", "rpm": 3.5, "voice": "ja-JP", "priority": 17},
        "ko": {"name": "Korean", "rpm": 3.0, "voice": "ko-KR", "priority": 18},
        "zh": {"name": "Chinese", "rpm": 2.5, "voice": "zh-CN", "priority": 19},
        "am": {"name": "Amharic", "rpm": 1.5, "voice": "am-ET", "priority": 20},
        "sv": {"name": "Swedish", "rpm": 4.5, "voice": "sv-SE", "priority": 21},
    }
    
    def __init__(self, db):
        self.db = db
        self.output_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.translations_dir = os.path.join(self.output_dir, "translations")
        os.makedirs(self.translations_dir, exist_ok=True)
        
        # API clients
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        self.azure_key = os.getenv("AZURE_SPEECH_KEY")
        self.azure_region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        
        # Cost tracking
        self.translation_cost_per_1k = 0.02  # GPT-4 translation
        self.tts_cost_per_char = 0.00003  # ElevenLabs
        
    def get_high_rpm_languages(self, min_rpm: float = 3.0) -> List[str]:
        """Get languages with RPM above threshold."""
        return [
            code for code, config in self.LANGUAGES.items()
            if config["rpm"] >= min_rpm
        ]
        
    def get_languages_by_priority(self, limit: int = 10) -> List[str]:
        """Get top languages by priority."""
        sorted_langs = sorted(
            self.LANGUAGES.items(),
            key=lambda x: x[1]["priority"]
        )
        return [code for code, _ in sorted_langs[:limit]]
        
    async def translate_script(
        self,
        script: str,
        source_lang: str,
        target_lang: str,
        style: str = "conversational"
    ) -> str:
        """
        Translate script to target language.
        
        Args:
            script: Original script text
            source_lang: Source language code
            target_lang: Target language code
            style: Translation style (conversational, formal, casual)
            
        Returns:
            Translated script
        """
        if not self.openai_key:
            raise ValueError("OpenAI API key required for translation")
            
        target_name = self.LANGUAGES.get(target_lang, {}).get("name", target_lang)
        source_name = self.LANGUAGES.get(source_lang, {}).get("name", source_lang)
        
        prompt = f"""Translate the following {source_name} script to {target_name}.

Style: {style}
- Keep the same tone and energy
- Adapt cultural references for {target_name} audience
- Maintain timing cues if present
- Keep it natural and engaging

Script:
{script}

Translated script:"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.openai_key}"},
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
                timeout=60.0
            )
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
    async def generate_voice(
        self,
        text: str,
        language: str,
        voice_id: Optional[str] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate voice audio for text.
        
        Args:
            text: Text to speak
            language: Language code
            voice_id: Optional specific voice ID
            output_path: Optional output file path
            
        Returns:
            Path to generated audio file
        """
        lang_config = self.LANGUAGES.get(language, {})
        
        # Try ElevenLabs first for supported languages
        if self.elevenlabs_key and language in ["en", "de", "es", "fr", "it", "pl", "pt"]:
            return await self._generate_elevenlabs(text, language, voice_id, output_path)
        
        # Fall back to Azure TTS
        if self.azure_key:
            return await self._generate_azure(text, language, output_path)
            
        raise ValueError("No TTS API configured")
        
    async def _generate_elevenlabs(
        self,
        text: str,
        language: str,
        voice_id: Optional[str],
        output_path: Optional[str]
    ) -> str:
        """Generate voice using ElevenLabs."""
        # Default voices per language
        default_voices = {
            "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel
            "de": "pNInz6obpgDQGcFmaJgB",  # Adam
            "es": "EXAVITQu4vr4xnSDxMaL",  # Bella
            "fr": "ThT5KcBeYPX3keUQqHPh",  # Dorothy
        }
        
        voice = voice_id or default_voices.get(language, "21m00Tcm4TlvDq8ikWAM")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key": self.elevenlabs_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                },
                timeout=120.0
            )
            
            if output_path is None:
                output_path = os.path.join(
                    self.translations_dir,
                    f"voice_{language}_{datetime.now().timestamp()}.mp3"
                )
                
            with open(output_path, "wb") as f:
                f.write(response.content)
                
            return output_path
            
    async def _generate_azure(
        self,
        text: str,
        language: str,
        output_path: Optional[str]
    ) -> str:
        """Generate voice using Azure TTS."""
        lang_config = self.LANGUAGES.get(language, {})
        voice_name = lang_config.get("voice", "en-US")
        
        # Azure voice names
        azure_voices = {
            "en-US": "en-US-JennyNeural",
            "de-DE": "de-DE-KatjaNeural",
            "es-ES": "es-ES-ElviraNeural",
            "fr-FR": "fr-FR-DeniseNeural",
            "it-IT": "it-IT-ElsaNeural",
            "pl-PL": "pl-PL-AgnieszkaNeural",
            "pt-BR": "pt-BR-FranciscaNeural",
            "nl-NL": "nl-NL-ColetteNeural",
            "ru-RU": "ru-RU-SvetlanaNeural",
            "am-ET": "am-ET-AmehaNeural",
            "ar-SA": "ar-SA-ZariyahNeural",
            "ja-JP": "ja-JP-NanamiNeural",
            "ko-KR": "ko-KR-SunHiNeural",
            "zh-CN": "zh-CN-XiaoxiaoNeural",
        }
        
        voice = azure_voices.get(voice_name, "en-US-JennyNeural")
        
        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{voice_name}'>
            <voice name='{voice}'>
                {text}
            </voice>
        </speak>
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://{self.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": self.azure_key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3"
                },
                content=ssml,
                timeout=120.0
            )
            
            if output_path is None:
                output_path = os.path.join(
                    self.translations_dir,
                    f"voice_{language}_{datetime.now().timestamp()}.mp3"
                )
                
            with open(output_path, "wb") as f:
                f.write(response.content)
                
            return output_path
            
    async def create_multilang_version(
        self,
        video_id: str,
        source_script: str,
        source_lang: str,
        target_langs: List[str],
        video_path: str
    ) -> List[Dict[str, Any]]:
        """
        Create multiple language versions of a video.
        
        Args:
            video_id: Original video ID
            source_script: Original script
            source_lang: Source language code
            target_langs: List of target language codes
            video_path: Path to source video
            
        Returns:
            List of created versions with paths
        """
        versions = []
        
        for lang in target_langs:
            if lang == source_lang:
                continue
                
            try:
                # Translate script
                translated = await self.translate_script(
                    source_script,
                    source_lang,
                    lang
                )
                
                # Generate voice
                audio_path = await self.generate_voice(translated, lang)
                
                # Create dubbed video
                output_video = os.path.join(
                    self.translations_dir,
                    f"{video_id}_{lang}.mp4"
                )
                
                await self._replace_audio(video_path, audio_path, output_video)
                
                # Generate subtitles
                subtitle_path = await self._generate_subtitles(
                    translated,
                    lang,
                    video_id
                )
                
                version = {
                    "video_id": video_id,
                    "language": lang,
                    "script": translated,
                    "audio_path": audio_path,
                    "video_path": output_video,
                    "subtitle_path": subtitle_path,
                    "rpm_estimate": self.LANGUAGES[lang]["rpm"],
                    "created_at": datetime.now().isoformat()
                }
                
                versions.append(version)
                
                # Save to database
                await self.db.execute("""
                    INSERT INTO video_translations 
                    (video_id, language, script, audio_path, video_path, subtitle_path, rpm_estimate)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, video_id, lang, translated, audio_path, output_video, 
                    subtitle_path, self.LANGUAGES[lang]["rpm"])
                    
            except Exception as e:
                print(f"Error creating {lang} version: {e}")
                continue
                
        return versions
        
    async def _replace_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str
    ):
        """Replace video audio with new audio track."""
        import subprocess
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
    async def _generate_subtitles(
        self,
        script: str,
        language: str,
        video_id: str
    ) -> str:
        """Generate SRT subtitles from script."""
        # Simple subtitle generation (in production, use forced alignment)
        lines = script.split('\n')
        srt_content = ""
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
                
            start_time = i * 3  # 3 seconds per line (simplified)
            end_time = start_time + 3
            
            srt_content += f"{i+1}\n"
            srt_content += f"{self._format_srt_time(start_time)} --> {self._format_srt_time(end_time)}\n"
            srt_content += f"{line.strip()}\n\n"
            
        output_path = os.path.join(
            self.translations_dir,
            f"{video_id}_{language}.srt"
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
            
        return output_path
        
    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT timestamp."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
    async def estimate_cost(
        self,
        script: str,
        target_langs: List[str]
    ) -> Dict[str, float]:
        """
        Estimate cost for multi-language production.
        
        Returns:
            Cost breakdown by category
        """
        char_count = len(script)
        word_count = len(script.split())
        
        translation_cost = (word_count / 1000) * self.translation_cost_per_1k * len(target_langs)
        tts_cost = char_count * self.tts_cost_per_char * len(target_langs)
        
        return {
            "translation": round(translation_cost, 2),
            "tts": round(tts_cost, 2),
            "total": round(translation_cost + tts_cost, 2),
            "per_language": round((translation_cost + tts_cost) / len(target_langs), 2)
        }
        
    async def get_revenue_projection(
        self,
        views_estimate: int,
        languages: List[str]
    ) -> Dict[str, Any]:
        """
        Project revenue across languages.
        
        Args:
            views_estimate: Estimated views per video
            languages: List of language codes
            
        Returns:
            Revenue projection by language
        """
        projections = {}
        total_revenue = 0
        
        for lang in languages:
            config = self.LANGUAGES.get(lang, {"rpm": 1.0})
            rpm = config["rpm"]
            revenue = (views_estimate / 1000) * rpm
            
            projections[lang] = {
                "rpm": rpm,
                "views": views_estimate,
                "revenue": round(revenue, 2)
            }
            total_revenue += revenue
            
        return {
            "by_language": projections,
            "total_revenue": round(total_revenue, 2),
            "avg_rpm": round(total_revenue / views_estimate * 1000, 2) if views_estimate > 0 else 0
        }
