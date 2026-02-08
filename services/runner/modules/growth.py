"""
Part H: Growth Loop Module
Handles distribution, A/B testing, metrics tracking, and daily reports.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import text
import httpx


class GrowthLoop:
    def __init__(self, db):
        self.db = db
        self.media_dir = os.getenv("MEDIA_DIR", "/app/media")
        
        # Distribution platforms
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
        self.twitter_api_key = os.getenv("TWITTER_API_KEY")
        self.twitter_api_secret = os.getenv("TWITTER_API_SECRET")
        self.twitter_access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.twitter_access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    
    async def distribute_and_track(self, video_id: str) -> Dict[str, Any]:
        """
        Distribute video to social platforms and set up tracking.
        
        Args:
            video_id: Internal video ID
        
        Returns:
            Dict with distribution results and initial metrics
        """
        # Get upload data
        with self.db.get_session() as session:
            result = session.execute(text("""
                SELECT u.*, v.title as original_title
                FROM uploads u
                JOIN videos v ON u.video_id = v.video_id
                WHERE u.video_id = :video_id
                ORDER BY u.created_at DESC LIMIT 1
            """), {"video_id": video_id})
            upload_data = result.fetchone()
        
        if not upload_data:
            raise Exception(f"No upload found for video {video_id}")
        
        upload_dict = dict(upload_data._mapping)
        youtube_url = f"https://youtube.com/watch?v={upload_dict['youtube_video_id']}"
        title = upload_dict.get("title", "")
        
        # Distribute to platforms
        platforms_posted = []
        
        # Post to Telegram
        if self.telegram_bot_token and self.telegram_channel_id:
            telegram_result = await self._post_to_telegram(title, youtube_url)
            if telegram_result:
                platforms_posted.append("telegram")
        
        # Post to X (Twitter)
        if all([self.twitter_api_key, self.twitter_api_secret, 
                self.twitter_access_token, self.twitter_access_secret]):
            twitter_result = await self._post_to_twitter(title, youtube_url)
            if twitter_result:
                platforms_posted.append("twitter")
        
        # Fetch early metrics (if available)
        early_metrics = await self._fetch_early_metrics(upload_dict['youtube_video_id'])
        
        # Save metrics
        if early_metrics:
            with self.db.get_session() as session:
                session.execute(text("""
                    INSERT INTO metrics (
                        upload_id, views, impressions, ctr_percent,
                        avg_view_duration_seconds, retention_percent, likes, comments
                    ) VALUES (
                        :upload_id, :views, :impressions, :ctr,
                        :avg_duration, :retention, :likes, :comments
                    )
                """), {
                    "upload_id": upload_dict["id"],
                    "views": early_metrics.get("views", 0),
                    "impressions": early_metrics.get("impressions", 0),
                    "ctr": early_metrics.get("ctr", 0),
                    "avg_duration": early_metrics.get("avg_view_duration", 0),
                    "retention": early_metrics.get("retention", 0),
                    "likes": early_metrics.get("likes", 0),
                    "comments": early_metrics.get("comments", 0)
                })
                session.commit()
        
        # Suggest optimizations
        suggestions = await self._generate_suggestions(early_metrics, upload_dict)
        
        self.db.update_video_status(video_id, "distributed")
        
        return {
            "platforms": platforms_posted,
            "distributed_to": platforms_posted,
            "youtube_url": youtube_url,
            "metrics": early_metrics,
            "suggestions": suggestions
        }
    
    async def _post_to_telegram(self, title: str, youtube_url: str) -> bool:
        """Post announcement to Telegram channel."""
        try:
            message = f"""🎬 አዲስ ፊልም ሪካፕ!

{title}

👉 {youtube_url}

#ፊልም #ሪካፕ #አማርኛ"""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_channel_id,
                        "text": message,
                        "parse_mode": "HTML"
                    }
                )
                return response.status_code == 200
                
        except Exception as e:
            print(f"Telegram post error: {e}")
            return False
    
    async def _post_to_twitter(self, title: str, youtube_url: str) -> bool:
        """Post announcement to X (Twitter)."""
        try:
            # Truncate title to fit Twitter limit
            max_title_len = 200
            if len(title) > max_title_len:
                title = title[:max_title_len-3] + "..."
            
            tweet = f"""🎬 አዲስ ፊልም ሪካፕ!

{title}

👉 {youtube_url}

#MovieRecap #Amharic #Ethiopian"""

            # Using Twitter API v2
            import tweepy
            
            client = tweepy.Client(
                consumer_key=self.twitter_api_key,
                consumer_secret=self.twitter_api_secret,
                access_token=self.twitter_access_token,
                access_token_secret=self.twitter_access_secret
            )
            
            response = client.create_tweet(text=tweet)
            return response.data is not None
            
        except Exception as e:
            print(f"Twitter post error: {e}")
            return False
    
    async def _fetch_early_metrics(self, youtube_video_id: str) -> Dict[str, Any]:
        """Fetch early metrics from YouTube Analytics."""
        # Note: YouTube Analytics data has a 2-day delay
        # For early metrics, we use the regular YouTube Data API
        
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            
            client_id = os.getenv("YOUTUBE_CLIENT_ID")
            client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
            refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
            
            if not all([client_id, client_secret, refresh_token]):
                return {}
            
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )
            credentials.refresh(Request())
            
            youtube = build("youtube", "v3", credentials=credentials)
            
            response = youtube.videos().list(
                part="statistics",
                id=youtube_video_id
            ).execute()
            
            if not response.get("items"):
                return {}
            
            stats = response["items"][0].get("statistics", {})
            
            return {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "impressions": 0,  # Not available via Data API
                "ctr": 0,
                "avg_view_duration": 0,
                "retention": 0
            }
            
        except Exception as e:
            print(f"Metrics fetch error: {e}")
            return {}
    
    async def _generate_suggestions(
        self,
        metrics: Dict[str, Any],
        upload_data: Dict[str, Any]
    ) -> List[str]:
        """Generate optimization suggestions based on metrics."""
        suggestions = []
        
        if not metrics:
            suggestions.append("Metrics not yet available. Check back in 24-48 hours.")
            return suggestions
        
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        
        # Engagement ratio
        if views > 0:
            engagement_ratio = likes / views
            
            if engagement_ratio < 0.02:
                suggestions.append("Low engagement ratio. Consider A/B testing a new title.")
            elif engagement_ratio > 0.05:
                suggestions.append("Great engagement! Consider promoting this video more.")
        
        # View velocity
        if views < 100:
            suggestions.append("Low initial views. Consider sharing on more platforms.")
        
        # Title suggestions
        titles = json.loads(upload_data.get("tags", "[]"))
        if len(titles) < 10:
            suggestions.append("Add more tags to improve discoverability.")
        
        return suggestions
    
    async def setup_ab_test(
        self,
        video_id: str,
        test_type: str,
        variants: List[str]
    ) -> int:
        """Set up A/B test for title or thumbnail."""
        with self.db.get_session() as session:
            # Get upload ID
            result = session.execute(text("""
                SELECT id FROM uploads WHERE video_id = :video_id
                ORDER BY created_at DESC LIMIT 1
            """), {"video_id": video_id})
            upload_row = result.fetchone()
            
            if not upload_row:
                raise Exception(f"No upload found for video {video_id}")
            
            upload_id = upload_row[0]
            
            # Create A/B test
            result = session.execute(text("""
                INSERT INTO ab_tests (
                    upload_id, test_type, variant_a, variant_b, variant_c,
                    current_variant, started_at
                ) VALUES (
                    :upload_id, :test_type, :variant_a, :variant_b, :variant_c,
                    'a', :started_at
                )
                RETURNING id
            """), {
                "upload_id": upload_id,
                "test_type": test_type,
                "variant_a": variants[0] if len(variants) > 0 else None,
                "variant_b": variants[1] if len(variants) > 1 else None,
                "variant_c": variants[2] if len(variants) > 2 else None,
                "started_at": datetime.utcnow()
            })
            
            test_id = result.fetchone()[0]
            session.commit()
            
            return test_id
    
    async def rotate_ab_variant(self, test_id: int) -> str:
        """Rotate to next A/B test variant."""
        with self.db.get_session() as session:
            # Get current variant
            result = session.execute(text("""
                SELECT current_variant, variant_a, variant_b, variant_c
                FROM ab_tests WHERE id = :test_id
            """), {"test_id": test_id})
            test_data = result.fetchone()
            
            if not test_data:
                raise Exception(f"A/B test {test_id} not found")
            
            current = test_data[0]
            variants = {"a": test_data[1], "b": test_data[2], "c": test_data[3]}
            
            # Determine next variant
            variant_order = ["a", "b", "c"]
            current_idx = variant_order.index(current)
            
            for i in range(1, 4):
                next_idx = (current_idx + i) % 3
                next_variant = variant_order[next_idx]
                if variants[next_variant]:
                    # Update to next variant
                    session.execute(text("""
                        UPDATE ab_tests SET current_variant = :variant WHERE id = :test_id
                    """), {"variant": next_variant, "test_id": test_id})
                    session.commit()
                    return next_variant
            
            return current
    
    async def generate_daily_report(self) -> Dict[str, Any]:
        """Generate daily report with production stats and metrics."""
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        
        with self.db.get_session() as session:
            # Videos produced today
            result = session.execute(text("""
                SELECT COUNT(*) FROM videos 
                WHERE DATE(created_at) = :today AND status = 'uploaded'
            """), {"today": today})
            videos_produced = result.fetchone()[0]
            
            # Videos uploaded today
            result = session.execute(text("""
                SELECT COUNT(*) FROM uploads 
                WHERE DATE(uploaded_at) = :today
            """), {"today": today})
            videos_uploaded = result.fetchone()[0]
            
            # Total views today (from metrics)
            result = session.execute(text("""
                SELECT COALESCE(SUM(views), 0) FROM metrics 
                WHERE DATE(recorded_at) = :today
            """), {"today": today})
            total_views = result.fetchone()[0]
            
            # Average CTR
            result = session.execute(text("""
                SELECT AVG(ctr_percent) FROM metrics 
                WHERE DATE(recorded_at) = :today AND ctr_percent > 0
            """), {"today": today})
            avg_ctr = result.fetchone()[0] or 0
            
            # Average retention
            result = session.execute(text("""
                SELECT AVG(retention_percent) FROM metrics 
                WHERE DATE(recorded_at) = :today AND retention_percent > 0
            """), {"today": today})
            avg_retention = result.fetchone()[0] or 0
            
            # Recent uploads with metrics
            result = session.execute(text("""
                SELECT u.youtube_video_id, u.title, m.views, m.likes
                FROM uploads u
                LEFT JOIN metrics m ON u.id = m.upload_id
                WHERE DATE(u.uploaded_at) >= :yesterday
                ORDER BY u.uploaded_at DESC
                LIMIT 10
            """), {"yesterday": yesterday})
            recent_uploads = [dict(row._mapping) for row in result.fetchall()]
        
        # Build report
        report = {
            "date": str(today),
            "summary": {
                "videos_produced": videos_produced,
                "videos_uploaded": videos_uploaded,
                "total_views": total_views,
                "avg_ctr": round(avg_ctr, 2),
                "avg_retention": round(avg_retention, 2)
            },
            "recent_uploads": recent_uploads,
            "recommendations": await self._generate_daily_recommendations(
                videos_produced, total_views, avg_ctr
            )
        }
        
        # Generate markdown report
        markdown_report = self._format_markdown_report(report)
        
        # Save to database
        with self.db.get_session() as session:
            session.execute(text("""
                INSERT INTO daily_reports (
                    report_date, videos_produced, videos_uploaded,
                    total_views, avg_ctr, avg_retention,
                    report_json, report_markdown
                ) VALUES (
                    :date, :produced, :uploaded, :views, :ctr, :retention,
                    :json, :markdown
                )
                ON CONFLICT (report_date) DO UPDATE SET
                    videos_produced = EXCLUDED.videos_produced,
                    videos_uploaded = EXCLUDED.videos_uploaded,
                    total_views = EXCLUDED.total_views,
                    avg_ctr = EXCLUDED.avg_ctr,
                    avg_retention = EXCLUDED.avg_retention,
                    report_json = EXCLUDED.report_json,
                    report_markdown = EXCLUDED.report_markdown
            """), {
                "date": today,
                "produced": videos_produced,
                "uploaded": videos_uploaded,
                "views": total_views,
                "ctr": avg_ctr,
                "retention": avg_retention,
                "json": json.dumps(report),
                "markdown": markdown_report
            })
            session.commit()
        
        # Save to file
        reports_dir = os.path.join(self.media_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        with open(os.path.join(reports_dir, f"report_{today}.json"), "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        with open(os.path.join(reports_dir, f"report_{today}.md"), "w") as f:
            f.write(markdown_report)
        
        return report
    
    async def _generate_daily_recommendations(
        self,
        videos_produced: int,
        total_views: int,
        avg_ctr: float
    ) -> List[str]:
        """Generate daily recommendations."""
        recommendations = []
        
        if videos_produced == 0:
            recommendations.append("No videos produced today. Consider running the discovery pipeline.")
        
        if total_views < 1000 and videos_produced > 0:
            recommendations.append("Low view count. Consider promoting videos on more platforms.")
        
        if avg_ctr < 2.0 and avg_ctr > 0:
            recommendations.append("CTR below average. Consider A/B testing thumbnails and titles.")
        elif avg_ctr > 5.0:
            recommendations.append("Excellent CTR! Analyze what's working and replicate.")
        
        if not recommendations:
            recommendations.append("Performance looks good. Keep up the consistent uploads!")
        
        return recommendations
    
    def _format_markdown_report(self, report: Dict[str, Any]) -> str:
        """Format report as Markdown."""
        summary = report["summary"]
        
        md = f"""# Daily Report - {report['date']}

## Summary

| Metric | Value |
|--------|-------|
| Videos Produced | {summary['videos_produced']} |
| Videos Uploaded | {summary['videos_uploaded']} |
| Total Views | {summary['total_views']:,} |
| Average CTR | {summary['avg_ctr']}% |
| Average Retention | {summary['avg_retention']}% |

## Recent Uploads

"""
        
        for upload in report.get("recent_uploads", []):
            md += f"- **{upload.get('title', 'Untitled')}**\n"
            md += f"  - Views: {upload.get('views', 0):,}\n"
            md += f"  - Likes: {upload.get('likes', 0):,}\n"
            md += f"  - URL: https://youtube.com/watch?v={upload.get('youtube_video_id', '')}\n\n"
        
        md += "## Recommendations\n\n"
        for rec in report.get("recommendations", []):
            md += f"- {rec}\n"
        
        return md
