"""
Telegram Bot Integration Module
Provides notifications, reports, and pipeline control via Telegram.
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import httpx
from functools import wraps


class TelegramBot:
    """
    Telegram bot for YouTube automation notifications and control.
    
    Features:
    - Video publish notifications
    - Daily/weekly revenue reports
    - Pipeline status updates
    - Control commands (retry, cancel, schedule)
    - Error alerts
    - Performance summaries
    """
    
    def __init__(self, db, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.db = db
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_base = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Command handlers
        self.commands: Dict[str, Callable] = {}
        self._register_default_commands()
        
        # Notification settings
        self.notify_on_publish = True
        self.notify_on_error = True
        self.notify_on_milestone = True
        self.daily_report_hour = 9  # 9 AM
        
    def _register_default_commands(self):
        """Register default bot commands."""
        self.commands = {
            "/status": self._cmd_status,
            "/queue": self._cmd_queue,
            "/stats": self._cmd_stats,
            "/today": self._cmd_today,
            "/week": self._cmd_week,
            "/retry": self._cmd_retry,
            "/cancel": self._cmd_cancel,
            "/schedule": self._cmd_schedule,
            "/shorts": self._cmd_shorts,
            "/help": self._cmd_help,
        }
        
    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        reply_markup: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send a message to Telegram."""
        if not self.token:
            return {"ok": False, "error": "No bot token configured"}
            
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return {"ok": False, "error": "No chat ID configured"}
            
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }
        
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
            
        try:
            response = await self.client.post(
                f"{self.api_base}/sendMessage",
                json=payload
            )
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
            
    async def send_photo(
        self,
        photo_url: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a photo to Telegram."""
        if not self.token:
            return {"ok": False, "error": "No bot token configured"}
            
        target_chat = chat_id or self.chat_id
        
        payload = {
            "chat_id": target_chat,
            "photo": photo_url,
        }
        
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = "HTML"
            
        try:
            response = await self.client.post(
                f"{self.api_base}/sendPhoto",
                json=payload
            )
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
            
    async def notify_video_published(
        self,
        video_id: str,
        title: str,
        youtube_url: str,
        thumbnail_url: Optional[str] = None,
        views_estimate: Optional[int] = None
    ):
        """Send notification when a video is published."""
        if not self.notify_on_publish:
            return
            
        message = (
            f"🎬 <b>Video Published!</b>\n\n"
            f"<b>{title}</b>\n\n"
            f"🔗 {youtube_url}\n"
        )
        
        if views_estimate:
            message += f"📊 Estimated first-day views: {views_estimate:,}\n"
            
        message += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        if thumbnail_url:
            await self.send_photo(thumbnail_url, caption=message)
        else:
            await self.send_message(message)
            
    async def notify_error(
        self,
        video_id: str,
        error_type: str,
        error_message: str,
        stage: str
    ):
        """Send notification when an error occurs."""
        if not self.notify_on_error:
            return
            
        message = (
            f"⚠️ <b>Pipeline Error</b>\n\n"
            f"<b>Video ID:</b> {video_id}\n"
            f"<b>Stage:</b> {stage}\n"
            f"<b>Error:</b> {error_type}\n\n"
            f"<code>{error_message[:500]}</code>\n\n"
            f"Use /retry {video_id} to retry"
        )
        
        await self.send_message(message)
        
    async def notify_milestone(
        self,
        milestone_type: str,
        value: Any,
        details: Optional[str] = None
    ):
        """Send notification for milestones (views, revenue, subscribers)."""
        if not self.notify_on_milestone:
            return
            
        emoji_map = {
            "views": "👀",
            "revenue": "💰",
            "subscribers": "👥",
            "videos": "🎬",
        }
        
        emoji = emoji_map.get(milestone_type, "🎉")
        
        message = (
            f"{emoji} <b>Milestone Reached!</b>\n\n"
            f"<b>{milestone_type.title()}:</b> {value:,}\n"
        )
        
        if details:
            message += f"\n{details}"
            
        await self.send_message(message)
        
    async def send_daily_report(self):
        """Send daily performance report."""
        try:
            # Get yesterday's stats
            yesterday = datetime.now() - timedelta(days=1)
            
            stats = await self.db.fetchrow("""
                SELECT 
                    COUNT(*) as videos_published,
                    SUM(views) as total_views,
                    SUM(revenue) as total_revenue,
                    AVG(ctr) as avg_ctr
                FROM metrics
                WHERE date = $1
            """, yesterday.date())
            
            # Get top video
            top_video = await self.db.fetchrow("""
                SELECT v.title, m.views, m.revenue
                FROM metrics m
                JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
                JOIN videos v ON u.video_id = v.id
                WHERE m.date = $1
                ORDER BY m.views DESC
                LIMIT 1
            """, yesterday.date())
            
            message = (
                f"📊 <b>Daily Report - {yesterday.strftime('%Y-%m-%d')}</b>\n\n"
                f"🎬 Videos Published: {stats['videos_published'] or 0}\n"
                f"👀 Total Views: {stats['total_views'] or 0:,}\n"
                f"💰 Revenue: ${stats['total_revenue'] or 0:.2f}\n"
                f"📈 Avg CTR: {(stats['avg_ctr'] or 0) * 100:.1f}%\n"
            )
            
            if top_video:
                message += (
                    f"\n🏆 <b>Top Video:</b>\n"
                    f"{top_video['title']}\n"
                    f"Views: {top_video['views']:,} | ${top_video['revenue']:.2f}"
                )
                
            await self.send_message(message)
            
        except Exception as e:
            await self.send_message(f"❌ Error generating daily report: {str(e)}")
            
    async def send_weekly_report(self):
        """Send weekly performance summary."""
        try:
            week_ago = datetime.now() - timedelta(days=7)
            
            stats = await self.db.fetchrow("""
                SELECT 
                    COUNT(DISTINCT u.youtube_video_id) as videos_published,
                    SUM(m.views) as total_views,
                    SUM(m.revenue) as total_revenue,
                    AVG(m.ctr) as avg_ctr,
                    AVG(m.avg_view_duration) as avg_duration
                FROM metrics m
                JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
                WHERE m.date >= $1
            """, week_ago.date())
            
            # Get growth comparison
            prev_week = await self.db.fetchrow("""
                SELECT 
                    SUM(views) as total_views,
                    SUM(revenue) as total_revenue
                FROM metrics
                WHERE date >= $1 AND date < $2
            """, (week_ago - timedelta(days=7)).date(), week_ago.date())
            
            views_growth = 0
            revenue_growth = 0
            if prev_week and prev_week['total_views']:
                views_growth = ((stats['total_views'] or 0) - prev_week['total_views']) / prev_week['total_views'] * 100
            if prev_week and prev_week['total_revenue']:
                revenue_growth = ((stats['total_revenue'] or 0) - prev_week['total_revenue']) / prev_week['total_revenue'] * 100
                
            views_arrow = "📈" if views_growth >= 0 else "📉"
            revenue_arrow = "📈" if revenue_growth >= 0 else "📉"
            
            message = (
                f"📊 <b>Weekly Report</b>\n"
                f"<i>{week_ago.strftime('%b %d')} - {datetime.now().strftime('%b %d, %Y')}</i>\n\n"
                f"🎬 Videos: {stats['videos_published'] or 0}\n"
                f"👀 Views: {stats['total_views'] or 0:,} {views_arrow} {views_growth:+.1f}%\n"
                f"💰 Revenue: ${stats['total_revenue'] or 0:.2f} {revenue_arrow} {revenue_growth:+.1f}%\n"
                f"📈 Avg CTR: {(stats['avg_ctr'] or 0) * 100:.1f}%\n"
                f"⏱️ Avg Watch: {stats['avg_duration'] or 0:.0f}s\n"
            )
            
            await self.send_message(message)
            
        except Exception as e:
            await self.send_message(f"❌ Error generating weekly report: {str(e)}")
            
    async def handle_update(self, update: Dict[str, Any]):
        """Handle incoming Telegram update (webhook or polling)."""
        if "message" not in update:
            return
            
        message = update["message"]
        text = message.get("text", "")
        chat_id = str(message["chat"]["id"])
        
        # Parse command
        if text.startswith("/"):
            parts = text.split()
            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            if command in self.commands:
                await self.commands[command](chat_id, args)
            else:
                await self.send_message(
                    "❓ Unknown command. Use /help for available commands.",
                    chat_id=chat_id
                )
                
    async def _cmd_status(self, chat_id: str, args: List[str]):
        """Get current pipeline status."""
        try:
            # Get queue counts
            queue = await self.db.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'processing') as processing,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed
                FROM videos
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            
            # Get next scheduled
            next_scheduled = await self.db.fetchrow("""
                SELECT scheduled_time, v.title
                FROM schedule s
                JOIN videos v ON s.video_id = v.id
                WHERE s.status = 'pending'
                ORDER BY scheduled_time
                LIMIT 1
            """)
            
            message = (
                f"📊 <b>Pipeline Status</b>\n\n"
                f"🔄 Processing: {queue['processing'] or 0}\n"
                f"⏳ Pending: {queue['pending'] or 0}\n"
                f"✅ Completed: {queue['completed'] or 0}\n"
                f"❌ Failed: {queue['failed'] or 0}\n"
            )
            
            if next_scheduled:
                message += (
                    f"\n⏰ <b>Next Scheduled:</b>\n"
                    f"{next_scheduled['title'][:50]}...\n"
                    f"At: {next_scheduled['scheduled_time'].strftime('%Y-%m-%d %H:%M')}"
                )
                
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_queue(self, chat_id: str, args: List[str]):
        """Get current video queue."""
        try:
            videos = await self.db.fetch("""
                SELECT id, title, status, progress
                FROM videos
                WHERE status IN ('processing', 'pending')
                ORDER BY created_at DESC
                LIMIT 10
            """)
            
            if not videos:
                await self.send_message("📭 Queue is empty!", chat_id=chat_id)
                return
                
            message = "📋 <b>Video Queue</b>\n\n"
            
            status_emoji = {
                "processing": "🔄",
                "pending": "⏳",
            }
            
            for v in videos:
                emoji = status_emoji.get(v['status'], "❓")
                progress = f" ({v['progress']}%)" if v['progress'] else ""
                title = v['title'][:40] + "..." if len(v['title']) > 40 else v['title']
                message += f"{emoji} {title}{progress}\n"
                
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_stats(self, chat_id: str, args: List[str]):
        """Get overall channel statistics."""
        try:
            stats = await self.db.fetchrow("""
                SELECT 
                    SUM(views) as total_views,
                    SUM(revenue) as total_revenue,
                    COUNT(DISTINCT youtube_video_id) as total_videos
                FROM metrics
            """)
            
            message = (
                f"📈 <b>Channel Statistics</b>\n\n"
                f"🎬 Total Videos: {stats['total_videos'] or 0}\n"
                f"👀 Total Views: {stats['total_views'] or 0:,}\n"
                f"💰 Total Revenue: ${stats['total_revenue'] or 0:.2f}\n"
            )
            
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_today(self, chat_id: str, args: List[str]):
        """Get today's statistics."""
        try:
            today = datetime.now().date()
            
            stats = await self.db.fetchrow("""
                SELECT 
                    COUNT(*) as videos,
                    SUM(views) as views,
                    SUM(revenue) as revenue
                FROM metrics
                WHERE date = $1
            """, today)
            
            message = (
                f"📊 <b>Today's Stats</b>\n\n"
                f"🎬 Videos: {stats['videos'] or 0}\n"
                f"👀 Views: {stats['views'] or 0:,}\n"
                f"💰 Revenue: ${stats['revenue'] or 0:.2f}\n"
            )
            
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_week(self, chat_id: str, args: List[str]):
        """Get this week's statistics."""
        await self.send_weekly_report()
        
    async def _cmd_retry(self, chat_id: str, args: List[str]):
        """Retry a failed video."""
        if not args:
            await self.send_message(
                "Usage: /retry <video_id>",
                chat_id=chat_id
            )
            return
            
        video_id = args[0]
        
        try:
            await self.db.execute(
                "UPDATE videos SET status = 'pending', error = NULL WHERE id = $1",
                video_id
            )
            await self.send_message(
                f"🔄 Video {video_id} queued for retry!",
                chat_id=chat_id
            )
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_cancel(self, chat_id: str, args: List[str]):
        """Cancel a scheduled video."""
        if not args:
            await self.send_message(
                "Usage: /cancel <schedule_id>",
                chat_id=chat_id
            )
            return
            
        schedule_id = args[0]
        
        try:
            await self.db.execute(
                "UPDATE schedule SET status = 'cancelled' WHERE id = $1",
                int(schedule_id)
            )
            await self.send_message(
                f"❌ Schedule {schedule_id} cancelled!",
                chat_id=chat_id
            )
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_schedule(self, chat_id: str, args: List[str]):
        """View upcoming schedule."""
        try:
            schedule = await self.db.fetch("""
                SELECT s.id, s.scheduled_time, v.title
                FROM schedule s
                JOIN videos v ON s.video_id = v.id
                WHERE s.status = 'pending'
                ORDER BY s.scheduled_time
                LIMIT 10
            """)
            
            if not schedule:
                await self.send_message("📭 No scheduled videos!", chat_id=chat_id)
                return
                
            message = "📅 <b>Upcoming Schedule</b>\n\n"
            
            for s in schedule:
                time_str = s['scheduled_time'].strftime('%m/%d %H:%M')
                title = s['title'][:35] + "..." if len(s['title']) > 35 else s['title']
                message += f"⏰ {time_str} - {title}\n"
                
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_shorts(self, chat_id: str, args: List[str]):
        """Get Shorts performance."""
        try:
            stats = await self.db.fetchrow("""
                SELECT 
                    COUNT(*) as total_shorts,
                    SUM(views) as total_views,
                    AVG(views) as avg_views
                FROM shorts_metrics
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """)
            
            message = (
                f"📱 <b>Shorts Performance (7 days)</b>\n\n"
                f"🎬 Total Shorts: {stats['total_shorts'] or 0}\n"
                f"👀 Total Views: {stats['total_views'] or 0:,}\n"
                f"📊 Avg Views: {stats['avg_views'] or 0:,.0f}\n"
            )
            
            await self.send_message(message, chat_id=chat_id)
            
        except Exception as e:
            await self.send_message(f"❌ Error: {str(e)}", chat_id=chat_id)
            
    async def _cmd_help(self, chat_id: str, args: List[str]):
        """Show help message."""
        message = (
            "🤖 <b>Amharic Recap Autopilot Bot</b>\n\n"
            "<b>Commands:</b>\n"
            "/status - Pipeline status\n"
            "/queue - Video queue\n"
            "/stats - Overall statistics\n"
            "/today - Today's stats\n"
            "/week - Weekly report\n"
            "/schedule - Upcoming schedule\n"
            "/shorts - Shorts performance\n"
            "/retry <id> - Retry failed video\n"
            "/cancel <id> - Cancel scheduled video\n"
            "/help - This message\n"
        )
        
        await self.send_message(message, chat_id=chat_id)
        
    async def start_polling(self, interval: int = 5):
        """Start polling for updates (for development/testing)."""
        offset = 0
        
        while True:
            try:
                response = await self.client.get(
                    f"{self.api_base}/getUpdates",
                    params={"offset": offset, "timeout": 30}
                )
                data = response.json()
                
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        offset = update["update_id"] + 1
                        await self.handle_update(update)
                        
            except Exception as e:
                print(f"Polling error: {e}")
                
            await asyncio.sleep(interval)
            
    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Set webhook URL for receiving updates."""
        try:
            response = await self.client.post(
                f"{self.api_base}/setWebhook",
                json={"url": webhook_url}
            )
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}
            
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class TelegramNotifier:
    """
    Simplified notifier for integration with other modules.
    Use this when you just need to send notifications without full bot functionality.
    """
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.api_base = f"https://api.telegram.org/bot{self.token}"
        
    async def notify(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a simple notification."""
        if not self.token or not self.chat_id:
            return False
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_base}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode
                    }
                )
                return response.json().get("ok", False)
            except Exception:
                return False
                
    async def notify_success(self, title: str, details: str = ""):
        """Send success notification."""
        message = f"✅ <b>{title}</b>"
        if details:
            message += f"\n\n{details}"
        return await self.notify(message)
        
    async def notify_error(self, title: str, error: str):
        """Send error notification."""
        message = f"❌ <b>{title}</b>\n\n<code>{error[:500]}</code>"
        return await self.notify(message)
        
    async def notify_info(self, title: str, details: str = ""):
        """Send info notification."""
        message = f"ℹ️ <b>{title}</b>"
        if details:
            message += f"\n\n{details}"
        return await self.notify(message)
