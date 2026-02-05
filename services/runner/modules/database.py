"""
Database module for Amharic Recap Autopilot.
Handles all database operations using SQLAlchemy.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Optional, Dict, Any, List
import json
from datetime import datetime


class Database:
    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = os.getenv("POSTGRES_PORT", "5432")
        self.user = os.getenv("POSTGRES_USER", "autopilot")
        self.password = os.getenv("POSTGRES_PASSWORD", "autopilot_secret")
        self.database = os.getenv("POSTGRES_DB", "autopilot")
        
        self.connection_string = f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        self.engine = create_engine(self.connection_string)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()
    
    def save_channel(self, channel_data: Dict[str, Any]) -> bool:
        with self.get_session() as session:
            try:
                session.execute(text("""
                    INSERT INTO channels (
                        channel_id, channel_name, subscriber_count, upload_count,
                        avg_views_per_upload, upload_consistency_score, growth_proxy_score,
                        composite_score, last_updated
                    ) VALUES (
                        :channel_id, :channel_name, :subscriber_count, :upload_count,
                        :avg_views_per_upload, :upload_consistency_score, :growth_proxy_score,
                        :composite_score, :last_updated
                    )
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        subscriber_count = EXCLUDED.subscriber_count,
                        upload_count = EXCLUDED.upload_count,
                        avg_views_per_upload = EXCLUDED.avg_views_per_upload,
                        upload_consistency_score = EXCLUDED.upload_consistency_score,
                        growth_proxy_score = EXCLUDED.growth_proxy_score,
                        composite_score = EXCLUDED.composite_score,
                        last_updated = EXCLUDED.last_updated
                """), {
                    "channel_id": channel_data["channel_id"],
                    "channel_name": channel_data["channel_name"],
                    "subscriber_count": channel_data.get("subscriber_count", 0),
                    "upload_count": channel_data.get("upload_count", 0),
                    "avg_views_per_upload": channel_data.get("avg_views_per_upload", 0),
                    "upload_consistency_score": channel_data.get("upload_consistency_score", 0),
                    "growth_proxy_score": channel_data.get("growth_proxy_score", 0),
                    "composite_score": channel_data.get("composite_score", 0),
                    "last_updated": datetime.utcnow()
                })
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                print(f"Error saving channel: {e}")
                return False
    
    def save_video(self, video_data: Dict[str, Any]) -> bool:
        with self.get_session() as session:
            try:
                session.execute(text("""
                    INSERT INTO videos (
                        video_id, channel_id, title, description, view_count,
                        like_count, comment_count, duration_seconds, published_at,
                        views_velocity, status
                    ) VALUES (
                        :video_id, :channel_id, :title, :description, :view_count,
                        :like_count, :comment_count, :duration_seconds, :published_at,
                        :views_velocity, :status
                    )
                    ON CONFLICT (video_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        view_count = EXCLUDED.view_count,
                        views_velocity = EXCLUDED.views_velocity,
                        status = EXCLUDED.status
                """), {
                    "video_id": video_data["video_id"],
                    "channel_id": video_data.get("channel_id"),
                    "title": video_data["title"],
                    "description": video_data.get("description", ""),
                    "view_count": video_data.get("view_count", 0),
                    "like_count": video_data.get("like_count", 0),
                    "comment_count": video_data.get("comment_count", 0),
                    "duration_seconds": video_data.get("duration_seconds"),
                    "published_at": video_data.get("published_at"),
                    "views_velocity": video_data.get("views_velocity", 0),
                    "status": video_data.get("status", "discovered")
                })
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                print(f"Error saving video: {e}")
                return False
    
    def save_transcript(self, video_id: str, transcript_data: Dict[str, Any]) -> bool:
        with self.get_session() as session:
            try:
                session.execute(text("""
                    INSERT INTO transcripts (
                        video_id, raw_transcript, cleaned_transcript, timestamps,
                        language_detected, source
                    ) VALUES (
                        :video_id, :raw_transcript, :cleaned_transcript, :timestamps,
                        :language_detected, :source
                    )
                """), {
                    "video_id": video_id,
                    "raw_transcript": transcript_data.get("raw_transcript", ""),
                    "cleaned_transcript": transcript_data.get("cleaned_transcript", ""),
                    "timestamps": json.dumps(transcript_data.get("timestamps", [])),
                    "language_detected": transcript_data.get("language_detected", "en"),
                    "source": transcript_data.get("source", "unknown")
                })
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                print(f"Error saving transcript: {e}")
                return False
    
    def save_script(self, video_id: str, script_data: Dict[str, Any]) -> int:
        with self.get_session() as session:
            try:
                result = session.execute(text("""
                    INSERT INTO scripts (
                        video_id, hook_text, main_recap_segments, payoff_text,
                        cta_text, full_script, quality_score
                    ) VALUES (
                        :video_id, :hook_text, :main_recap_segments, :payoff_text,
                        :cta_text, :full_script, :quality_score
                    )
                    RETURNING id
                """), {
                    "video_id": video_id,
                    "hook_text": script_data.get("hook_text", ""),
                    "main_recap_segments": json.dumps(script_data.get("main_recap_segments", [])),
                    "payoff_text": script_data.get("payoff_text", ""),
                    "cta_text": script_data.get("cta_text", ""),
                    "full_script": script_data.get("full_script", ""),
                    "quality_score": script_data.get("quality_score", 0)
                })
                script_id = result.fetchone()[0]
                session.commit()
                return script_id
            except Exception as e:
                session.rollback()
                print(f"Error saving script: {e}")
                return -1
    
    def save_audio(self, video_id: str, script_id: int, audio_data: Dict[str, Any]) -> int:
        with self.get_session() as session:
            try:
                result = session.execute(text("""
                    INSERT INTO audio (
                        video_id, script_id, voice_provider, voice_id,
                        audio_file_path, duration_seconds, loudness_lufs, quality_check_passed
                    ) VALUES (
                        :video_id, :script_id, :voice_provider, :voice_id,
                        :audio_file_path, :duration_seconds, :loudness_lufs, :quality_check_passed
                    )
                    RETURNING id
                """), {
                    "video_id": video_id,
                    "script_id": script_id,
                    "voice_provider": audio_data.get("voice_provider", "azure"),
                    "voice_id": audio_data.get("voice_id", "am-ET-AmehaNeural"),
                    "audio_file_path": audio_data.get("audio_file_path", ""),
                    "duration_seconds": audio_data.get("duration_seconds", 0),
                    "loudness_lufs": audio_data.get("loudness_lufs", -14),
                    "quality_check_passed": audio_data.get("quality_check_passed", False)
                })
                audio_id = result.fetchone()[0]
                session.commit()
                return audio_id
            except Exception as e:
                session.rollback()
                print(f"Error saving audio: {e}")
                return -1
    
    def save_render(self, video_id: str, audio_id: int, render_data: Dict[str, Any]) -> int:
        with self.get_session() as session:
            try:
                result = session.execute(text("""
                    INSERT INTO renders (
                        video_id, audio_id, output_file_path, duration_seconds,
                        scene_alignment_score, quality_check_passed
                    ) VALUES (
                        :video_id, :audio_id, :output_file_path, :duration_seconds,
                        :scene_alignment_score, :quality_check_passed
                    )
                    RETURNING id
                """), {
                    "video_id": video_id,
                    "audio_id": audio_id,
                    "output_file_path": render_data.get("output_file_path", ""),
                    "duration_seconds": render_data.get("duration_seconds", 0),
                    "scene_alignment_score": render_data.get("scene_alignment_score", 0),
                    "quality_check_passed": render_data.get("quality_check_passed", False)
                })
                render_id = result.fetchone()[0]
                session.commit()
                return render_id
            except Exception as e:
                session.rollback()
                print(f"Error saving render: {e}")
                return -1
    
    def save_thumbnail(self, video_id: str, thumbnail_data: Dict[str, Any]) -> int:
        with self.get_session() as session:
            try:
                result = session.execute(text("""
                    INSERT INTO thumbnails (
                        video_id, thumbnail_path, hook_text_amharic,
                        is_selected, heuristic_score
                    ) VALUES (
                        :video_id, :thumbnail_path, :hook_text_amharic,
                        :is_selected, :heuristic_score
                    )
                    RETURNING id
                """), {
                    "video_id": video_id,
                    "thumbnail_path": thumbnail_data.get("thumbnail_path", ""),
                    "hook_text_amharic": thumbnail_data.get("hook_text_amharic", ""),
                    "is_selected": thumbnail_data.get("is_selected", False),
                    "heuristic_score": thumbnail_data.get("heuristic_score", 0)
                })
                thumbnail_id = result.fetchone()[0]
                session.commit()
                return thumbnail_id
            except Exception as e:
                session.rollback()
                print(f"Error saving thumbnail: {e}")
                return -1
    
    def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM videos WHERE video_id = :video_id
            """), {"video_id": video_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def get_transcript(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM transcripts WHERE video_id = :video_id
                ORDER BY created_at DESC LIMIT 1
            """), {"video_id": video_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def get_script(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM scripts WHERE video_id = :video_id
                ORDER BY created_at DESC LIMIT 1
            """), {"video_id": video_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def get_audio(self, video_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM audio WHERE video_id = :video_id
                ORDER BY created_at DESC LIMIT 1
            """), {"video_id": video_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def get_top_channels(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM channels
                ORDER BY composite_score DESC
                LIMIT :limit
            """), {"limit": limit})
            return [dict(row._mapping) for row in result.fetchall()]
    
    def get_top_videos(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            result = session.execute(text("""
                SELECT * FROM videos
                WHERE status = 'discovered'
                ORDER BY views_velocity DESC
                LIMIT :limit
            """), {"limit": limit})
            return [dict(row._mapping) for row in result.fetchall()]
    
    def update_video_status(self, video_id: str, status: str) -> bool:
        with self.get_session() as session:
            try:
                session.execute(text("""
                    UPDATE videos SET status = :status WHERE video_id = :video_id
                """), {"video_id": video_id, "status": status})
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                print(f"Error updating video status: {e}")
                return False
