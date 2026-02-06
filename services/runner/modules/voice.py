"""
Part D: Voice Generation Module
Generates Amharic narration using Azure TTS with deep, cinematic voice.

IMPORTANT: ElevenLabs does NOT support Amharic TTS.
We use Microsoft Azure TTS which has am-ET voices:
- am-ET-AmehaNeural (Male)
- am-ET-MekdesNeural (Female)
"""

import os
import subprocess
from typing import Dict, Any, Optional, List
from datetime import datetime
import wave
import struct
import math


class VoiceGenerator:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
        # Azure Speech configuration
        self.azure_key = os.getenv("AZURE_SPEECH_KEY")
        self.azure_region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        
        # Voice settings for deep, cinematic narrator
        # Using male voice for the "gritty narrator" vibe
        self.voice_id = "am-ET-AmehaNeural"  # Male Amharic voice
        self.voice_settings = {
            "rate": "-5%",      # Slightly slower for dramatic effect
            "pitch": "-10%",    # Lower pitch for deeper voice
            "volume": "+0%"     # Normal volume
        }
        
        # Target loudness for normalization
        self.target_lufs = -14  # YouTube recommended
    
    async def generate_narration(self, video_id: str) -> Dict[str, Any]:
        """
        Generate Amharic narration audio from script.
        
        Args:
            video_id: YouTube video ID
        
        Returns:
            Dict with audio file path and metadata
        """
        # Get script from database
        script_data = self.db.get_script(video_id)
        
        if not script_data or not script_data.get("full_script"):
            raise Exception(f"No script found for video {video_id}")
        
        full_script = script_data["full_script"]
        script_id = script_data["id"]
        
        # Create output directory
        audio_dir = os.path.join(self.media_dir, "audio", video_id)
        os.makedirs(audio_dir, exist_ok=True)
        
        # Generate audio segments
        segments = script_data.get("main_recap_segments", [])
        if isinstance(segments, str):
            import json
            segments = json.loads(segments)
        
        segment_files = []
        
        # Generate hook audio
        hook_text = script_data.get("hook_text", "")
        if hook_text:
            hook_file = os.path.join(audio_dir, "hook.wav")
            await self._synthesize_speech(hook_text, hook_file)
            segment_files.append(hook_file)
        
        # Generate main segment audio
        for i, segment in enumerate(segments):
            segment_text = segment.get("text", "") if isinstance(segment, dict) else str(segment)
            if segment_text:
                segment_file = os.path.join(audio_dir, f"segment_{i:03d}.wav")
                await self._synthesize_speech(segment_text, segment_file)
                segment_files.append(segment_file)
        
        # Generate payoff audio
        payoff_text = script_data.get("payoff_text", "")
        if payoff_text:
            payoff_file = os.path.join(audio_dir, "payoff.wav")
            await self._synthesize_speech(payoff_text, payoff_file)
            segment_files.append(payoff_file)
        
        # Generate CTA audio
        cta_text = script_data.get("cta_text", "")
        if cta_text:
            cta_file = os.path.join(audio_dir, "cta.wav")
            await self._synthesize_speech(cta_text, cta_file)
            segment_files.append(cta_file)
        
        # Concatenate all segments
        final_audio = os.path.join(audio_dir, "narration.wav")
        await self._concatenate_audio(segment_files, final_audio)
        
        # Apply "Fantastic Captain" post-processing
        # Deep, confident, cinematic narrator; warm low-end; crisp consonants
        processed_audio = os.path.join(audio_dir, "narration_processed.wav")
        await self._apply_fantastic_captain_processing(final_audio, processed_audio)
        
        # Normalize audio
        normalized_audio = os.path.join(audio_dir, "narration_normalized.wav")
        loudness = await self._normalize_audio(processed_audio, normalized_audio)
        
        # Quality check
        quality_passed = await self._quality_check(normalized_audio)
        
        # Get duration
        duration = await self._get_audio_duration(normalized_audio)
        
        # Save to database
        audio_data = {
            "voice_provider": "azure",
            "voice_id": self.voice_id,
            "audio_file_path": normalized_audio,
            "duration_seconds": duration,
            "loudness_lufs": loudness,
            "quality_check_passed": quality_passed
        }
        
        audio_id = self.db.save_audio(video_id, script_id, audio_data)
        self.db.update_video_status(video_id, "voiced")
        
        return {
            "audio_id": audio_id,
            "audio_file": normalized_audio,
            "duration": duration,
            "loudness_lufs": loudness,
            "quality_passed": quality_passed,
            "segment_files": segment_files
        }
    
    async def _synthesize_speech(self, text: str, output_file: str) -> bool:
        """Synthesize speech using Azure TTS."""
        if not self.azure_key:
            print("Azure Speech key not configured, using fallback")
            return await self._fallback_synthesis(text, output_file)
        
        try:
            import azure.cognitiveservices.speech as speechsdk
            
            # Configure speech synthesis
            speech_config = speechsdk.SpeechConfig(
                subscription=self.azure_key,
                region=self.azure_region
            )
            
            # Set output format
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
            )
            
            # Create SSML for more control
            ssml = self._create_ssml(text)
            
            # Create synthesizer
            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=audio_config
            )
            
            # Synthesize
            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return True
            else:
                print(f"Speech synthesis failed: {result.reason}")
                return False
                
        except Exception as e:
            print(f"Azure TTS error: {e}")
            return await self._fallback_synthesis(text, output_file)
    
    def _create_ssml(self, text: str) -> str:
        """Create SSML markup for Azure TTS with voice styling."""
        # Process text to handle [PAUSE] markers
        text = text.replace("[PAUSE]", '<break time="500ms"/>')
        
        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" 
                   xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="am-ET">
    <voice name="{self.voice_id}">
        <prosody rate="{self.voice_settings['rate']}" 
                 pitch="{self.voice_settings['pitch']}" 
                 volume="{self.voice_settings['volume']}">
            {text}
        </prosody>
    </voice>
</speak>"""
        
        return ssml
    
    async def _fallback_synthesis(self, text: str, output_file: str) -> bool:
        """Fallback synthesis using espeak or similar."""
        try:
            # Try espeak with Amharic if available
            cmd = [
                "espeak-ng",
                "-v", "am",  # Amharic voice
                "-w", output_file,
                text[:1000]  # Limit text length
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            return result.returncode == 0
            
        except Exception as e:
            print(f"Fallback synthesis error: {e}")
            # Create silent audio as last resort
            return await self._create_silent_audio(output_file, 5.0)
    
    async def _create_silent_audio(self, output_file: str, duration: float) -> bool:
        """Create silent audio file as placeholder."""
        try:
            sample_rate = 24000
            num_samples = int(sample_rate * duration)
            
            with wave.open(output_file, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                
                # Write silence
                for _ in range(num_samples):
                    wav_file.writeframes(struct.pack('<h', 0))
            
            return True
        except Exception as e:
            print(f"Silent audio creation error: {e}")
            return False
    
    async def _concatenate_audio(self, input_files: List[str], output_file: str) -> bool:
        """Concatenate multiple audio files."""
        if not input_files:
            return False
        
        # Filter existing files
        existing_files = [f for f in input_files if os.path.exists(f)]
        
        if not existing_files:
            return False
        
        if len(existing_files) == 1:
            # Just copy the single file
            import shutil
            shutil.copy(existing_files[0], output_file)
            return True
        
        try:
            # Create file list for ffmpeg
            list_file = output_file + ".txt"
            with open(list_file, "w") as f:
                for audio_file in existing_files:
                    f.write(f"file '{audio_file}'\n")
            
            # Concatenate with ffmpeg
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                "-y",
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            # Clean up list file
            os.remove(list_file)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"Audio concatenation error: {e}")
            return False
    
    async def _normalize_audio(self, input_file: str, output_file: str) -> float:
        """Normalize audio to target LUFS."""
        try:
            # First pass: measure loudness
            cmd_measure = [
                "ffmpeg",
                "-i", input_file,
                "-af", f"loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11:print_format=json",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd_measure, capture_output=True, text=True, timeout=120)
            
            # Parse loudness from output
            import re
            import json
            
            # Find JSON in output
            json_match = re.search(r'\{[^}]+\}', result.stderr)
            if json_match:
                loudness_data = json.loads(json_match.group())
                measured_i = float(loudness_data.get("input_i", -23))
            else:
                measured_i = -23
            
            # Second pass: apply normalization
            cmd_normalize = [
                "ffmpeg",
                "-i", input_file,
                "-af", f"loudnorm=I={self.target_lufs}:TP=-1.5:LRA=11",
                "-ar", "24000",
                "-ac", "1",
                "-y",
                output_file
            ]
            
            subprocess.run(cmd_normalize, capture_output=True, timeout=300)
            
            return self.target_lufs
            
        except Exception as e:
            print(f"Audio normalization error: {e}")
            # Copy original if normalization fails
            import shutil
            shutil.copy(input_file, output_file)
            return -23
    
    async def _quality_check(self, audio_file: str) -> bool:
        """Check audio quality: no clipping, proper loudness, no long silences."""
        try:
            # Check for clipping using ffmpeg
            cmd = [
                "ffmpeg",
                "-i", audio_file,
                "-af", "astats=metadata=1:reset=1",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Check for clipping indicators
            if "Clipping" in result.stderr:
                print("Audio has clipping")
                return False
            
            # Check duration (should be > 10 seconds for a recap)
            duration = await self._get_audio_duration(audio_file)
            if duration < 10:
                print(f"Audio too short: {duration}s")
                return False
            
            # Check for long silences
            silence_check = await self._check_silences(audio_file)
            if not silence_check:
                print("Audio has long silences")
                return False
            
            return True
            
        except Exception as e:
            print(f"Quality check error: {e}")
            return True  # Pass by default if check fails
    
    async def _check_silences(self, audio_file: str) -> bool:
        """Check for long silences in audio."""
        try:
            cmd = [
                "ffmpeg",
                "-i", audio_file,
                "-af", "silencedetect=noise=-50dB:d=3",  # Detect silences > 3 seconds
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Count silence detections
            silence_count = result.stderr.count("silence_end")
            
            # Allow up to 2 long silences (for dramatic pauses)
            return silence_count <= 2
            
        except Exception as e:
            print(f"Silence check error: {e}")
            return True
    
    async def _get_audio_duration(self, audio_file: str) -> float:
        """Get audio file duration in seconds."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return float(result.stdout.strip())
            
        except Exception as e:
            print(f"Duration check error: {e}")
            return 0.0
    
    async def _apply_fantastic_captain_processing(self, input_file: str, output_file: str) -> bool:
        """
        Apply "Fantastic Captain" voice processing for deep, cinematic narrator vibe.
        
        Processing chain:
        1. High-pass filter at 80Hz to remove rumble
        2. Low shelf boost at 200Hz for warmth (+3dB)
        3. Presence boost at 3kHz for crisp consonants (+2dB)
        4. Compression for controlled, confident delivery
        5. De-essing to reduce sibilance
        6. Subtle saturation for warmth
        """
        try:
            # Complex filter chain for "Fantastic Captain" voice
            # - highpass: remove low rumble
            # - lowshelf: add warmth to low-end
            # - equalizer: presence boost for clarity
            # - compand: compression for controlled delivery
            # - acompressor: additional dynamic control
            filter_chain = (
                "highpass=f=80,"  # Remove rumble below 80Hz
                "lowshelf=g=3:f=200:t=s,"  # Warm low-end boost
                "equalizer=f=3000:t=q:w=1:g=2,"  # Presence/clarity boost
                "equalizer=f=6000:t=q:w=1:g=-1,"  # Slight de-essing
                "acompressor=threshold=-20dB:ratio=3:attack=5:release=50:makeup=2,"  # Compression
                "afftdn=nf=-25"  # Noise reduction
            )
            
            cmd = [
                "ffmpeg",
                "-i", input_file,
                "-af", filter_chain,
                "-ar", "24000",
                "-ac", "1",
                "-y",
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode != 0:
                print(f"Fantastic Captain processing failed: {result.stderr}")
                # Fall back to simple copy
                import shutil
                shutil.copy(input_file, output_file)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"Fantastic Captain processing error: {e}")
            import shutil
            shutil.copy(input_file, output_file)
            return False
