"""
Analytics Dashboard - FastAPI Backend
Provides real-time analytics, video queue management, and performance tracking.
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import asyncpg
import httpx


app = FastAPI(
    title="Amharic Recap Autopilot Dashboard",
    description="Analytics and management dashboard for YouTube automation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


class VideoStatus(BaseModel):
    video_id: str
    status: str
    title: Optional[str] = None
    progress: int = 0
    error: Optional[str] = None


class ScheduleRequest(BaseModel):
    video_id: str
    scheduled_time: datetime
    

class ABTestRequest(BaseModel):
    video_id: str
    variants: List[Dict[str, Any]]
    metric: str = "ctr"


@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "autopilot"),
        password=os.getenv("POSTGRES_PASSWORD", "autopilot_secret_password"),
        database=os.getenv("POSTGRES_DB", "amharic_recap"),
        min_size=2,
        max_size=10
    )
    

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()


# ============== Dashboard Overview ==============

@app.get("/api/overview")
async def get_overview() -> Dict[str, Any]:
    """Get dashboard overview with key metrics."""
    async with db_pool.acquire() as conn:
        # Videos stats
        total_videos = await conn.fetchval("SELECT COUNT(*) FROM videos")
        published_videos = await conn.fetchval(
            "SELECT COUNT(*) FROM uploads WHERE status = 'published'"
        )
        processing_videos = await conn.fetchval(
            "SELECT COUNT(*) FROM videos WHERE status IN ('processing', 'queued')"
        )
        
        # Today's stats
        today = datetime.utcnow().date()
        videos_today = await conn.fetchval(
            "SELECT COUNT(*) FROM uploads WHERE DATE(published_at) = $1",
            today
        )
        
        # Revenue (if available)
        revenue_30d = await conn.fetchval(
            """SELECT COALESCE(SUM(estimated_revenue), 0) FROM metrics 
               WHERE date >= NOW() - INTERVAL '30 days'"""
        ) or 0
        
        # Views
        views_30d = await conn.fetchval(
            """SELECT COALESCE(SUM(views), 0) FROM metrics 
               WHERE date >= NOW() - INTERVAL '30 days'"""
        ) or 0
        
        # Shorts stats
        total_shorts = await conn.fetchval(
            "SELECT COUNT(*) FROM shorts"
        ) or 0
        
    return {
        "total_videos": total_videos or 0,
        "published_videos": published_videos or 0,
        "processing_videos": processing_videos or 0,
        "videos_today": videos_today or 0,
        "revenue_30d": float(revenue_30d),
        "views_30d": views_30d or 0,
        "total_shorts": total_shorts,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============== Video Queue ==============

@app.get("/api/queue")
async def get_video_queue(
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0
) -> Dict[str, Any]:
    """Get videos in the processing queue."""
    async with db_pool.acquire() as conn:
        query = """
            SELECT v.id, v.youtube_id, v.title, v.status, v.progress,
                   v.created_at, v.updated_at, v.error_message,
                   c.name as channel_name
            FROM videos v
            LEFT JOIN channels c ON v.channel_id = c.id
        """
        params = []
        
        if status:
            query += " WHERE v.status = $1"
            params.append(status)
            
        query += " ORDER BY v.created_at DESC LIMIT $%d OFFSET $%d" % (
            len(params) + 1, len(params) + 2
        )
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM videos" + 
            (f" WHERE status = '{status}'" if status else "")
        )
        
    return {
        "videos": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/queue/{video_id}")
async def get_video_details(video_id: str) -> Dict[str, Any]:
    """Get detailed info for a specific video."""
    async with db_pool.acquire() as conn:
        video = await conn.fetchrow(
            """SELECT v.*, c.name as channel_name, c.youtube_id as channel_youtube_id
               FROM videos v
               LEFT JOIN channels c ON v.channel_id = c.id
               WHERE v.id = $1 OR v.youtube_id = $1""",
            video_id
        )
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
            
        # Get related data
        transcript = await conn.fetchrow(
            "SELECT * FROM transcripts WHERE video_id = $1",
            video["id"]
        )
        
        script = await conn.fetchrow(
            "SELECT * FROM scripts WHERE video_id = $1",
            video["id"]
        )
        
        audio = await conn.fetchrow(
            "SELECT * FROM audio WHERE video_id = $1",
            video["id"]
        )
        
        render = await conn.fetchrow(
            "SELECT * FROM renders WHERE video_id = $1",
            video["id"]
        )
        
        upload = await conn.fetchrow(
            "SELECT * FROM uploads WHERE video_id = $1",
            video["id"]
        )
        
        shorts = await conn.fetch(
            "SELECT * FROM shorts WHERE video_id = $1 ORDER BY index",
            video["id"]
        )
        
    return {
        "video": dict(video),
        "transcript": dict(transcript) if transcript else None,
        "script": dict(script) if script else None,
        "audio": dict(audio) if audio else None,
        "render": dict(render) if render else None,
        "upload": dict(upload) if upload else None,
        "shorts": [dict(s) for s in shorts]
    }


@app.post("/api/queue/{video_id}/retry")
async def retry_video(video_id: str, background_tasks: BackgroundTasks):
    """Retry processing a failed video."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """UPDATE videos SET status = 'queued', error_message = NULL, 
               progress = 0, updated_at = NOW() WHERE id = $1""",
            video_id
        )
    return {"status": "queued", "video_id": video_id}


@app.delete("/api/queue/{video_id}")
async def remove_from_queue(video_id: str):
    """Remove a video from the queue."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE videos SET status = 'cancelled' WHERE id = $1",
            video_id
        )
    return {"status": "cancelled", "video_id": video_id}


# ============== Analytics ==============

@app.get("/api/analytics/performance")
async def get_performance_analytics(
    days: int = Query(30, le=90),
    metric: str = "views"
) -> Dict[str, Any]:
    """Get performance analytics over time."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT date, SUM({metric}) as value
                FROM metrics
                WHERE date >= NOW() - INTERVAL '{days} days'
                GROUP BY date
                ORDER BY date""",
        )
        
    return {
        "metric": metric,
        "days": days,
        "data": [{"date": r["date"].isoformat(), "value": r["value"]} for r in rows]
    }


@app.get("/api/analytics/top-videos")
async def get_top_videos(
    days: int = Query(30, le=90),
    metric: str = "views",
    limit: int = Query(10, le=50)
) -> List[Dict[str, Any]]:
    """Get top performing videos."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT v.id, v.title, u.youtube_video_id,
                       SUM(m.{metric}) as total_{metric},
                       AVG(m.ctr) as avg_ctr,
                       AVG(m.avg_view_duration) as avg_duration
                FROM videos v
                JOIN uploads u ON v.id = u.video_id
                JOIN metrics m ON u.youtube_video_id = m.youtube_video_id
                WHERE m.date >= NOW() - INTERVAL '{days} days'
                GROUP BY v.id, v.title, u.youtube_video_id
                ORDER BY total_{metric} DESC
                LIMIT $1""",
            limit
        )
        
    return [dict(r) for r in rows]


@app.get("/api/analytics/channel-stats")
async def get_channel_stats() -> Dict[str, Any]:
    """Get overall channel statistics."""
    async with db_pool.acquire() as conn:
        # Total subscribers (from latest metric)
        subs = await conn.fetchval(
            "SELECT subscribers FROM channel_metrics ORDER BY date DESC LIMIT 1"
        ) or 0
        
        # Total views
        total_views = await conn.fetchval(
            "SELECT SUM(views) FROM metrics"
        ) or 0
        
        # Total watch time
        total_watch_time = await conn.fetchval(
            "SELECT SUM(watch_time_minutes) FROM metrics"
        ) or 0
        
        # Average CTR
        avg_ctr = await conn.fetchval(
            "SELECT AVG(ctr) FROM metrics WHERE date >= NOW() - INTERVAL '30 days'"
        ) or 0
        
        # Revenue
        total_revenue = await conn.fetchval(
            "SELECT SUM(estimated_revenue) FROM metrics"
        ) or 0
        
    return {
        "subscribers": subs,
        "total_views": total_views,
        "total_watch_time_hours": round(total_watch_time / 60, 1),
        "avg_ctr_30d": round(float(avg_ctr), 2),
        "total_revenue": round(float(total_revenue), 2)
    }


@app.get("/api/analytics/topics")
async def get_topic_performance(days: int = Query(30, le=90)) -> List[Dict[str, Any]]:
    """Get performance breakdown by topic/category."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT v.category, COUNT(*) as video_count,
                      SUM(m.views) as total_views,
                      AVG(m.ctr) as avg_ctr,
                      SUM(m.estimated_revenue) as total_revenue
               FROM videos v
               JOIN uploads u ON v.id = u.video_id
               JOIN metrics m ON u.youtube_video_id = m.youtube_video_id
               WHERE m.date >= NOW() - INTERVAL '%s days'
               GROUP BY v.category
               ORDER BY total_views DESC""" % days
        )
        
    return [dict(r) for r in rows]


# ============== A/B Testing ==============

@app.get("/api/ab-tests")
async def get_ab_tests(active_only: bool = True) -> List[Dict[str, Any]]:
    """Get A/B test configurations and results."""
    async with db_pool.acquire() as conn:
        query = "SELECT * FROM ab_tests"
        if active_only:
            query += " WHERE status = 'active'"
        query += " ORDER BY created_at DESC"
        
        rows = await conn.fetch(query)
        
    return [dict(r) for r in rows]


@app.post("/api/ab-tests")
async def create_ab_test(request: ABTestRequest) -> Dict[str, Any]:
    """Create a new A/B test."""
    async with db_pool.acquire() as conn:
        test_id = await conn.fetchval(
            """INSERT INTO ab_tests (video_id, variants, metric, status, created_at)
               VALUES ($1, $2, $3, 'active', NOW())
               RETURNING id""",
            request.video_id,
            str(request.variants),
            request.metric
        )
        
    return {"test_id": test_id, "status": "created"}


@app.get("/api/ab-tests/{test_id}/results")
async def get_ab_test_results(test_id: int) -> Dict[str, Any]:
    """Get results for an A/B test."""
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow(
            "SELECT * FROM ab_tests WHERE id = $1",
            test_id
        )
        
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")
            
        results = await conn.fetch(
            """SELECT variant_id, COUNT(*) as impressions,
                      SUM(CASE WHEN clicked THEN 1 ELSE 0 END) as clicks,
                      AVG(watch_time) as avg_watch_time
               FROM ab_test_impressions
               WHERE test_id = $1
               GROUP BY variant_id""",
            test_id
        )
        
    return {
        "test": dict(test),
        "results": [dict(r) for r in results]
    }


# ============== Scheduling ==============

@app.get("/api/schedule")
async def get_schedule(
    days_ahead: int = Query(7, le=30)
) -> List[Dict[str, Any]]:
    """Get scheduled video publications."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.*, v.title, v.youtube_id
               FROM schedule s
               JOIN videos v ON s.video_id = v.id
               WHERE s.scheduled_time >= NOW()
                 AND s.scheduled_time <= NOW() + INTERVAL '%s days'
               ORDER BY s.scheduled_time""" % days_ahead
        )
        
    return [dict(r) for r in rows]


@app.post("/api/schedule")
async def schedule_video(request: ScheduleRequest) -> Dict[str, Any]:
    """Schedule a video for publication."""
    async with db_pool.acquire() as conn:
        schedule_id = await conn.fetchval(
            """INSERT INTO schedule (video_id, scheduled_time, status, created_at)
               VALUES ($1, $2, 'pending', NOW())
               RETURNING id""",
            request.video_id,
            request.scheduled_time
        )
        
    return {"schedule_id": schedule_id, "status": "scheduled"}


@app.delete("/api/schedule/{schedule_id}")
async def cancel_scheduled(schedule_id: int):
    """Cancel a scheduled publication."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE schedule SET status = 'cancelled' WHERE id = $1",
            schedule_id
        )
    return {"status": "cancelled"}


# ============== Shorts Analytics ==============

@app.get("/api/shorts")
async def get_shorts(
    limit: int = Query(50, le=100),
    offset: int = 0
) -> Dict[str, Any]:
    """Get generated shorts with performance data."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.*, v.title as video_title,
                      m.views, m.likes, m.comments
               FROM shorts s
               JOIN videos v ON s.video_id = v.id
               LEFT JOIN shorts_metrics m ON s.id = m.short_id
               ORDER BY s.created_at DESC
               LIMIT $1 OFFSET $2""",
            limit, offset
        )
        
        total = await conn.fetchval("SELECT COUNT(*) FROM shorts")
        
    return {
        "shorts": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/shorts/performance")
async def get_shorts_performance(days: int = Query(30, le=90)) -> Dict[str, Any]:
    """Get Shorts performance summary."""
    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow(
            """SELECT COUNT(*) as total_shorts,
                      SUM(m.views) as total_views,
                      AVG(m.views) as avg_views,
                      SUM(m.likes) as total_likes,
                      MAX(m.views) as best_views
               FROM shorts s
               LEFT JOIN shorts_metrics m ON s.id = m.short_id
               WHERE s.created_at >= NOW() - INTERVAL '%s days'""" % days
        )
        
    return dict(stats) if stats else {}


# ============== Health & Status ==============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/system/status")
async def get_system_status() -> Dict[str, Any]:
    """Get system component status."""
    status = {
        "database": "unknown",
        "runner": "unknown",
        "n8n": "unknown",
        "zthumb": "unknown"
    }
    
    # Check database
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        status["database"] = "healthy"
    except:
        status["database"] = "unhealthy"
        
    # Check runner service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://runner:8000/health")
            status["runner"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except:
        status["runner"] = "unreachable"
        
    # Check n8n
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://n8n:5678/healthz")
            status["n8n"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except:
        status["n8n"] = "unreachable"
        
    # Check ZThumb
    zthumb_url = os.getenv("ZTHUMB_URL")
    if zthumb_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{zthumb_url}/health")
                status["zthumb"] = "healthy" if resp.status_code == 200 else "unhealthy"
        except:
            status["zthumb"] = "unreachable"
    else:
        status["zthumb"] = "not configured"
        
    return status


# ============== Static Files & Frontend ==============

# Serve static frontend files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the dashboard frontend."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    # Return embedded HTML if no static files
    return HTMLResponse(content=EMBEDDED_DASHBOARD_HTML)


# Embedded dashboard HTML (fallback)
EMBEDDED_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amharic Recap Autopilot Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        [x-cloak] { display: none !important; }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div x-data="dashboard()" x-init="init()" class="container mx-auto px-4 py-8">
        <!-- Header -->
        <header class="mb-8">
            <h1 class="text-3xl font-bold text-purple-400">Amharic Recap Autopilot</h1>
            <p class="text-gray-400">YouTube Automation Dashboard</p>
        </header>
        
        <!-- Overview Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Total Videos</h3>
                <p class="text-3xl font-bold" x-text="overview.total_videos">-</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Published</h3>
                <p class="text-3xl font-bold text-green-400" x-text="overview.published_videos">-</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Processing</h3>
                <p class="text-3xl font-bold text-yellow-400" x-text="overview.processing_videos">-</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Views (30d)</h3>
                <p class="text-3xl font-bold text-blue-400" x-text="formatNumber(overview.views_30d)">-</p>
            </div>
        </div>
        
        <!-- Revenue Card -->
        <div class="bg-gradient-to-r from-purple-900 to-indigo-900 rounded-lg p-6 mb-8">
            <h3 class="text-gray-300 text-sm">Estimated Revenue (30 days)</h3>
            <p class="text-4xl font-bold text-green-400">$<span x-text="overview.revenue_30d?.toFixed(2) || '0.00'"></span></p>
        </div>
        
        <!-- Tabs -->
        <div class="mb-6">
            <nav class="flex space-x-4">
                <button @click="activeTab = 'queue'" 
                        :class="activeTab === 'queue' ? 'bg-purple-600' : 'bg-gray-700'"
                        class="px-4 py-2 rounded-lg">Queue</button>
                <button @click="activeTab = 'analytics'" 
                        :class="activeTab === 'analytics' ? 'bg-purple-600' : 'bg-gray-700'"
                        class="px-4 py-2 rounded-lg">Analytics</button>
                <button @click="activeTab = 'shorts'" 
                        :class="activeTab === 'shorts' ? 'bg-purple-600' : 'bg-gray-700'"
                        class="px-4 py-2 rounded-lg">Shorts</button>
                <button @click="activeTab = 'schedule'" 
                        :class="activeTab === 'schedule' ? 'bg-purple-600' : 'bg-gray-700'"
                        class="px-4 py-2 rounded-lg">Schedule</button>
            </nav>
        </div>
        
        <!-- Queue Tab -->
        <div x-show="activeTab === 'queue'" x-cloak>
            <div class="bg-gray-800 rounded-lg overflow-hidden">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="px-4 py-3 text-left">Title</th>
                            <th class="px-4 py-3 text-left">Status</th>
                            <th class="px-4 py-3 text-left">Progress</th>
                            <th class="px-4 py-3 text-left">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        <template x-for="video in queue.videos" :key="video.id">
                            <tr class="border-t border-gray-700">
                                <td class="px-4 py-3" x-text="video.title || video.youtube_id"></td>
                                <td class="px-4 py-3">
                                    <span :class="{
                                        'bg-yellow-600': video.status === 'processing',
                                        'bg-green-600': video.status === 'completed',
                                        'bg-red-600': video.status === 'failed',
                                        'bg-gray-600': video.status === 'queued'
                                    }" class="px-2 py-1 rounded text-sm" x-text="video.status"></span>
                                </td>
                                <td class="px-4 py-3">
                                    <div class="w-full bg-gray-700 rounded-full h-2">
                                        <div class="bg-purple-600 h-2 rounded-full" :style="'width: ' + (video.progress || 0) + '%'"></div>
                                    </div>
                                </td>
                                <td class="px-4 py-3">
                                    <button @click="retryVideo(video.id)" 
                                            x-show="video.status === 'failed'"
                                            class="text-blue-400 hover:text-blue-300">Retry</button>
                                </td>
                            </tr>
                        </template>
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Analytics Tab -->
        <div x-show="activeTab === 'analytics'" x-cloak>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-bold mb-4">Performance Over Time</h3>
                <canvas id="performanceChart" height="100"></canvas>
            </div>
            
            <div class="mt-6 bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-bold mb-4">Top Videos</h3>
                <div class="space-y-4">
                    <template x-for="video in topVideos" :key="video.id">
                        <div class="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                            <span x-text="video.title"></span>
                            <span class="text-green-400" x-text="formatNumber(video.total_views) + ' views'"></span>
                        </div>
                    </template>
                </div>
            </div>
        </div>
        
        <!-- Shorts Tab -->
        <div x-show="activeTab === 'shorts'" x-cloak>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-gray-800 rounded-lg p-6">
                    <h3 class="text-gray-400 text-sm">Total Shorts</h3>
                    <p class="text-3xl font-bold" x-text="shortsStats.total_shorts || 0">-</p>
                </div>
                <div class="bg-gray-800 rounded-lg p-6">
                    <h3 class="text-gray-400 text-sm">Total Views</h3>
                    <p class="text-3xl font-bold text-blue-400" x-text="formatNumber(shortsStats.total_views)">-</p>
                </div>
                <div class="bg-gray-800 rounded-lg p-6">
                    <h3 class="text-gray-400 text-sm">Avg Views</h3>
                    <p class="text-3xl font-bold text-purple-400" x-text="formatNumber(shortsStats.avg_views)">-</p>
                </div>
            </div>
            
            <div class="bg-gray-800 rounded-lg overflow-hidden">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="px-4 py-3 text-left">Video</th>
                            <th class="px-4 py-3 text-left">Short #</th>
                            <th class="px-4 py-3 text-left">Views</th>
                            <th class="px-4 py-3 text-left">Likes</th>
                        </tr>
                    </thead>
                    <tbody>
                        <template x-for="short in shorts.shorts" :key="short.id">
                            <tr class="border-t border-gray-700">
                                <td class="px-4 py-3" x-text="short.video_title"></td>
                                <td class="px-4 py-3" x-text="'#' + short.index"></td>
                                <td class="px-4 py-3" x-text="formatNumber(short.views)"></td>
                                <td class="px-4 py-3" x-text="formatNumber(short.likes)"></td>
                            </tr>
                        </template>
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Schedule Tab -->
        <div x-show="activeTab === 'schedule'" x-cloak>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-xl font-bold mb-4">Upcoming Publications</h3>
                <div class="space-y-4">
                    <template x-for="item in schedule" :key="item.id">
                        <div class="flex justify-between items-center p-4 bg-gray-700 rounded-lg">
                            <div>
                                <p class="font-bold" x-text="item.title"></p>
                                <p class="text-gray-400 text-sm" x-text="formatDate(item.scheduled_time)"></p>
                            </div>
                            <button @click="cancelSchedule(item.id)" class="text-red-400 hover:text-red-300">Cancel</button>
                        </div>
                    </template>
                    <p x-show="schedule.length === 0" class="text-gray-400">No scheduled publications</p>
                </div>
            </div>
        </div>
        
        <!-- System Status -->
        <div class="mt-8 bg-gray-800 rounded-lg p-6">
            <h3 class="text-xl font-bold mb-4">System Status</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <template x-for="(status, service) in systemStatus" :key="service">
                    <div class="flex items-center space-x-2">
                        <span :class="status === 'healthy' ? 'bg-green-500' : 'bg-red-500'" 
                              class="w-3 h-3 rounded-full"></span>
                        <span class="capitalize" x-text="service"></span>
                    </div>
                </template>
            </div>
        </div>
    </div>
    
    <script>
        function dashboard() {
            return {
                activeTab: 'queue',
                overview: {},
                queue: { videos: [] },
                topVideos: [],
                shorts: { shorts: [] },
                shortsStats: {},
                schedule: [],
                systemStatus: {},
                performanceChart: null,
                
                async init() {
                    await this.loadOverview();
                    await this.loadQueue();
                    await this.loadTopVideos();
                    await this.loadShorts();
                    await this.loadShortsStats();
                    await this.loadSchedule();
                    await this.loadSystemStatus();
                    this.initChart();
                    
                    // Refresh every 30 seconds
                    setInterval(() => this.loadOverview(), 30000);
                    setInterval(() => this.loadQueue(), 30000);
                },
                
                async loadOverview() {
                    try {
                        const resp = await fetch('/api/overview');
                        this.overview = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadQueue() {
                    try {
                        const resp = await fetch('/api/queue');
                        this.queue = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadTopVideos() {
                    try {
                        const resp = await fetch('/api/analytics/top-videos');
                        this.topVideos = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadShorts() {
                    try {
                        const resp = await fetch('/api/shorts');
                        this.shorts = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadShortsStats() {
                    try {
                        const resp = await fetch('/api/shorts/performance');
                        this.shortsStats = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadSchedule() {
                    try {
                        const resp = await fetch('/api/schedule');
                        this.schedule = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async loadSystemStatus() {
                    try {
                        const resp = await fetch('/api/system/status');
                        this.systemStatus = await resp.json();
                    } catch (e) { console.error(e); }
                },
                
                async retryVideo(videoId) {
                    await fetch(`/api/queue/${videoId}/retry`, { method: 'POST' });
                    await this.loadQueue();
                },
                
                async cancelSchedule(scheduleId) {
                    await fetch(`/api/schedule/${scheduleId}`, { method: 'DELETE' });
                    await this.loadSchedule();
                },
                
                initChart() {
                    const ctx = document.getElementById('performanceChart');
                    if (!ctx) return;
                    
                    this.performanceChart = new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: [],
                            datasets: [{
                                label: 'Views',
                                data: [],
                                borderColor: 'rgb(147, 51, 234)',
                                tension: 0.1
                            }]
                        },
                        options: {
                            responsive: true,
                            scales: {
                                y: { beginAtZero: true }
                            }
                        }
                    });
                    
                    this.loadChartData();
                },
                
                async loadChartData() {
                    try {
                        const resp = await fetch('/api/analytics/performance?days=30');
                        const data = await resp.json();
                        
                        if (this.performanceChart && data.data) {
                            this.performanceChart.data.labels = data.data.map(d => d.date);
                            this.performanceChart.data.datasets[0].data = data.data.map(d => d.value);
                            this.performanceChart.update();
                        }
                    } catch (e) { console.error(e); }
                },
                
                formatNumber(num) {
                    if (!num) return '0';
                    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
                    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
                    return num.toString();
                },
                
                formatDate(dateStr) {
                    return new Date(dateStr).toLocaleString();
                }
            }
        }
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
