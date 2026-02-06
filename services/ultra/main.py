"""
Ultra Autopilot - Main Orchestrator
Superior YouTube automation system combining all engines.
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import asyncpg

from .engines import (
    MultiLanguageEngine,
    ViralNicheDetector,
    AmbientContentGenerator,
    QuizContentGenerator,
    RevenueOptimizer,
)


class UltraAutopilot:
    """
    Main orchestrator for the Ultra Autopilot system.
    
    Combines all engines for maximum YouTube automation:
    - Multi-language content production
    - Viral niche detection
    - Ambient content (walking/driving)
    - Quiz content generation
    - Revenue optimization
    """
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db = db_pool
        
        # Initialize engines
        self.multilang = MultiLanguageEngine(db_pool)
        self.viral = ViralNicheDetector(db_pool)
        self.ambient = AmbientContentGenerator(db_pool)
        self.quiz = QuizContentGenerator(db_pool)
        self.revenue = RevenueOptimizer(db_pool)
        
        # Configuration
        self.max_concurrent_jobs = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))
        self.auto_translate_languages = os.getenv(
            "AUTO_TRANSLATE_LANGUAGES",
            "de,pl,es,fr,it"
        ).split(",")
        
    async def run_full_pipeline(
        self,
        content_type: str,
        source_data: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run the full Ultra Autopilot pipeline.
        
        Args:
            content_type: Type of content (recap, quiz, walking, driving)
            source_data: Source content data
            options: Additional options
            
        Returns:
            Pipeline results
        """
        options = options or {}
        results = {
            "content_type": content_type,
            "started_at": datetime.now().isoformat(),
            "stages": {}
        }
        
        try:
            # Stage 1: Viral analysis
            if options.get("analyze_viral", True):
                viral_analysis = await self.viral.analyze_niche(
                    content_type,
                    source_data.get("keywords", [content_type]),
                    days_back=14
                )
                results["stages"]["viral_analysis"] = viral_analysis
                
            # Stage 2: Generate base content
            if content_type == "quiz":
                base_content = await self.quiz.generate_quiz_video(
                    format_type=source_data.get("format", "find_odd"),
                    topic=source_data.get("topic", "general"),
                    num_questions=source_data.get("num_questions", 10),
                    difficulty=source_data.get("difficulty", "medium")
                )
            elif content_type == "walking":
                base_content = await self.ambient.process_walking_video(
                    input_path=source_data["video_path"],
                    city=source_data["city"],
                    area=source_data["area"],
                    time_of_day=source_data.get("time_of_day", "day")
                )
            elif content_type == "driving":
                base_content = await self.ambient.process_driving_video(
                    input_path=source_data["video_path"],
                    route=source_data["route"]
                )
            else:
                # Default: use source as-is
                base_content = source_data
                
            results["stages"]["base_content"] = base_content
            
            # Stage 3: Multi-language versions
            if options.get("translate", True) and base_content.get("video_path"):
                languages = options.get("languages", self.auto_translate_languages)
                
                translations = await self.multilang.create_multilang_version(
                    video_id=base_content.get("video_id", "unknown"),
                    source_script=base_content.get("script", ""),
                    source_lang="en",
                    target_langs=languages,
                    video_path=base_content["video_path"]
                )
                results["stages"]["translations"] = translations
                
            # Stage 4: Revenue projection
            if options.get("project_revenue", True):
                languages_used = options.get("languages", self.auto_translate_languages)
                projection = await self.multilang.get_revenue_projection(
                    views_estimate=options.get("views_estimate", 10000),
                    languages=languages_used
                )
                results["stages"]["revenue_projection"] = projection
                
            results["status"] = "completed"
            results["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            
        return results
        
    async def discover_opportunities(
        self,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Discover content opportunities based on trends and revenue.
        
        Returns:
            Ranked opportunities with recommendations
        """
        # Get trending niches
        trending = await self.viral.find_trending_niches(limit=limit)
        
        # Get revenue optimization suggestions
        revenue_suggestions = await self.revenue.get_optimization_suggestions()
        
        # Get content prioritization
        priorities = await self.revenue.get_content_prioritization(limit=limit)
        
        return {
            "trending_niches": trending,
            "revenue_suggestions": revenue_suggestions,
            "content_priorities": priorities,
            "generated_at": datetime.now().isoformat()
        }
        
    async def generate_daily_content_plan(
        self,
        videos_per_day: int = 3
    ) -> Dict[str, Any]:
        """
        Generate a daily content production plan.
        
        Args:
            videos_per_day: Target videos per day
            
        Returns:
            Content plan with specific recommendations
        """
        # Get opportunities
        opportunities = await self.discover_opportunities(limit=20)
        
        # Get high RPM languages
        high_rpm_langs = self.multilang.get_high_rpm_languages(min_rpm=3.0)
        
        # Create plan
        plan = {
            "date": datetime.now().date().isoformat(),
            "target_videos": videos_per_day,
            "content_slots": []
        }
        
        # Allocate content slots
        trending = opportunities["trending_niches"]
        
        for i in range(videos_per_day):
            if i < len(trending):
                niche = trending[i]
                slot = {
                    "slot": i + 1,
                    "niche": niche["niche"],
                    "viral_score": niche["viral_score"],
                    "languages": high_rpm_langs[:5],
                    "estimated_rpm": niche["rpm_range"],
                    "recommendation": niche["recommendation"]
                }
            else:
                # Default to quiz content
                slot = {
                    "slot": i + 1,
                    "niche": "quiz",
                    "type": "find_odd",
                    "languages": high_rpm_langs[:5],
                    "estimated_rpm": (3, 6)
                }
                
            plan["content_slots"].append(slot)
            
        # Add revenue forecast
        forecast = await self.revenue.forecast_revenue(
            days_ahead=30,
            videos_per_day=videos_per_day
        )
        plan["monthly_forecast"] = forecast
        
        return plan
        
    async def batch_produce(
        self,
        content_specs: List[Dict[str, Any]],
        max_concurrent: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Batch produce multiple content pieces.
        
        Args:
            content_specs: List of content specifications
            max_concurrent: Maximum concurrent productions
            
        Returns:
            List of production results
        """
        max_concurrent = max_concurrent or self.max_concurrent_jobs
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def produce_one(spec: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.run_full_pipeline(
                    content_type=spec.get("type", "recap"),
                    source_data=spec.get("data", {}),
                    options=spec.get("options", {})
                )
                
        tasks = [produce_one(spec) for spec in content_specs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]
        
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data.
        
        Returns:
            Dashboard data for UI
        """
        # Revenue data
        daily_report = await self.revenue.get_daily_report()
        rpm_by_lang = await self.revenue.get_rpm_by_language(30)
        rpm_by_niche = await self.revenue.get_rpm_by_niche(30)
        
        # Opportunities
        opportunities = await self.discover_opportunities(5)
        
        # Available content types
        quiz_formats = self.quiz.get_available_formats()
        cities = self.ambient.get_available_cities()
        routes = self.ambient.get_available_routes()
        languages = list(self.multilang.LANGUAGES.keys())
        
        return {
            "revenue": {
                "daily": daily_report,
                "by_language": rpm_by_lang,
                "by_niche": rpm_by_niche
            },
            "opportunities": opportunities,
            "available_content": {
                "quiz_formats": quiz_formats,
                "walking_cities": cities,
                "driving_routes": routes,
                "languages": languages
            },
            "generated_at": datetime.now().isoformat()
        }


async def create_ultra_autopilot() -> UltraAutopilot:
    """
    Factory function to create UltraAutopilot instance.
    
    Returns:
        Configured UltraAutopilot instance
    """
    # Create database pool
    db_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "autopilot"),
        password=os.getenv("POSTGRES_PASSWORD", "autopilot_secret_password"),
        database=os.getenv("POSTGRES_DB", "amharic_recap"),
        min_size=2,
        max_size=10
    )
    
    return UltraAutopilot(db_pool)


# CLI entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ultra Autopilot CLI")
    parser.add_argument("command", choices=["plan", "discover", "dashboard"])
    parser.add_argument("--videos", type=int, default=3, help="Videos per day")
    
    args = parser.parse_args()
    
    async def main():
        autopilot = await create_ultra_autopilot()
        
        if args.command == "plan":
            plan = await autopilot.generate_daily_content_plan(args.videos)
            print(json.dumps(plan, indent=2))
        elif args.command == "discover":
            opportunities = await autopilot.discover_opportunities()
            print(json.dumps(opportunities, indent=2))
        elif args.command == "dashboard":
            data = await autopilot.get_dashboard_data()
            print(json.dumps(data, indent=2))
            
    import json
    asyncio.run(main())
