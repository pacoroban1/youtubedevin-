"""
Revenue Optimizer Engine
Real-time RPM tracking, cost analysis, and profit optimization.
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict


class RevenueOptimizer:
    """
    Optimizes revenue across languages, niches, and content types.
    
    Features:
    - Real-time RPM tracking by language/niche
    - Cost vs revenue analysis
    - Profit margin optimization
    - Content prioritization
    - ROI calculations
    - Revenue forecasting
    """
    
    def __init__(self, db):
        self.db = db
        
        # Cost configurations
        self.costs = {
            "translation_per_1k_words": 0.02,
            "tts_elevenlabs_per_char": 0.00003,
            "tts_azure_per_char": 0.000016,
            "image_generation_per_image": 0.02,
            "video_editing_per_minute": 0.10,
            "storage_per_gb_month": 0.023,
            "bandwidth_per_gb": 0.09,
        }
        
        # Revenue targets
        self.targets = {
            "min_profit_margin": 0.50,  # 50%
            "target_profit_margin": 0.70,  # 70%
            "min_rpm": 2.0,
            "target_rpm": 5.0,
        }
        
    async def get_rpm_by_language(
        self,
        days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get RPM breakdown by language.
        
        Returns:
            RPM data per language with trends
        """
        query = """
            SELECT 
                language,
                AVG(revenue / NULLIF(views, 0) * 1000) as rpm,
                SUM(views) as total_views,
                SUM(revenue) as total_revenue,
                COUNT(*) as video_count
            FROM metrics m
            JOIN video_translations vt ON m.youtube_video_id = vt.youtube_video_id
            WHERE m.date >= NOW() - INTERVAL '%s days'
            GROUP BY language
            ORDER BY rpm DESC
        """ % days
        
        rows = await self.db.fetch(query)
        
        results = {}
        for row in rows:
            lang = row["language"]
            results[lang] = {
                "rpm": round(float(row["rpm"] or 0), 2),
                "total_views": int(row["total_views"] or 0),
                "total_revenue": round(float(row["total_revenue"] or 0), 2),
                "video_count": int(row["video_count"] or 0),
            }
            
            # Calculate trend (compare to previous period)
            prev_rpm = await self._get_previous_rpm(lang, days)
            if prev_rpm > 0:
                trend = ((results[lang]["rpm"] - prev_rpm) / prev_rpm) * 100
                results[lang]["trend"] = round(trend, 1)
            else:
                results[lang]["trend"] = 0
                
        return results
        
    async def _get_previous_rpm(self, language: str, days: int) -> float:
        """Get RPM from previous period for comparison."""
        query = """
            SELECT AVG(revenue / NULLIF(views, 0) * 1000) as rpm
            FROM metrics m
            JOIN video_translations vt ON m.youtube_video_id = vt.youtube_video_id
            WHERE vt.language = $1
              AND m.date >= NOW() - INTERVAL '%s days' - INTERVAL '%s days'
              AND m.date < NOW() - INTERVAL '%s days'
        """ % (days, days, days)
        
        result = await self.db.fetchval(query, language)
        return float(result or 0)
        
    async def get_rpm_by_niche(
        self,
        days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get RPM breakdown by niche/category.
        
        Returns:
            RPM data per niche
        """
        query = """
            SELECT 
                v.niche,
                AVG(m.revenue / NULLIF(m.views, 0) * 1000) as rpm,
                SUM(m.views) as total_views,
                SUM(m.revenue) as total_revenue,
                COUNT(*) as video_count
            FROM metrics m
            JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
            JOIN videos v ON u.video_id = v.id
            WHERE m.date >= NOW() - INTERVAL '%s days'
              AND v.niche IS NOT NULL
            GROUP BY v.niche
            ORDER BY rpm DESC
        """ % days
        
        rows = await self.db.fetch(query)
        
        results = {}
        for row in rows:
            niche = row["niche"]
            results[niche] = {
                "rpm": round(float(row["rpm"] or 0), 2),
                "total_views": int(row["total_views"] or 0),
                "total_revenue": round(float(row["total_revenue"] or 0), 2),
                "video_count": int(row["video_count"] or 0),
            }
            
        return results
        
    async def calculate_video_cost(
        self,
        video_id: str
    ) -> Dict[str, float]:
        """
        Calculate total cost for producing a video.
        
        Returns:
            Cost breakdown by category
        """
        # Get video details
        video = await self.db.fetchrow("""
            SELECT 
                v.*,
                (SELECT COUNT(*) FROM video_translations WHERE video_id = v.id) as translation_count,
                (SELECT SUM(LENGTH(script)) FROM video_translations WHERE video_id = v.id) as total_chars
            FROM videos v
            WHERE v.id = $1
        """, video_id)
        
        if not video:
            return {"total": 0}
            
        costs = {}
        
        # Script/translation costs
        script_length = len(video.get("script", "") or "")
        word_count = script_length / 5  # Approximate words
        translation_count = video.get("translation_count", 0)
        
        costs["translation"] = round(
            (word_count / 1000) * self.costs["translation_per_1k_words"] * translation_count,
            2
        )
        
        # TTS costs
        total_chars = video.get("total_chars", 0) or script_length
        costs["tts"] = round(
            total_chars * self.costs["tts_azure_per_char"],
            2
        )
        
        # Image generation (thumbnails)
        costs["images"] = round(
            self.costs["image_generation_per_image"] * 4,  # 4 thumbnail variants
            2
        )
        
        # Video editing (based on duration)
        duration_minutes = video.get("duration", 600) / 60
        costs["editing"] = round(
            duration_minutes * self.costs["video_editing_per_minute"],
            2
        )
        
        # Storage
        file_size_gb = video.get("file_size", 500_000_000) / (1024**3)
        costs["storage"] = round(
            file_size_gb * self.costs["storage_per_gb_month"],
            2
        )
        
        costs["total"] = round(sum(costs.values()), 2)
        
        return costs
        
    async def calculate_profit_margin(
        self,
        video_id: str
    ) -> Dict[str, Any]:
        """
        Calculate profit margin for a video.
        
        Returns:
            Profit analysis with margin percentage
        """
        # Get costs
        costs = await self.calculate_video_cost(video_id)
        
        # Get revenue
        revenue = await self.db.fetchval("""
            SELECT SUM(m.revenue)
            FROM metrics m
            JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
            WHERE u.video_id = $1
        """, video_id)
        
        revenue = float(revenue or 0)
        total_cost = costs["total"]
        
        profit = revenue - total_cost
        margin = (profit / revenue * 100) if revenue > 0 else 0
        
        return {
            "video_id": video_id,
            "revenue": round(revenue, 2),
            "costs": costs,
            "profit": round(profit, 2),
            "margin_percent": round(margin, 1),
            "meets_target": margin >= self.targets["target_profit_margin"] * 100,
            "status": self._get_margin_status(margin)
        }
        
    def _get_margin_status(self, margin: float) -> str:
        """Get status based on profit margin."""
        if margin >= 70:
            return "excellent"
        elif margin >= 50:
            return "good"
        elif margin >= 30:
            return "acceptable"
        elif margin >= 0:
            return "low"
        else:
            return "loss"
            
    async def get_content_prioritization(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get prioritized content recommendations based on ROI.
        
        Returns:
            Ranked list of content opportunities
        """
        # Get language performance
        lang_rpm = await self.get_rpm_by_language(30)
        
        # Get niche performance
        niche_rpm = await self.get_rpm_by_niche(30)
        
        # Calculate opportunity scores
        opportunities = []
        
        for lang, lang_data in lang_rpm.items():
            for niche, niche_data in niche_rpm.items():
                # Combined RPM estimate
                combined_rpm = (lang_data["rpm"] + niche_data["rpm"]) / 2
                
                # Estimate cost
                estimated_cost = 5.0  # Base cost estimate
                
                # Calculate ROI score
                roi_score = combined_rpm / estimated_cost if estimated_cost > 0 else 0
                
                opportunities.append({
                    "language": lang,
                    "niche": niche,
                    "estimated_rpm": round(combined_rpm, 2),
                    "estimated_cost": estimated_cost,
                    "roi_score": round(roi_score, 2),
                    "recommendation": self._get_recommendation(roi_score, combined_rpm)
                })
                
        # Sort by ROI score
        opportunities.sort(key=lambda x: x["roi_score"], reverse=True)
        
        return opportunities[:limit]
        
    def _get_recommendation(self, roi_score: float, rpm: float) -> str:
        """Get recommendation based on ROI and RPM."""
        if roi_score > 2 and rpm > 5:
            return "HIGH PRIORITY - Excellent ROI and RPM"
        elif roi_score > 1.5 and rpm > 3:
            return "RECOMMENDED - Good potential"
        elif roi_score > 1:
            return "CONSIDER - Moderate opportunity"
        else:
            return "LOW PRIORITY - Limited potential"
            
    async def forecast_revenue(
        self,
        days_ahead: int = 30,
        videos_per_day: int = 2
    ) -> Dict[str, Any]:
        """
        Forecast revenue based on historical performance.
        
        Args:
            days_ahead: Days to forecast
            videos_per_day: Expected videos per day
            
        Returns:
            Revenue forecast with confidence intervals
        """
        # Get historical averages
        historical = await self.db.fetchrow("""
            SELECT 
                AVG(revenue) as avg_revenue_per_video,
                STDDEV(revenue) as stddev_revenue,
                AVG(views) as avg_views,
                AVG(revenue / NULLIF(views, 0) * 1000) as avg_rpm
            FROM metrics m
            JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
            WHERE m.date >= NOW() - INTERVAL '30 days'
        """)
        
        avg_revenue = float(historical["avg_revenue_per_video"] or 0)
        stddev = float(historical["stddev_revenue"] or avg_revenue * 0.3)
        avg_rpm = float(historical["avg_rpm"] or 3)
        
        total_videos = days_ahead * videos_per_day
        
        # Calculate forecasts
        expected_revenue = avg_revenue * total_videos
        low_estimate = (avg_revenue - stddev) * total_videos
        high_estimate = (avg_revenue + stddev) * total_videos
        
        return {
            "period_days": days_ahead,
            "videos_planned": total_videos,
            "avg_revenue_per_video": round(avg_revenue, 2),
            "avg_rpm": round(avg_rpm, 2),
            "forecast": {
                "expected": round(expected_revenue, 2),
                "low": round(max(0, low_estimate), 2),
                "high": round(high_estimate, 2),
            },
            "confidence": "Based on 30-day historical data"
        }
        
    async def get_optimization_suggestions(self) -> List[Dict[str, str]]:
        """
        Generate optimization suggestions based on data.
        
        Returns:
            List of actionable suggestions
        """
        suggestions = []
        
        # Check language performance
        lang_rpm = await self.get_rpm_by_language(30)
        
        # Find underperforming languages
        for lang, data in lang_rpm.items():
            if data["rpm"] < self.targets["min_rpm"] and data["video_count"] > 5:
                suggestions.append({
                    "type": "language",
                    "priority": "high",
                    "suggestion": f"Consider reducing content in {lang} (RPM: ${data['rpm']:.2f}). Focus on higher RPM languages.",
                    "potential_impact": f"Could improve overall RPM by focusing on better performing languages"
                })
                
        # Find high performers to scale
        top_langs = sorted(lang_rpm.items(), key=lambda x: x[1]["rpm"], reverse=True)[:3]
        for lang, data in top_langs:
            if data["rpm"] > self.targets["target_rpm"]:
                suggestions.append({
                    "type": "language",
                    "priority": "medium",
                    "suggestion": f"Scale up content in {lang} (RPM: ${data['rpm']:.2f}). High performing language.",
                    "potential_impact": f"Estimated +${data['rpm'] * 1000:.0f} per 1M views"
                })
                
        # Check niche performance
        niche_rpm = await self.get_rpm_by_niche(30)
        
        top_niches = sorted(niche_rpm.items(), key=lambda x: x[1]["rpm"], reverse=True)[:3]
        for niche, data in top_niches:
            suggestions.append({
                "type": "niche",
                "priority": "medium",
                "suggestion": f"Focus on {niche} content (RPM: ${data['rpm']:.2f})",
                "potential_impact": f"Top performing niche with {data['video_count']} videos"
            })
            
        # Cost optimization
        suggestions.append({
            "type": "cost",
            "priority": "low",
            "suggestion": "Consider batch processing translations to reduce API costs",
            "potential_impact": "Could reduce translation costs by 20-30%"
        })
        
        return suggestions
        
    async def get_daily_report(self) -> Dict[str, Any]:
        """
        Generate daily revenue report.
        
        Returns:
            Comprehensive daily report
        """
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Today's stats
        today_stats = await self.db.fetchrow("""
            SELECT 
                SUM(views) as views,
                SUM(revenue) as revenue,
                COUNT(DISTINCT youtube_video_id) as videos
            FROM metrics
            WHERE date = $1
        """, today)
        
        # Yesterday's stats for comparison
        yesterday_stats = await self.db.fetchrow("""
            SELECT 
                SUM(views) as views,
                SUM(revenue) as revenue
            FROM metrics
            WHERE date = $1
        """, yesterday)
        
        # Calculate changes
        today_revenue = float(today_stats["revenue"] or 0)
        yesterday_revenue = float(yesterday_stats["revenue"] or 0)
        
        revenue_change = 0
        if yesterday_revenue > 0:
            revenue_change = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
            
        # Get top performers
        top_videos = await self.db.fetch("""
            SELECT 
                v.title,
                m.views,
                m.revenue,
                m.revenue / NULLIF(m.views, 0) * 1000 as rpm
            FROM metrics m
            JOIN uploads u ON m.youtube_video_id = u.youtube_video_id
            JOIN videos v ON u.video_id = v.id
            WHERE m.date = $1
            ORDER BY m.revenue DESC
            LIMIT 5
        """, today)
        
        return {
            "date": today.isoformat(),
            "summary": {
                "views": int(today_stats["views"] or 0),
                "revenue": round(today_revenue, 2),
                "videos_active": int(today_stats["videos"] or 0),
                "revenue_change_percent": round(revenue_change, 1)
            },
            "top_performers": [
                {
                    "title": v["title"][:50],
                    "views": int(v["views"] or 0),
                    "revenue": round(float(v["revenue"] or 0), 2),
                    "rpm": round(float(v["rpm"] or 0), 2)
                }
                for v in top_videos
            ],
            "generated_at": datetime.now().isoformat()
        }
        
    async def get_monthly_summary(
        self,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """
        Generate monthly revenue summary.
        
        Returns:
            Monthly summary with trends
        """
        from calendar import monthrange
        
        start_date = datetime(year, month, 1).date()
        _, last_day = monthrange(year, month)
        end_date = datetime(year, month, last_day).date()
        
        # Monthly totals
        monthly = await self.db.fetchrow("""
            SELECT 
                SUM(views) as total_views,
                SUM(revenue) as total_revenue,
                COUNT(DISTINCT youtube_video_id) as total_videos,
                AVG(revenue / NULLIF(views, 0) * 1000) as avg_rpm
            FROM metrics
            WHERE date >= $1 AND date <= $2
        """, start_date, end_date)
        
        # Daily breakdown
        daily = await self.db.fetch("""
            SELECT 
                date,
                SUM(views) as views,
                SUM(revenue) as revenue
            FROM metrics
            WHERE date >= $1 AND date <= $2
            GROUP BY date
            ORDER BY date
        """, start_date, end_date)
        
        return {
            "period": f"{year}-{month:02d}",
            "summary": {
                "total_views": int(monthly["total_views"] or 0),
                "total_revenue": round(float(monthly["total_revenue"] or 0), 2),
                "total_videos": int(monthly["total_videos"] or 0),
                "avg_rpm": round(float(monthly["avg_rpm"] or 0), 2),
                "avg_daily_revenue": round(float(monthly["total_revenue"] or 0) / last_day, 2)
            },
            "daily_data": [
                {
                    "date": d["date"].isoformat(),
                    "views": int(d["views"] or 0),
                    "revenue": round(float(d["revenue"] or 0), 2)
                }
                for d in daily
            ]
        }
