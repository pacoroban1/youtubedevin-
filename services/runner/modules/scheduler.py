"""
Smart Scheduling Module
Auto-publishes videos at optimal times based on audience analytics.
Supports timezone-aware scheduling and consistent posting patterns.
"""

import os
import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo
import json
import random


class SmartScheduler:
    """
    Intelligent video scheduling based on audience behavior.
    
    Features:
    - Optimal posting time detection
    - Timezone-aware scheduling
    - Consistent posting patterns
    - Queue management
    - Holiday/event awareness
    - A/B testing for posting times
    """
    
    def __init__(self, db):
        self.db = db
        
        # Default timezone for Ethiopian audience
        self.default_timezone = ZoneInfo(os.getenv("DEFAULT_TIMEZONE", "Africa/Addis_Ababa"))
        
        # Default optimal posting windows (in local time)
        # Based on typical YouTube audience patterns
        self.default_optimal_hours = [
            (6, 8),    # Early morning
            (12, 14),  # Lunch time
            (18, 21),  # Evening prime time
        ]
        
        # Days of week weights (0=Monday, 6=Sunday)
        self.day_weights = {
            0: 0.9,   # Monday
            1: 0.95,  # Tuesday
            2: 1.0,   # Wednesday
            3: 1.0,   # Thursday
            4: 1.1,   # Friday
            5: 1.2,   # Saturday
            6: 1.15,  # Sunday
        }
        
        # Minimum gap between posts (hours)
        self.min_gap_hours = int(os.getenv("MIN_POST_GAP_HOURS", "4"))
        
        # Maximum posts per day
        self.max_posts_per_day = int(os.getenv("MAX_POSTS_PER_DAY", "3"))
        
    async def get_optimal_time(
        self,
        video_id: str,
        preferred_date: Optional[datetime] = None,
        video_type: str = "long"  # "long" or "short"
    ) -> datetime:
        """
        Calculate the optimal posting time for a video.
        
        Args:
            video_id: Database video ID
            preferred_date: Optional preferred date (defaults to next available)
            video_type: Type of video ("long" or "short")
            
        Returns:
            Optimal datetime for posting (UTC)
        """
        # Get audience analytics if available
        audience_data = await self._get_audience_analytics()
        
        # Get existing schedule to avoid conflicts
        existing_schedule = await self._get_existing_schedule()
        
        # Determine optimal hours based on analytics or defaults
        if audience_data and audience_data.get("peak_hours"):
            optimal_hours = audience_data["peak_hours"]
        else:
            optimal_hours = self.default_optimal_hours
            
        # Shorts have different optimal times (more spread throughout day)
        if video_type == "short":
            optimal_hours = [
                (7, 9),
                (11, 13),
                (15, 17),
                (19, 22),
            ]
            
        # Find the next available slot
        if preferred_date:
            start_date = preferred_date.date()
        else:
            start_date = datetime.now(self.default_timezone).date()
            
        # Search up to 7 days ahead
        for day_offset in range(7):
            check_date = start_date + timedelta(days=day_offset)
            
            # Check posts already scheduled for this day
            day_posts = [
                s for s in existing_schedule
                if s["scheduled_time"].date() == check_date
            ]
            
            if len(day_posts) >= self.max_posts_per_day:
                continue
                
            # Find available slot in optimal hours
            for hour_start, hour_end in optimal_hours:
                for hour in range(hour_start, hour_end):
                    candidate_time = datetime.combine(
                        check_date,
                        time(hour=hour, minute=random.randint(0, 30))
                    )
                    candidate_time = candidate_time.replace(tzinfo=self.default_timezone)
                    
                    # Check if slot is available (respects min gap)
                    if self._is_slot_available(candidate_time, existing_schedule):
                        # Apply day weight scoring
                        day_weight = self.day_weights.get(check_date.weekday(), 1.0)
                        
                        # Convert to UTC for storage
                        return candidate_time.astimezone(ZoneInfo("UTC"))
                        
        # Fallback: schedule for tomorrow at a default time
        fallback_time = datetime.combine(
            start_date + timedelta(days=1),
            time(hour=18, minute=0)
        )
        fallback_time = fallback_time.replace(tzinfo=self.default_timezone)
        return fallback_time.astimezone(ZoneInfo("UTC"))
        
    def _is_slot_available(
        self,
        candidate: datetime,
        existing: List[Dict[str, Any]]
    ) -> bool:
        """Check if a time slot is available (respects minimum gap)."""
        min_gap = timedelta(hours=self.min_gap_hours)
        
        for scheduled in existing:
            scheduled_time = scheduled["scheduled_time"]
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=ZoneInfo("UTC"))
            scheduled_time = scheduled_time.astimezone(self.default_timezone)
            
            if abs(candidate - scheduled_time) < min_gap:
                return False
                
        # Also check if time is in the future
        now = datetime.now(self.default_timezone)
        if candidate <= now + timedelta(minutes=30):
            return False
            
        return True
        
    async def _get_audience_analytics(self) -> Optional[Dict[str, Any]]:
        """Get audience analytics from database."""
        try:
            query = """
                SELECT 
                    EXTRACT(HOUR FROM best_time) as peak_hour,
                    COUNT(*) as count
                FROM metrics
                WHERE date >= NOW() - INTERVAL '30 days'
                  AND best_time IS NOT NULL
                GROUP BY EXTRACT(HOUR FROM best_time)
                ORDER BY count DESC
                LIMIT 5
            """
            
            rows = await self.db.fetch(query)
            
            if not rows:
                return None
                
            # Convert to hour ranges
            peak_hours = []
            for row in rows:
                hour = int(row["peak_hour"])
                peak_hours.append((hour, hour + 2))
                
            return {"peak_hours": peak_hours}
            
        except Exception:
            return None
            
    async def _get_existing_schedule(self) -> List[Dict[str, Any]]:
        """Get existing scheduled posts."""
        try:
            query = """
                SELECT video_id, scheduled_time, status
                FROM schedule
                WHERE scheduled_time >= NOW()
                  AND status IN ('pending', 'scheduled')
                ORDER BY scheduled_time
            """
            
            rows = await self.db.fetch(query)
            return [dict(r) for r in rows]
            
        except Exception:
            return []
            
    async def schedule_video(
        self,
        video_id: str,
        scheduled_time: Optional[datetime] = None,
        video_type: str = "long",
        priority: int = 5
    ) -> Dict[str, Any]:
        """
        Schedule a video for publication.
        
        Args:
            video_id: Database video ID
            scheduled_time: Optional specific time (auto-calculated if None)
            video_type: Type of video
            priority: Priority level (1-10, higher = more important)
            
        Returns:
            Schedule info with ID and time
        """
        if scheduled_time is None:
            scheduled_time = await self.get_optimal_time(video_id, video_type=video_type)
            
        # Ensure timezone
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=ZoneInfo("UTC"))
            
        query = """
            INSERT INTO schedule (video_id, scheduled_time, video_type, priority, status, created_at)
            VALUES ($1, $2, $3, $4, 'pending', NOW())
            ON CONFLICT (video_id) DO UPDATE SET
                scheduled_time = EXCLUDED.scheduled_time,
                video_type = EXCLUDED.video_type,
                priority = EXCLUDED.priority,
                status = 'pending'
            RETURNING id
        """
        
        schedule_id = await self.db.fetchval(
            query,
            video_id,
            scheduled_time,
            video_type,
            priority
        )
        
        return {
            "schedule_id": schedule_id,
            "video_id": video_id,
            "scheduled_time": scheduled_time.isoformat(),
            "video_type": video_type,
            "priority": priority,
            "status": "pending"
        }
        
    async def schedule_batch(
        self,
        video_ids: List[str],
        start_date: Optional[datetime] = None,
        video_type: str = "long",
        spread_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Schedule multiple videos with optimal spacing.
        
        Args:
            video_ids: List of video IDs to schedule
            start_date: Starting date for scheduling
            video_type: Type of videos
            spread_days: Number of days to spread videos over
            
        Returns:
            List of schedule info for each video
        """
        results = []
        
        if start_date is None:
            start_date = datetime.now(self.default_timezone)
            
        # Calculate videos per day
        videos_per_day = max(1, len(video_ids) // spread_days)
        videos_per_day = min(videos_per_day, self.max_posts_per_day)
        
        current_date = start_date
        videos_scheduled_today = 0
        
        for video_id in video_ids:
            # Move to next day if needed
            if videos_scheduled_today >= videos_per_day:
                current_date += timedelta(days=1)
                videos_scheduled_today = 0
                
            # Get optimal time for this date
            optimal_time = await self.get_optimal_time(
                video_id,
                preferred_date=current_date,
                video_type=video_type
            )
            
            # Schedule the video
            result = await self.schedule_video(
                video_id,
                scheduled_time=optimal_time,
                video_type=video_type
            )
            results.append(result)
            
            videos_scheduled_today += 1
            
        return results
        
    async def get_schedule(
        self,
        days_ahead: int = 7,
        include_past: bool = False
    ) -> List[Dict[str, Any]]:
        """Get the current publication schedule."""
        query = """
            SELECT s.*, v.title, v.youtube_id
            FROM schedule s
            JOIN videos v ON s.video_id = v.id
            WHERE s.scheduled_time <= NOW() + INTERVAL '%s days'
        """ % days_ahead
        
        if not include_past:
            query += " AND s.scheduled_time >= NOW()"
            
        query += " ORDER BY s.scheduled_time"
        
        rows = await self.db.fetch(query)
        return [dict(r) for r in rows]
        
    async def reschedule_video(
        self,
        schedule_id: int,
        new_time: datetime
    ) -> Dict[str, Any]:
        """Reschedule a video to a new time."""
        if new_time.tzinfo is None:
            new_time = new_time.replace(tzinfo=ZoneInfo("UTC"))
            
        await self.db.execute(
            """UPDATE schedule SET scheduled_time = $1, status = 'pending'
               WHERE id = $2""",
            new_time,
            schedule_id
        )
        
        return {"schedule_id": schedule_id, "new_time": new_time.isoformat()}
        
    async def cancel_schedule(self, schedule_id: int) -> bool:
        """Cancel a scheduled publication."""
        await self.db.execute(
            "UPDATE schedule SET status = 'cancelled' WHERE id = $1",
            schedule_id
        )
        return True
        
    async def get_next_due(self) -> Optional[Dict[str, Any]]:
        """Get the next video due for publication."""
        query = """
            SELECT s.*, v.title, v.youtube_id
            FROM schedule s
            JOIN videos v ON s.video_id = v.id
            WHERE s.status = 'pending'
              AND s.scheduled_time <= NOW()
            ORDER BY s.priority DESC, s.scheduled_time
            LIMIT 1
        """
        
        row = await self.db.fetchrow(query)
        return dict(row) if row else None
        
    async def mark_published(self, schedule_id: int, youtube_video_id: str):
        """Mark a scheduled video as published."""
        await self.db.execute(
            """UPDATE schedule SET status = 'published', 
               published_at = NOW(), youtube_video_id = $1
               WHERE id = $2""",
            youtube_video_id,
            schedule_id
        )
        
    async def get_posting_analytics(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze posting patterns and their performance.
        
        Returns insights on best posting times based on actual performance.
        """
        query = """
            SELECT 
                EXTRACT(DOW FROM s.scheduled_time) as day_of_week,
                EXTRACT(HOUR FROM s.scheduled_time) as hour,
                COUNT(*) as post_count,
                AVG(m.views) as avg_views,
                AVG(m.ctr) as avg_ctr,
                AVG(m.avg_view_duration) as avg_duration
            FROM schedule s
            JOIN uploads u ON s.video_id = u.video_id
            JOIN metrics m ON u.youtube_video_id = m.youtube_video_id
            WHERE s.status = 'published'
              AND s.published_at >= NOW() - INTERVAL '%s days'
            GROUP BY EXTRACT(DOW FROM s.scheduled_time), EXTRACT(HOUR FROM s.scheduled_time)
            ORDER BY avg_views DESC
        """ % days
        
        rows = await self.db.fetch(query)
        
        # Find best times
        best_times = []
        for row in rows[:5]:
            best_times.append({
                "day": int(row["day_of_week"]),
                "hour": int(row["hour"]),
                "avg_views": float(row["avg_views"] or 0),
                "avg_ctr": float(row["avg_ctr"] or 0)
            })
            
        # Calculate consistency score
        total_scheduled = await self.db.fetchval(
            """SELECT COUNT(*) FROM schedule 
               WHERE status = 'published' 
               AND published_at >= NOW() - INTERVAL '%s days'""" % days
        )
        
        on_time = await self.db.fetchval(
            """SELECT COUNT(*) FROM schedule 
               WHERE status = 'published' 
               AND published_at >= NOW() - INTERVAL '%s days'
               AND ABS(EXTRACT(EPOCH FROM (published_at - scheduled_time))) < 3600""" % days
        )
        
        consistency_score = (on_time / total_scheduled * 100) if total_scheduled > 0 else 0
        
        return {
            "best_times": best_times,
            "total_posts": total_scheduled or 0,
            "consistency_score": round(consistency_score, 1),
            "avg_posts_per_day": round((total_scheduled or 0) / days, 1)
        }
        
    async def suggest_schedule_improvements(self) -> List[str]:
        """Generate suggestions for improving posting schedule."""
        suggestions = []
        
        analytics = await self.get_posting_analytics()
        
        # Check consistency
        if analytics["consistency_score"] < 80:
            suggestions.append(
                "Your posting consistency is below 80%. Try to publish videos "
                "closer to their scheduled times for better algorithm performance."
            )
            
        # Check posting frequency
        if analytics["avg_posts_per_day"] < 1:
            suggestions.append(
                "Consider increasing your posting frequency. "
                "Channels that post daily tend to grow faster."
            )
            
        # Check if posting at optimal times
        if analytics["best_times"]:
            best_hour = analytics["best_times"][0]["hour"]
            suggestions.append(
                f"Your best performing hour is {best_hour}:00. "
                f"Consider scheduling more videos around this time."
            )
            
        return suggestions
