"""
Viral Niche Detector Engine
ML-based trend prediction to find viral content BEFORE it peaks.
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import httpx
from collections import defaultdict


class ViralNicheDetector:
    """
    Detects viral niches and predicts trending content.
    
    Features:
    - Trend velocity analysis
    - Niche scoring and ranking
    - Concept variation suggestions
    - Competition analysis
    - Timing optimization
    """
    
    # Niche categories with base viral potential
    NICHE_CATEGORIES = {
        "recap": {"base_score": 8, "competition": "high", "rpm_range": (3, 8)},
        "quiz": {"base_score": 7, "competition": "medium", "rpm_range": (2, 6)},
        "walking_tour": {"base_score": 9, "competition": "low", "rpm_range": (15, 30)},
        "driving": {"base_score": 8, "competition": "low", "rpm_range": (10, 25)},
        "asmr": {"base_score": 6, "competition": "high", "rpm_range": (4, 10)},
        "compilation": {"base_score": 5, "competition": "very_high", "rpm_range": (1, 4)},
        "educational": {"base_score": 7, "competition": "medium", "rpm_range": (5, 12)},
        "news_recap": {"base_score": 8, "competition": "high", "rpm_range": (4, 10)},
        "sports_highlights": {"base_score": 6, "competition": "very_high", "rpm_range": (2, 6)},
        "gaming": {"base_score": 5, "competition": "very_high", "rpm_range": (2, 5)},
        "finance": {"base_score": 9, "competition": "medium", "rpm_range": (10, 25)},
        "tech_review": {"base_score": 7, "competition": "high", "rpm_range": (6, 15)},
        "true_crime": {"base_score": 8, "competition": "medium", "rpm_range": (5, 12)},
        "mystery": {"base_score": 8, "competition": "medium", "rpm_range": (5, 12)},
        "history": {"base_score": 7, "competition": "low", "rpm_range": (6, 15)},
        "science": {"base_score": 7, "competition": "medium", "rpm_range": (5, 12)},
        "nature": {"base_score": 8, "competition": "low", "rpm_range": (8, 20)},
        "relaxation": {"base_score": 7, "competition": "medium", "rpm_range": (6, 15)},
    }
    
    def __init__(self, db):
        self.db = db
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        self.trends_cache = {}
        self.cache_ttl = 3600  # 1 hour
        
    async def analyze_niche(
        self,
        niche: str,
        keywords: List[str],
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze a niche for viral potential.
        
        Args:
            niche: Niche category
            keywords: Related keywords
            days_back: Days of data to analyze
            
        Returns:
            Niche analysis with scores and recommendations
        """
        # Get base niche data
        niche_config = self.NICHE_CATEGORIES.get(niche, {
            "base_score": 5,
            "competition": "unknown",
            "rpm_range": (2, 8)
        })
        
        # Analyze trending videos
        trending_data = await self._get_trending_videos(keywords)
        
        # Calculate velocity (growth rate)
        velocity = await self._calculate_velocity(keywords, days_back)
        
        # Analyze competition
        competition = await self._analyze_competition(keywords)
        
        # Calculate viral score
        viral_score = self._calculate_viral_score(
            niche_config["base_score"],
            velocity,
            competition
        )
        
        # Generate concept variations
        variations = await self._generate_variations(niche, keywords)
        
        return {
            "niche": niche,
            "keywords": keywords,
            "viral_score": viral_score,
            "velocity": velocity,
            "competition": competition,
            "rpm_estimate": niche_config["rpm_range"],
            "trending_videos": trending_data[:5],
            "concept_variations": variations,
            "recommendation": self._get_recommendation(viral_score, competition),
            "best_posting_times": await self._get_best_times(niche),
            "analyzed_at": datetime.now().isoformat()
        }
        
    async def _get_trending_videos(
        self,
        keywords: List[str],
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """Get trending videos for keywords."""
        if not self.youtube_api_key:
            return []
            
        videos = []
        
        async with httpx.AsyncClient() as client:
            for keyword in keywords[:3]:  # Limit API calls
                try:
                    response = await client.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "key": self.youtube_api_key,
                            "q": keyword,
                            "part": "snippet",
                            "type": "video",
                            "order": "viewCount",
                            "publishedAfter": (datetime.now() - timedelta(days=7)).isoformat() + "Z",
                            "maxResults": max_results // len(keywords)
                        },
                        timeout=30.0
                    )
                    
                    data = response.json()
                    
                    for item in data.get("items", []):
                        videos.append({
                            "video_id": item["id"]["videoId"],
                            "title": item["snippet"]["title"],
                            "channel": item["snippet"]["channelTitle"],
                            "published": item["snippet"]["publishedAt"],
                            "keyword": keyword
                        })
                        
                except Exception as e:
                    print(f"Error fetching videos for {keyword}: {e}")
                    
        return videos
        
    async def _calculate_velocity(
        self,
        keywords: List[str],
        days_back: int
    ) -> Dict[str, Any]:
        """Calculate trend velocity (growth rate)."""
        # In production, this would use YouTube Analytics or Google Trends API
        # For now, we estimate based on video counts
        
        if not self.youtube_api_key:
            return {"score": 5, "trend": "stable"}
            
        recent_count = 0
        older_count = 0
        
        async with httpx.AsyncClient() as client:
            for keyword in keywords[:2]:
                try:
                    # Recent videos (last 7 days)
                    recent = await client.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "key": self.youtube_api_key,
                            "q": keyword,
                            "part": "id",
                            "type": "video",
                            "publishedAfter": (datetime.now() - timedelta(days=7)).isoformat() + "Z",
                            "maxResults": 50
                        },
                        timeout=30.0
                    )
                    recent_data = recent.json()
                    recent_count += len(recent_data.get("items", []))
                    
                    # Older videos (7-30 days ago)
                    older = await client.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "key": self.youtube_api_key,
                            "q": keyword,
                            "part": "id",
                            "type": "video",
                            "publishedAfter": (datetime.now() - timedelta(days=30)).isoformat() + "Z",
                            "publishedBefore": (datetime.now() - timedelta(days=7)).isoformat() + "Z",
                            "maxResults": 50
                        },
                        timeout=30.0
                    )
                    older_data = older.json()
                    older_count += len(older_data.get("items", []))
                    
                except Exception:
                    pass
                    
        # Calculate velocity score
        if older_count > 0:
            ratio = recent_count / older_count
            if ratio > 2:
                return {"score": 10, "trend": "exploding", "ratio": ratio}
            elif ratio > 1.5:
                return {"score": 8, "trend": "rising_fast", "ratio": ratio}
            elif ratio > 1.1:
                return {"score": 6, "trend": "rising", "ratio": ratio}
            elif ratio > 0.9:
                return {"score": 5, "trend": "stable", "ratio": ratio}
            else:
                return {"score": 3, "trend": "declining", "ratio": ratio}
        
        return {"score": 5, "trend": "unknown", "ratio": 1.0}
        
    async def _analyze_competition(
        self,
        keywords: List[str]
    ) -> Dict[str, Any]:
        """Analyze competition level for keywords."""
        if not self.youtube_api_key:
            return {"level": "unknown", "score": 5}
            
        total_videos = 0
        high_view_videos = 0
        
        async with httpx.AsyncClient() as client:
            for keyword in keywords[:2]:
                try:
                    # Search for videos
                    response = await client.get(
                        "https://www.googleapis.com/youtube/v3/search",
                        params={
                            "key": self.youtube_api_key,
                            "q": keyword,
                            "part": "id",
                            "type": "video",
                            "maxResults": 50
                        },
                        timeout=30.0
                    )
                    
                    data = response.json()
                    video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
                    total_videos += len(video_ids)
                    
                    if video_ids:
                        # Get video statistics
                        stats_response = await client.get(
                            "https://www.googleapis.com/youtube/v3/videos",
                            params={
                                "key": self.youtube_api_key,
                                "id": ",".join(video_ids[:25]),
                                "part": "statistics"
                            },
                            timeout=30.0
                        )
                        
                        stats_data = stats_response.json()
                        for item in stats_data.get("items", []):
                            views = int(item["statistics"].get("viewCount", 0))
                            if views > 100000:
                                high_view_videos += 1
                                
                except Exception:
                    pass
                    
        # Calculate competition score
        if total_videos > 0:
            high_view_ratio = high_view_videos / total_videos
            
            if high_view_ratio > 0.5:
                return {"level": "very_high", "score": 2, "high_view_ratio": high_view_ratio}
            elif high_view_ratio > 0.3:
                return {"level": "high", "score": 4, "high_view_ratio": high_view_ratio}
            elif high_view_ratio > 0.15:
                return {"level": "medium", "score": 6, "high_view_ratio": high_view_ratio}
            elif high_view_ratio > 0.05:
                return {"level": "low", "score": 8, "high_view_ratio": high_view_ratio}
            else:
                return {"level": "very_low", "score": 10, "high_view_ratio": high_view_ratio}
                
        return {"level": "unknown", "score": 5, "high_view_ratio": 0}
        
    def _calculate_viral_score(
        self,
        base_score: int,
        velocity: Dict[str, Any],
        competition: Dict[str, Any]
    ) -> int:
        """Calculate overall viral potential score (1-10)."""
        velocity_score = velocity.get("score", 5)
        competition_score = competition.get("score", 5)
        
        # Weighted average
        score = (base_score * 0.3) + (velocity_score * 0.4) + (competition_score * 0.3)
        
        return min(10, max(1, round(score)))
        
    async def _generate_variations(
        self,
        niche: str,
        keywords: List[str]
    ) -> List[Dict[str, str]]:
        """Generate concept variations for the niche."""
        # Variation templates
        templates = {
            "recap": [
                "{keyword} in 10 minutes",
                "Everything you missed about {keyword}",
                "{keyword} explained simply",
                "The truth about {keyword}",
                "{keyword} - What they don't tell you"
            ],
            "quiz": [
                "Can you find the odd {keyword}?",
                "{keyword} quiz - 99% fail",
                "Only geniuses can solve this {keyword} puzzle",
                "Test your {keyword} knowledge",
                "{keyword} brain teaser"
            ],
            "walking_tour": [
                "Walking in {keyword} 4K",
                "{keyword} city walk - sunrise edition",
                "Rainy day walk in {keyword}",
                "{keyword} hidden streets tour",
                "Night walk through {keyword}"
            ],
            "driving": [
                "Driving through {keyword} 4K",
                "{keyword} scenic drive",
                "Road trip: {keyword}",
                "{keyword} mountain roads",
                "Sunset drive in {keyword}"
            ],
        }
        
        niche_templates = templates.get(niche, [
            "{keyword} - Complete guide",
            "Top 10 {keyword} facts",
            "{keyword} you need to know",
            "The ultimate {keyword} video"
        ])
        
        variations = []
        for template in niche_templates:
            for keyword in keywords[:2]:
                variations.append({
                    "title": template.format(keyword=keyword),
                    "niche": niche,
                    "keyword": keyword
                })
                
        return variations[:10]
        
    def _get_recommendation(
        self,
        viral_score: int,
        competition: Dict[str, Any]
    ) -> str:
        """Get recommendation based on analysis."""
        comp_level = competition.get("level", "unknown")
        
        if viral_score >= 8 and comp_level in ["low", "very_low"]:
            return "HIGHLY RECOMMENDED - High viral potential with low competition. Start immediately!"
        elif viral_score >= 7 and comp_level in ["low", "medium"]:
            return "RECOMMENDED - Good opportunity. Consider starting a channel in this niche."
        elif viral_score >= 6:
            return "MODERATE - Decent potential but may require more effort to stand out."
        elif viral_score >= 4:
            return "CAUTION - Lower potential or high competition. Consider variations."
        else:
            return "NOT RECOMMENDED - Low viral potential or oversaturated market."
            
    async def _get_best_times(self, niche: str) -> List[Dict[str, Any]]:
        """Get best posting times for niche."""
        # Default optimal times (can be refined with actual data)
        times = {
            "recap": [
                {"day": "Friday", "hour": 17, "reason": "Weekend viewing starts"},
                {"day": "Saturday", "hour": 10, "reason": "Morning catch-up"},
                {"day": "Sunday", "hour": 19, "reason": "Evening relaxation"}
            ],
            "quiz": [
                {"day": "Monday", "hour": 12, "reason": "Lunch break engagement"},
                {"day": "Wednesday", "hour": 18, "reason": "Mid-week entertainment"},
                {"day": "Saturday", "hour": 14, "reason": "Weekend leisure"}
            ],
            "walking_tour": [
                {"day": "Sunday", "hour": 8, "reason": "Morning relaxation"},
                {"day": "Saturday", "hour": 20, "reason": "Evening wind-down"},
                {"day": "Friday", "hour": 21, "reason": "Weekend start"}
            ],
            "driving": [
                {"day": "Saturday", "hour": 9, "reason": "Weekend morning"},
                {"day": "Sunday", "hour": 15, "reason": "Afternoon relaxation"},
                {"day": "Friday", "hour": 20, "reason": "Evening escape"}
            ],
        }
        
        return times.get(niche, [
            {"day": "Friday", "hour": 17, "reason": "General peak time"},
            {"day": "Saturday", "hour": 12, "reason": "Weekend engagement"},
            {"day": "Sunday", "hour": 18, "reason": "Evening viewing"}
        ])
        
    async def find_trending_niches(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find currently trending niches.
        
        Returns:
            List of trending niches with scores
        """
        results = []
        
        for niche, config in self.NICHE_CATEGORIES.items():
            # Sample keywords for each niche
            sample_keywords = {
                "recap": ["movie recap", "series recap"],
                "quiz": ["find the odd one", "brain teaser"],
                "walking_tour": ["city walk 4k", "walking tour"],
                "driving": ["driving 4k", "road trip"],
                "true_crime": ["true crime", "unsolved mystery"],
                "finance": ["stock market", "crypto news"],
            }
            
            keywords = sample_keywords.get(niche, [niche])
            
            try:
                analysis = await self.analyze_niche(niche, keywords, days_back=14)
                results.append({
                    "niche": niche,
                    "viral_score": analysis["viral_score"],
                    "velocity": analysis["velocity"]["trend"],
                    "competition": analysis["competition"]["level"],
                    "rpm_range": config["rpm_range"],
                    "recommendation": analysis["recommendation"]
                })
            except Exception as e:
                print(f"Error analyzing {niche}: {e}")
                
        # Sort by viral score
        results.sort(key=lambda x: x["viral_score"], reverse=True)
        
        return results[:limit]
        
    async def suggest_niche_pivot(
        self,
        current_niche: str,
        performance_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Suggest niche pivots based on performance.
        
        Args:
            current_niche: Current niche
            performance_data: Current performance metrics
            
        Returns:
            Pivot suggestions
        """
        current_rpm = performance_data.get("rpm", 0)
        current_views = performance_data.get("avg_views", 0)
        
        suggestions = []
        
        for niche, config in self.NICHE_CATEGORIES.items():
            if niche == current_niche:
                continue
                
            min_rpm, max_rpm = config["rpm_range"]
            avg_rpm = (min_rpm + max_rpm) / 2
            
            # Calculate potential improvement
            rpm_improvement = ((avg_rpm - current_rpm) / current_rpm * 100) if current_rpm > 0 else 0
            
            if rpm_improvement > 20:  # At least 20% improvement potential
                suggestions.append({
                    "niche": niche,
                    "current_rpm": current_rpm,
                    "potential_rpm": avg_rpm,
                    "improvement": f"+{rpm_improvement:.0f}%",
                    "competition": config["competition"],
                    "base_score": config["base_score"]
                })
                
        # Sort by potential improvement
        suggestions.sort(key=lambda x: float(x["improvement"].replace("+", "").replace("%", "")), reverse=True)
        
        return {
            "current_niche": current_niche,
            "current_performance": performance_data,
            "pivot_suggestions": suggestions[:5],
            "recommendation": suggestions[0] if suggestions else None
        }
