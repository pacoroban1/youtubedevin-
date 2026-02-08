"""
Part A: Channel Discovery Module
Discovers top-performing recap YouTube channels and videos.
"""

import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json


class ChannelDiscovery:
    def __init__(self, db):
        self.db = db
        self.youtube = None
        self._init_youtube_client()
        
        # Scoring weights for composite score
        self.weights = {
            "subscribers": 0.2,
            "avg_views": 0.4,
            "upload_consistency": 0.2,
            "growth_proxy": 0.2
        }
    
    def _init_youtube_client(self):
        api_key = os.getenv("YOUTUBE_API_KEY")
        if api_key:
            self.youtube = build("youtube", "v3", developerKey=api_key)
    
    async def discover_top_channels(
        self,
        queries: List[str] = None,
        top_n: int = 10,
        videos_per_channel: int = 5,
        # Scout tuning
        lookback_days: int = 14,
        max_video_age_hours: float = 72.0,
        min_views_per_hour: float = 250.0,
        min_views_total: int = 20000,
        min_duration_seconds: int = 180,
    ) -> Dict[str, Any]:
        """
        Discover top recap channels using YouTube Data API.
        
        Args:
            queries: Search queries for finding recap channels
            top_n: Number of top channels to select
            videos_per_channel: Number of videos to select per channel
            lookback_days: Only consider videos published within this lookback window
            max_video_age_hours: Only consider "banger" candidates within this age window
            min_views_per_hour: Minimum views/hour to qualify as a "banger"
            min_views_total: Minimum total views to qualify as a "banger"
            min_duration_seconds: Filter out very short videos (e.g., Shorts)
        
        Returns:
            Dict with channels and videos data
        """
        if queries is None:
            queries = [
                "movie recap",
                "story recap", 
                "ending explained recap",
                "recap explained"
            ]
        
        if not self.youtube:
            return {"error": "YouTube API not configured", "channels": [], "videos": []}
        
        all_channels = {}
        
        # Search for channels using each query
        for query in queries:
            try:
                channels = await self._search_channels(query)
                for channel in channels:
                    channel_id = channel["channel_id"]
                    if channel_id not in all_channels:
                        all_channels[channel_id] = channel
            except HttpError as e:
                print(f"Error searching for '{query}': {e}")
                continue
        
        # Fetch detailed stats for each channel
        enriched_channels = []
        for channel_id, channel_data in all_channels.items():
            try:
                stats = await self._get_channel_stats(channel_id)
                channel_data.update(stats)
                
                # Calculate composite score
                channel_data["composite_score"] = self._calculate_composite_score(channel_data)
                enriched_channels.append(channel_data)
                
                # Save to database
                self.db.save_channel(channel_data)
            except HttpError as e:
                print(f"Error getting stats for channel {channel_id}: {e}")
                continue
        
        # Sort by composite score and select top N
        enriched_channels.sort(key=lambda x: x["composite_score"], reverse=True)
        top_channels = enriched_channels[:top_n]
        
        # Get top videos for each channel
        all_videos = []
        for channel in top_channels:
            try:
                videos = await self._get_channel_videos(
                    channel["channel_id"],
                    max_results=videos_per_channel,
                    lookback_days=lookback_days,
                    min_duration_seconds=min_duration_seconds,
                )
                for video in videos:
                    video["channel_id"] = channel["channel_id"]
                    self.db.save_video(video)
                    all_videos.append(video)
            except HttpError as e:
                print(f"Error getting videos for channel {channel['channel_id']}: {e}")
                continue
        
        # Sort videos by "viral_score" (falls back to views velocity if missing).
        all_videos.sort(key=lambda x: (x.get("viral_score", 0), x.get("views_velocity", 0)), reverse=True)

        selected_video, selection_mode = self._select_target_video(
            all_videos,
            max_video_age_hours=max_video_age_hours,
            min_views_per_hour=min_views_per_hour,
            min_views_total=min_views_total,
        )
        
        # Save snapshot to JSON
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "channels": top_channels,
            "videos": all_videos,
            "selected_video_id": (selected_video.get("video_id") if selected_video else None),
            "selection_mode": selection_mode,
            "thresholds": {
                "lookback_days": lookback_days,
                "max_video_age_hours": max_video_age_hours,
                "min_views_per_hour": min_views_per_hour,
                "min_views_total": min_views_total,
                "min_duration_seconds": min_duration_seconds,
            },
        }
        self._save_snapshot(snapshot)
        
        return {
            "channels": top_channels,
            "videos": all_videos,
            "selected_video_id": (selected_video.get("video_id") if selected_video else None),
            "selected_video": selected_video,
            "selection_mode": selection_mode,
            "thresholds": snapshot["thresholds"],
            "snapshot_saved": True
        }
    
    async def _search_channels(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Search for channels matching the query."""
        request = self.youtube.search().list(
            part="snippet",
            q=query,
            type="channel",
            maxResults=max_results,
            order="relevance"
        )
        response = request.execute()
        
        channels = []
        for item in response.get("items", []):
            channels.append({
                "channel_id": item["snippet"]["channelId"],
                "channel_name": item["snippet"]["title"],
                "description": item["snippet"].get("description", "")
            })
        
        return channels
    
    async def _get_channel_stats(self, channel_id: str) -> Dict[str, Any]:
        """Get detailed statistics for a channel."""
        request = self.youtube.channels().list(
            part="statistics,contentDetails",
            id=channel_id
        )
        response = request.execute()
        
        if not response.get("items"):
            return {}
        
        item = response["items"][0]
        stats = item.get("statistics", {})
        
        subscriber_count = int(stats.get("subscriberCount", 0))
        video_count = int(stats.get("videoCount", 0))
        view_count = int(stats.get("viewCount", 0))
        
        # Calculate average views per video
        avg_views = view_count / video_count if video_count > 0 else 0
        
        # Get recent uploads to calculate consistency
        uploads_playlist = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        upload_consistency = await self._calculate_upload_consistency(uploads_playlist) if uploads_playlist else 0
        
        # Growth proxy: recent views / total views (approximation)
        growth_proxy = await self._estimate_growth_proxy(channel_id)
        
        return {
            "subscriber_count": subscriber_count,
            "upload_count": video_count,
            "avg_views_per_upload": int(avg_views),
            "upload_consistency_score": upload_consistency,
            "growth_proxy_score": growth_proxy
        }
    
    async def _calculate_upload_consistency(self, playlist_id: str) -> float:
        """Calculate upload consistency based on recent uploads."""
        try:
            request = self.youtube.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=20
            )
            response = request.execute()
            
            items = response.get("items", [])
            if len(items) < 2:
                return 0.0
            
            # Get publish dates
            dates = []
            for item in items:
                published = item.get("contentDetails", {}).get("videoPublishedAt")
                if published:
                    dates.append(datetime.fromisoformat(published.replace("Z", "+00:00")))
            
            if len(dates) < 2:
                return 0.0
            
            # Calculate average days between uploads
            dates.sort(reverse=True)
            intervals = []
            for i in range(len(dates) - 1):
                interval = (dates[i] - dates[i + 1]).days
                intervals.append(interval)
            
            avg_interval = sum(intervals) / len(intervals)
            
            # Score: lower interval = higher consistency (max 1.0 for daily uploads)
            # 7 days = 0.5, 14 days = 0.25, etc.
            consistency = min(1.0, 7.0 / max(avg_interval, 1))
            return consistency
            
        except Exception as e:
            print(f"Error calculating upload consistency: {e}")
            return 0.0
    
    async def _estimate_growth_proxy(self, channel_id: str) -> float:
        """Estimate channel growth based on recent video performance."""
        try:
            # Get recent videos
            request = self.youtube.search().list(
                part="snippet",
                channelId=channel_id,
                type="video",
                order="date",
                maxResults=10,
                publishedAfter=(datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
            )
            response = request.execute()
            
            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
            
            if not video_ids:
                return 0.0
            
            # Get video stats
            stats_request = self.youtube.videos().list(
                part="statistics",
                id=",".join(video_ids)
            )
            stats_response = stats_request.execute()
            
            total_views = sum(
                int(item.get("statistics", {}).get("viewCount", 0))
                for item in stats_response.get("items", [])
            )
            
            # Normalize: 1M views in 30 days = 1.0
            growth_proxy = min(1.0, total_views / 1000000)
            return growth_proxy
            
        except Exception as e:
            print(f"Error estimating growth proxy: {e}")
            return 0.0
    
    def _calculate_composite_score(self, channel_data: Dict[str, Any]) -> float:
        """Calculate composite score for channel ranking."""
        # Normalize subscriber count (1M subs = 1.0)
        subs_normalized = min(1.0, channel_data.get("subscriber_count", 0) / 1000000)
        
        # Normalize avg views (100K views = 1.0)
        views_normalized = min(1.0, channel_data.get("avg_views_per_upload", 0) / 100000)
        
        score = (
            self.weights["subscribers"] * subs_normalized +
            self.weights["avg_views"] * views_normalized +
            self.weights["upload_consistency"] * channel_data.get("upload_consistency_score", 0) +
            self.weights["growth_proxy"] * channel_data.get("growth_proxy_score", 0)
        )
        
        return round(score, 4)
    
    async def _get_channel_videos(
        self,
        channel_id: str,
        max_results: int = 5,
        lookback_days: int = 14,
        min_duration_seconds: int = 180,
    ) -> List[Dict[str, Any]]:
        """Get recent videos from a channel and rank by a "viral_score"."""
        published_after = (datetime.utcnow() - timedelta(days=lookback_days)).replace(microsecond=0).isoformat() + "Z"
        # Search for recent videos (we compute velocity ourselves, so prefer recency over total views).
        request = self.youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            publishedAfter=published_after,
            maxResults=min(50, max_results * 6),
        )
        response = request.execute()
        
        video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
        
        if not video_ids:
            return []
        
        # Get detailed video stats
        stats_request = self.youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=",".join(video_ids)
        )
        stats_response = stats_request.execute()
        
        videos = []
        for item in stats_response.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            
            # Parse duration
            duration_str = item.get("contentDetails", {}).get("duration", "PT0S")
            duration_seconds = self._parse_duration(duration_str)

            # Skip Shorts / very short uploads.
            if duration_seconds and duration_seconds < min_duration_seconds:
                continue

            if snippet.get("liveBroadcastContent") not in (None, "none"):
                continue

            # Calculate views velocity (views/hour since publish, smoothed).
            published_at = snippet.get("publishedAt")
            views = int(stats.get("viewCount", 0))
            views_velocity = self._calculate_views_velocity(views, published_at)
            age_hours = self._age_hours(published_at)

            like_count = int(stats.get("likeCount", 0))
            comment_count = int(stats.get("commentCount", 0))
            denom = float(max(views, 1))
            like_rate = like_count / denom
            comment_rate = comment_count / denom
            engagement_rate = (like_count + comment_count) / denom
            # Lightweight engagement-adjusted velocity score (works without dislikes).
            viral_score = views_velocity * (1.0 + 6.0 * like_rate) * (1.0 + 20.0 * comment_rate)
            
            videos.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "view_count": views,
                "like_count": like_count,
                "comment_count": comment_count,
                "duration_seconds": duration_seconds,
                "published_at": published_at,
                "views_velocity": views_velocity,
                "views_per_hour": views_velocity,
                "age_hours": age_hours,
                "like_rate": round(like_rate, 6),
                "comment_rate": round(comment_rate, 6),
                "engagement_rate": round(engagement_rate, 6),
                "viral_score": round(viral_score, 4),
                "status": "discovered"
            })
        
        # Sort by viral score (then velocity) and return top N
        videos.sort(key=lambda x: (x.get("viral_score", 0), x.get("views_velocity", 0)), reverse=True)
        return videos[:max_results]
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        import re
        
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    
    def _calculate_views_velocity(self, views: int, published_at: str) -> float:
        """Calculate views per hour since publish (smoothed for very fresh uploads)."""
        if not published_at:
            return 0.0
        
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_since = (now - published).total_seconds() / 3600.0
            # Smooth uploads within the last hour to 1 hour to avoid extreme spikes.
            hours_since = max(hours_since, 1.0)
            return views / hours_since
        except Exception:
            return 0.0

    def _age_hours(self, published_at: Optional[str]) -> float:
        """Compute age in hours (UTC)."""
        if not published_at:
            return 0.0
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return max(0.0, (now - published).total_seconds() / 3600.0)
        except Exception:
            return 0.0

    def _select_target_video(
        self,
        videos: List[Dict[str, Any]],
        max_video_age_hours: float,
        min_views_per_hour: float,
        min_views_total: int,
        fallback_window_hours: float = 24.0,
    ):
        """
        "Taste layer" selector:
          - Prefer candidates that look viral (views/hour + minimum total views + age window)
          - If none qualify, fall back to highest total views in the last 24h
          - Final fallback: highest viral_score overall
        """
        if not videos:
            return None, "none"

        # Only consider reasonably recent videos for selection.
        recent = [v for v in videos if float(v.get("age_hours") or 0.0) <= float(max_video_age_hours)]

        for v in recent:
            vph = float(v.get("views_per_hour") or v.get("views_velocity") or 0.0)
            views = int(v.get("view_count") or 0)
            age_h = float(v.get("age_hours") or 0.0)
            v["banger"] = bool(age_h <= max_video_age_hours and vph >= min_views_per_hour and views >= min_views_total)

        bangers = [v for v in recent if v.get("banger")]
        if bangers:
            chosen = max(bangers, key=lambda v: float(v.get("viral_score") or 0.0))
            return chosen, "banger"

        # Fallback: pick the most viewed video in the last 24h.
        last_day = [v for v in recent if float(v.get("age_hours") or 0.0) <= float(fallback_window_hours)]
        if last_day:
            chosen = max(last_day, key=lambda v: (int(v.get("view_count") or 0), float(v.get("viral_score") or 0.0)))
            return chosen, "fallback_24h_highest_views"

        # Final fallback: best score among recent.
        if recent:
            chosen = max(recent, key=lambda v: float(v.get("viral_score") or 0.0))
            return chosen, "fallback_best_score"

        # If everything is older than the max window, still pick something rather than returning nothing.
        chosen = max(videos, key=lambda v: float(v.get("viral_score") or 0.0))
        return chosen, "fallback_any"
    
    def _save_snapshot(self, snapshot: Dict[str, Any]):
        """Save discovery snapshot to JSON file."""
        os.makedirs("/app/media/snapshots", exist_ok=True)
        filename = f"/app/media/snapshots/discovery_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)
