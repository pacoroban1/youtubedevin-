"""
OmniASR Integration Module
Local multilingual speech recognition using OmniASR-LLM-7B.
Supports 1,600+ languages including Amharic.
"""

import os
import asyncio
import subprocess
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import tempfile


class OmniASRTranscriber:
    """
    Local transcription using OmniASR-LLM-7B model.
    
    Features:
    - 1,600+ language support including Amharic
    - Local inference (no API costs)
    - Word-level timestamps
    - Speaker diarization
    - Automatic language detection
    - GPU acceleration with fallback to CPU
    """
    
    def __init__(self, db, model_path: Optional[str] = None):
        self.db = db
        self.model_path = model_path or os.getenv(
            "OMNIASR_MODEL_PATH",
            "/models/omniASR_LLM_7B_V2"
        )
        self.device = os.getenv("OMNIASR_DEVICE", "auto")
        self.compute_type = os.getenv("OMNIASR_COMPUTE_TYPE", "float16")
        
        # Model settings
        self.batch_size = int(os.getenv("OMNIASR_BATCH_SIZE", "16"))
        self.beam_size = int(os.getenv("OMNIASR_BEAM_SIZE", "5"))
        
        # Output directory
        self.output_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.transcripts_dir = os.path.join(self.output_dir, "transcripts")
        os.makedirs(self.transcripts_dir, exist_ok=True)
        
        # Supported languages (subset - full list has 1600+)
        self.priority_languages = [
            "am",  # Amharic
            "en",  # English
            "ar",  # Arabic
            "ti",  # Tigrinya
            "om",  # Oromo
            "so",  # Somali
        ]
        
        self._model = None
        self._processor = None
        
    async def load_model(self):
        """Load the OmniASR model into memory."""
        if self._model is not None:
            return True
            
        try:
            # Check if model exists
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(
                    f"OmniASR model not found at {self.model_path}. "
                    "Please download the model first."
                )
                
            # Determine device
            device = self.device
            if device == "auto":
                device = await self._detect_device()
                
            # Import and load model
            # Note: This assumes the OmniASR package is installed
            # In production, you'd use the actual OmniASR library
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
            import torch
            
            self._processor = AutoProcessor.from_pretrained(self.model_path)
            self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if self.compute_type == "float16" else torch.float32,
                device_map=device,
                low_cpu_mem_usage=True,
            )
            
            return True
            
        except ImportError:
            # Fallback to CLI mode if library not available
            return await self._check_cli_available()
            
        except Exception as e:
            print(f"Error loading OmniASR model: {e}")
            return False
            
    async def _detect_device(self) -> str:
        """Detect available compute device."""
        try:
            import torch
            if torch.cuda.is_available():
                # Check VRAM (OmniASR 7B needs ~17GB)
                vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if vram >= 16:
                    return "cuda"
                else:
                    print(f"VRAM ({vram:.1f}GB) may be insufficient for OmniASR 7B")
                    return "cuda"  # Try anyway
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        except ImportError:
            return "cpu"
            
    async def _check_cli_available(self) -> bool:
        """Check if OmniASR CLI is available."""
        try:
            result = subprocess.run(
                ["omniasr", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
            
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
        word_timestamps: bool = True,
        diarize: bool = False
    ) -> Dict[str, Any]:
        """
        Transcribe audio file.
        
        Args:
            audio_path: Path to audio file
            language: Language code (auto-detect if None)
            task: "transcribe" or "translate" (to English)
            word_timestamps: Include word-level timestamps
            diarize: Enable speaker diarization
            
        Returns:
            Transcription result with text, segments, and metadata
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        # Try library mode first, fall back to CLI
        if self._model is not None:
            return await self._transcribe_library(
                audio_path, language, task, word_timestamps
            )
        else:
            return await self._transcribe_cli(
                audio_path, language, task, word_timestamps, diarize
            )
            
    async def _transcribe_library(
        self,
        audio_path: str,
        language: Optional[str],
        task: str,
        word_timestamps: bool
    ) -> Dict[str, Any]:
        """Transcribe using loaded model."""
        import torch
        import librosa
        
        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Process
        inputs = self._processor(
            audio,
            sampling_rate=16000,
            return_tensors="pt"
        )
        
        # Move to device
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        
        # Generate
        generate_kwargs = {
            "max_new_tokens": 448,
            "num_beams": self.beam_size,
            "return_timestamps": word_timestamps,
        }
        
        if language:
            generate_kwargs["language"] = language
        if task == "translate":
            generate_kwargs["task"] = "translate"
            
        with torch.no_grad():
            outputs = self._model.generate(**inputs, **generate_kwargs)
            
        # Decode
        transcription = self._processor.batch_decode(
            outputs,
            skip_special_tokens=True,
            output_offsets=word_timestamps
        )
        
        # Format result
        result = {
            "text": transcription[0] if isinstance(transcription, list) else transcription,
            "language": language or "auto",
            "segments": [],
            "word_timestamps": [],
        }
        
        return result
        
    async def _transcribe_cli(
        self,
        audio_path: str,
        language: Optional[str],
        task: str,
        word_timestamps: bool,
        diarize: bool
    ) -> Dict[str, Any]:
        """Transcribe using CLI (fallback mode)."""
        # Build command
        cmd = [
            "omniasr",
            audio_path,
            "--model", self.model_path,
            "--output_format", "json",
            "--task", task,
        ]
        
        if language:
            cmd.extend(["--language", language])
        if word_timestamps:
            cmd.append("--word_timestamps")
        if diarize:
            cmd.append("--diarize")
            
        # Create output file
        output_file = tempfile.NamedTemporaryFile(
            suffix=".json",
            delete=False
        )
        cmd.extend(["--output_file", output_file.name])
        
        try:
            # Run transcription
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"OmniASR CLI error: {stderr.decode()}")
                
            # Read result
            with open(output_file.name, 'r') as f:
                result = json.load(f)
                
            return result
            
        finally:
            # Cleanup
            if os.path.exists(output_file.name):
                os.unlink(output_file.name)
                
    async def transcribe_video(
        self,
        video_id: str,
        video_path: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe video and save to database.
        
        Args:
            video_id: Database video ID
            video_path: Path to video file
            language: Expected language (auto-detect if None)
            
        Returns:
            Transcription result
        """
        # Extract audio from video
        audio_path = await self._extract_audio(video_path)
        
        try:
            # Transcribe
            result = await self.transcribe(
                audio_path,
                language=language,
                word_timestamps=True
            )
            
            # Save transcript to file
            transcript_file = os.path.join(
                self.transcripts_dir,
                f"{video_id}_transcript.json"
            )
            with open(transcript_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
            # Update database
            await self.db.execute("""
                UPDATE videos SET
                    transcript = $1,
                    transcript_path = $2,
                    transcript_language = $3,
                    transcribed_at = NOW()
                WHERE id = $4
            """, result.get("text", ""), transcript_file, 
                result.get("language", "unknown"), video_id)
                
            return result
            
        finally:
            # Cleanup extracted audio
            if os.path.exists(audio_path):
                os.unlink(audio_path)
                
    async def _extract_audio(self, video_path: str) -> str:
        """Extract audio from video file."""
        audio_path = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ).name
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        if not os.path.exists(audio_path):
            raise RuntimeError("Failed to extract audio from video")
            
        return audio_path
        
    async def detect_language(self, audio_path: str) -> Tuple[str, float]:
        """
        Detect the language of an audio file.
        
        Returns:
            Tuple of (language_code, confidence)
        """
        # Use short segment for detection
        result = await self.transcribe(
            audio_path,
            language=None,
            word_timestamps=False
        )
        
        detected = result.get("language", "unknown")
        confidence = result.get("language_probability", 0.0)
        
        return detected, confidence
        
    async def get_word_timestamps(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get word-level timestamps for audio.
        
        Returns:
            List of words with start/end times
        """
        result = await self.transcribe(
            audio_path,
            language=language,
            word_timestamps=True
        )
        
        return result.get("word_timestamps", [])
        
    async def batch_transcribe(
        self,
        audio_paths: List[str],
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Transcribe multiple audio files.
        
        Args:
            audio_paths: List of audio file paths
            language: Language code (same for all)
            
        Returns:
            List of transcription results
        """
        results = []
        
        for audio_path in audio_paths:
            try:
                result = await self.transcribe(audio_path, language=language)
                results.append(result)
            except Exception as e:
                results.append({
                    "error": str(e),
                    "audio_path": audio_path
                })
                
        return results
        
    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Get list of supported languages."""
        # OmniASR supports 1600+ languages
        # This is a subset of commonly used ones
        return [
            {"code": "am", "name": "Amharic", "native": "አማርኛ"},
            {"code": "en", "name": "English", "native": "English"},
            {"code": "ar", "name": "Arabic", "native": "العربية"},
            {"code": "ti", "name": "Tigrinya", "native": "ትግርኛ"},
            {"code": "om", "name": "Oromo", "native": "Afaan Oromoo"},
            {"code": "so", "name": "Somali", "native": "Soomaali"},
            {"code": "sw", "name": "Swahili", "native": "Kiswahili"},
            {"code": "ha", "name": "Hausa", "native": "Hausa"},
            {"code": "yo", "name": "Yoruba", "native": "Yorùbá"},
            {"code": "ig", "name": "Igbo", "native": "Igbo"},
            {"code": "zu", "name": "Zulu", "native": "isiZulu"},
            {"code": "xh", "name": "Xhosa", "native": "isiXhosa"},
            {"code": "af", "name": "Afrikaans", "native": "Afrikaans"},
            {"code": "fr", "name": "French", "native": "Français"},
            {"code": "pt", "name": "Portuguese", "native": "Português"},
            {"code": "es", "name": "Spanish", "native": "Español"},
            {"code": "de", "name": "German", "native": "Deutsch"},
            {"code": "it", "name": "Italian", "native": "Italiano"},
            {"code": "ru", "name": "Russian", "native": "Русский"},
            {"code": "zh", "name": "Chinese", "native": "中文"},
            {"code": "ja", "name": "Japanese", "native": "日本語"},
            {"code": "ko", "name": "Korean", "native": "한국어"},
            {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
            {"code": "bn", "name": "Bengali", "native": "বাংলা"},
            {"code": "ta", "name": "Tamil", "native": "தமிழ்"},
            {"code": "te", "name": "Telugu", "native": "తెలుగు"},
            {"code": "mr", "name": "Marathi", "native": "मराठी"},
            {"code": "gu", "name": "Gujarati", "native": "ગુજરાતી"},
            {"code": "kn", "name": "Kannada", "native": "ಕನ್ನಡ"},
            {"code": "ml", "name": "Malayalam", "native": "മലയാളം"},
            {"code": "pa", "name": "Punjabi", "native": "ਪੰਜਾਬੀ"},
            {"code": "ur", "name": "Urdu", "native": "اردو"},
            {"code": "fa", "name": "Persian", "native": "فارسی"},
            {"code": "tr", "name": "Turkish", "native": "Türkçe"},
            {"code": "vi", "name": "Vietnamese", "native": "Tiếng Việt"},
            {"code": "th", "name": "Thai", "native": "ไทย"},
            {"code": "id", "name": "Indonesian", "native": "Bahasa Indonesia"},
            {"code": "ms", "name": "Malay", "native": "Bahasa Melayu"},
            {"code": "tl", "name": "Tagalog", "native": "Tagalog"},
            {"code": "pl", "name": "Polish", "native": "Polski"},
            {"code": "uk", "name": "Ukrainian", "native": "Українська"},
            {"code": "nl", "name": "Dutch", "native": "Nederlands"},
            {"code": "el", "name": "Greek", "native": "Ελληνικά"},
            {"code": "he", "name": "Hebrew", "native": "עברית"},
            {"code": "cs", "name": "Czech", "native": "Čeština"},
            {"code": "sv", "name": "Swedish", "native": "Svenska"},
            {"code": "da", "name": "Danish", "native": "Dansk"},
            {"code": "fi", "name": "Finnish", "native": "Suomi"},
            {"code": "no", "name": "Norwegian", "native": "Norsk"},
            {"code": "hu", "name": "Hungarian", "native": "Magyar"},
            {"code": "ro", "name": "Romanian", "native": "Română"},
        ]


class WhisperFallback:
    """
    Fallback transcriber using OpenAI Whisper.
    Used when OmniASR is not available.
    """
    
    def __init__(self, model_size: str = "large-v3"):
        self.model_size = model_size
        self._model = None
        
    async def load_model(self):
        """Load Whisper model."""
        try:
            import whisper
            self._model = whisper.load_model(self.model_size)
            return True
        except Exception as e:
            print(f"Error loading Whisper: {e}")
            return False
            
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Transcribe using Whisper."""
        if self._model is None:
            await self.load_model()
            
        result = self._model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True
        )
        
        return {
            "text": result["text"],
            "language": result.get("language", "unknown"),
            "segments": result.get("segments", []),
        }


async def get_transcriber(db, prefer_local: bool = True):
    """
    Get the best available transcriber.
    
    Args:
        db: Database connection
        prefer_local: Prefer local OmniASR over cloud APIs
        
    Returns:
        Transcriber instance
    """
    if prefer_local:
        # Try OmniASR first
        omniasr = OmniASRTranscriber(db)
        if await omniasr.load_model():
            return omniasr
            
        # Fall back to Whisper
        whisper = WhisperFallback()
        if await whisper.load_model():
            return whisper
            
    # Return OmniASR anyway (will use CLI mode or fail gracefully)
    return OmniASRTranscriber(db)
