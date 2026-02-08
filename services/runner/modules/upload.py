"""
Part G: YouTube Upload Module
Uploads videos to YouTube with metadata, chapters, and thumbnails.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

from sqlalchemy import text

from modules.gemini_client import gemini

class YouTubeUploader:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
        # OAuth credentials
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

        # Upload defaults
        # Allowed: public | unlisted | private
        self.privacy_status = (os.getenv("YOUTUBE_PRIVACY_STATUS") or "public").strip().lower()
        if self.privacy_status not in ("public", "unlisted", "private"):
            self.privacy_status = "public"
        
        # YouTube API scopes
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]
        
        self.youtube = None
        self._init_youtube_client()
    
    def _init_youtube_client(self):
        """Initialize YouTube API client with OAuth."""
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            print("YouTube OAuth credentials not configured")
            return
        
        try:
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.scopes
            )
            
            # Refresh the token
            credentials.refresh(Request())
            
            self.youtube = build("youtube", "v3", credentials=credentials)
            
        except Exception as e:
            print(f"YouTube client initialization error: {e}")
    
    async def upload_video(self, video_id: str) -> Dict[str, Any]:
        """
        Upload video to YouTube with full metadata.
        
        Args:
            video_id: Internal video ID
        
        Returns:
            Dict with YouTube video ID and upload status
        """
        if not self.youtube:
            raise Exception("YouTube API not configured")
        
        # Get video data
        video_data = self.db.get_video(video_id)
        script_data = self.db.get_script(video_id)
        
        # Get render path
        output_dir = os.path.join(self.media_dir, "output", video_id)
        video_file = os.path.join(output_dir, "final_video.mp4")
        
        if not os.path.exists(video_file):
            raise Exception(f"Rendered video not found: {video_file}")
        
        # Generate title candidates
        titles = await self._generate_title_candidates(video_data, script_data)
        selected_title = titles[0] if titles else "አዲስ ፊልም ሪካፕ"
        
        # Generate description
        description = await self._generate_description(video_data, script_data)
        
        # Generate tags
        tags = await self._generate_tags(video_data)
        
        # Generate chapters from script segments
        chapters = await self._generate_chapters(script_data)
        
        # Add chapters to description
        if chapters:
            description += "\n\n" + self._format_chapters(chapters)
        
        # Upload video
        youtube_video_id = await self._upload_to_youtube(
            video_file=video_file,
            title=selected_title,
            description=description,
            tags=tags,
            category_id="24"  # Entertainment
        )
        
        if not youtube_video_id:
            raise Exception("Video upload failed")
        
        # Upload thumbnail
        thumb_dir = os.path.join(self.media_dir, "thumbnails", video_id)
        thumbnail_uploaded = await self._upload_thumbnail(youtube_video_id, video_id, thumb_dir)
        
        # Add to playlist
        playlist_id = await self._add_to_playlist(youtube_video_id)
        
        # Save upload record
        with self.db.get_session() as session:
            # Get render and thumbnail IDs
            render_result = session.execute(text("""
                SELECT id FROM renders WHERE video_id = :video_id ORDER BY created_at DESC LIMIT 1
            """), {"video_id": video_id})
            render_row = render_result.fetchone()
            render_id = render_row[0] if render_row else None
            
            thumb_result = session.execute(text("""
                SELECT id FROM thumbnails WHERE video_id = :video_id AND is_selected = TRUE LIMIT 1
            """), {"video_id": video_id})
            thumb_row = thumb_result.fetchone()
            thumbnail_id = thumb_row[0] if thumb_row else None
            
            session.execute(text("""
                INSERT INTO uploads (
                    video_id, render_id, thumbnail_id, youtube_video_id,
                    title, description, tags, chapters, playlist_id,
                    upload_status, uploaded_at
                ) VALUES (
                    :video_id, :render_id, :thumbnail_id, :youtube_video_id,
                    :title, :description, :tags, :chapters, :playlist_id,
                    :upload_status, :uploaded_at
                )
            """), {
                "video_id": video_id,
                "render_id": render_id,
                "thumbnail_id": thumbnail_id,
                "youtube_video_id": youtube_video_id,
                "title": selected_title,
                "description": description,
                "tags": json.dumps(tags),
                "chapters": json.dumps(chapters),
                "playlist_id": playlist_id,
                "upload_status": "uploaded",
                "uploaded_at": datetime.utcnow()
            })
            session.commit()
        
        self.db.update_video_status(video_id, "uploaded")
        
        return {
            "youtube_video_id": youtube_video_id,
            "youtube_url": f"https://youtube.com/watch?v={youtube_video_id}",
            "title": selected_title,
            "thumbnail_uploaded": thumbnail_uploaded,
            "playlist_id": playlist_id,
            "status": "uploaded"
        }
    
    async def _generate_title_candidates(
        self,
        video_data: Optional[Dict],
        script_data: Optional[Dict]
    ) -> List[str]:
        """Generate 3 title candidates in Amharic."""
        if not gemini.is_configured():
            return self._fallback_titles()
        
        try:
            original_title = video_data.get("title", "") if video_data else ""
            hook = script_data.get("hook_text", "") if script_data else ""
            
            prompt = f"""Generate 3 YouTube video titles in Amharic for a movie recap video.

Original title: {original_title}
Hook: {hook[:200]}

Requirements:
1. Use Ge'ez script (ፊደል)
2. Include emotional/dramatic words
3. Create curiosity
4. Keep under 60 characters each
5. Include relevant keywords

Return ONLY 3 titles, one per line, nothing else."""
            response_text = gemini.generate_text(prompt, temperature=0.7)
            titles = response_text.strip().split('\n')
            titles = [t.strip() for t in titles if t.strip()]
            
            return titles[:3] if titles else self._fallback_titles()
            
        except Exception as e:
            print(f"Title generation error: {e}")
            return self._fallback_titles()
    
    def _fallback_titles(self) -> List[str]:
        """Fallback Amharic titles."""
        return [
            "አስደናቂ ፊልም ሪካፕ - ይህን ማየት አለባችሁ!",
            "ፊልም ማጠቃለያ - እውነተኛ ታሪክ",
            "አዲስ ፊልም ሪካፕ በአማርኛ"
        ]
    
    async def _generate_description(
        self,
        video_data: Optional[Dict],
        script_data: Optional[Dict]
    ) -> str:
        """Generate video description in Amharic."""
        base_description = """🎬 ፊልም ሪካፕ በአማርኛ

ይህን ቻናል ሰብስክራይብ ያድርጉ ለተጨማሪ ፊልም ሪካፕ!

#ፊልም #ሪካፕ #አማርኛ #MovieRecap #Ethiopian"""

        if not gemini.is_configured():
            return base_description
        
        try:
            original_title = video_data.get("title", "") if video_data else ""
            hook = script_data.get("hook_text", "") if script_data else ""
            
            prompt = f"""Write a YouTube video description in Amharic for a movie recap.

Movie: {original_title}
Hook: {hook[:200]}

Requirements:
1. Use Ge'ez script
2. 2-3 paragraph summary
3. Include call to action (subscribe, like)
4. Add relevant hashtags
5. Keep professional but engaging

Write the description, nothing else."""
            response_text = gemini.generate_text(prompt, temperature=0.7)
            return response_text.strip()
            
        except Exception as e:
            print(f"Description generation error: {e}")
            return base_description
    
    async def _generate_tags(self, video_data: Optional[Dict]) -> List[str]:
        """Generate relevant tags for the video."""
        base_tags = [
            "movie recap",
            "film recap",
            "amharic",
            "ethiopian",
            "ፊልም",
            "ሪካፕ",
            "አማርኛ",
            "movie explanation",
            "ending explained"
        ]
        
        if video_data:
            title = video_data.get("title", "")
            # Extract potential keywords from title
            words = title.split()
            for word in words[:5]:
                if len(word) > 3:
                    base_tags.append(word.lower())
        
        return base_tags[:30]  # YouTube limit
    
    async def _generate_chapters(self, script_data: Optional[Dict]) -> List[Dict[str, Any]]:
        """Generate video chapters from script segments."""
        if not script_data:
            return []
        
        segments = script_data.get("main_recap_segments", [])
        if isinstance(segments, str):
            segments = json.loads(segments)
        
        chapters = [{"time": "0:00", "title": "መግቢያ"}]  # Intro
        
        current_time = 15  # Start after hook (15 seconds)
        
        for i, segment in enumerate(segments):
            minutes = current_time // 60
            seconds = current_time % 60
            time_str = f"{minutes}:{seconds:02d}"
            
            # Generate chapter title
            chapter_title = f"ክፍል {i + 1}"
            
            chapters.append({
                "time": time_str,
                "title": chapter_title
            })
            
            duration = segment.get("estimated_duration", 30)
            current_time += int(duration)
        
        # Add ending chapter
        minutes = current_time // 60
        seconds = current_time % 60
        chapters.append({
            "time": f"{minutes}:{seconds:02d}",
            "title": "መደምደሚያ"  # Conclusion
        })
        
        return chapters
    
    def _format_chapters(self, chapters: List[Dict]) -> str:
        """Format chapters for YouTube description."""
        lines = ["📑 ምዕራፎች / Chapters:"]
        for chapter in chapters:
            lines.append(f"{chapter['time']} - {chapter['title']}")
        return "\n".join(lines)
    
    async def _upload_to_youtube(
        self,
        video_file: str,
        title: str,
        description: str,
        tags: List[str],
        category_id: str = "24"
    ) -> Optional[str]:
        """Upload video file to YouTube."""
        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id,
                    "defaultLanguage": "am",
                    "defaultAudioLanguage": "am"
                },
                "status": {
                    "privacyStatus": self.privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }
            
            media = MediaFileUpload(
                video_file,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024  # 1MB chunks
            )
            
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress() * 100)}%")
            
            return response.get("id")
            
        except Exception as e:
            print(f"YouTube upload error: {e}")
            return None
    
    async def _upload_thumbnail(self, youtube_video_id: str, video_id: str, thumb_dir: str) -> bool:
        """Upload thumbnail to YouTube video."""
        try:
            # Prefer the selected thumbnail from the DB if present.
            selected_path = None
            try:
                with self.db.get_session() as session:
                    row = session.execute(
                        text(
                            """
                            SELECT thumbnail_path
                            FROM thumbnails
                            WHERE video_id = :video_id AND is_selected = TRUE
                            ORDER BY created_at DESC
                            LIMIT 1
                            """
                        ),
                        {"video_id": video_id},
                    ).fetchone()
                if row and row[0]:
                    selected_path = str(row[0])
            except Exception:
                selected_path = None

            if selected_path and os.path.exists(selected_path):
                self.youtube.thumbnails().set(
                    videoId=youtube_video_id,
                    media_body=MediaFileUpload(selected_path, mimetype="image/png"),
                ).execute()
                return True

            # Find selected thumbnail
            for filename in os.listdir(thumb_dir) if os.path.exists(thumb_dir) else []:
                if filename.endswith(".png"):
                    thumb_path = os.path.join(thumb_dir, filename)
                    
                    self.youtube.thumbnails().set(
                        videoId=youtube_video_id,
                        media_body=MediaFileUpload(thumb_path, mimetype="image/png")
                    ).execute()
                    
                    return True
            
            return False
            
        except Exception as e:
            print(f"Thumbnail upload error: {e}")
            return False
    
    async def _add_to_playlist(self, youtube_video_id: str) -> Optional[str]:
        """Add video to recap playlist."""
        playlist_id = os.getenv("YOUTUBE_PLAYLIST_ID")
        
        if not playlist_id:
            # Try to find or create playlist
            playlist_id = await self._get_or_create_playlist()
        
        if not playlist_id:
            return None
        
        try:
            self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": youtube_video_id
                        }
                    }
                }
            ).execute()
            
            return playlist_id
            
        except Exception as e:
            print(f"Playlist add error: {e}")
            return None
    
    async def _get_or_create_playlist(self) -> Optional[str]:
        """Get existing playlist or create new one."""
        try:
            # Search for existing playlist
            request = self.youtube.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50
            )
            response = request.execute()
            
            for item in response.get("items", []):
                if "ሪካፕ" in item["snippet"]["title"] or "recap" in item["snippet"]["title"].lower():
                    return item["id"]
            
            # Create new playlist
            request = self.youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": "ፊልም ሪካፕ | Movie Recaps",
                        "description": "የፊልም ሪካፕ ቪዲዮዎች በአማርኛ"
                    },
                    "status": {
                        "privacyStatus": "public"
                    }
                }
            )
            response = request.execute()
            
            return response.get("id")
            
        except Exception as e:
            print(f"Playlist error: {e}")
            return None
