-- Initialize database schema for Amharic Recap Autopilot

-- Channels table: stores discovered YouTube recap channels
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(255) UNIQUE NOT NULL,
    channel_name VARCHAR(500) NOT NULL,
    subscriber_count BIGINT DEFAULT 0,
    upload_count INTEGER DEFAULT 0,
    avg_views_per_upload BIGINT DEFAULT 0,
    upload_consistency_score FLOAT DEFAULT 0,
    growth_proxy_score FLOAT DEFAULT 0,
    composite_score FLOAT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Videos table: stores target videos for processing
CREATE TABLE IF NOT EXISTS videos (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) UNIQUE NOT NULL,
    channel_id VARCHAR(255) REFERENCES channels(channel_id),
    title VARCHAR(1000) NOT NULL,
    description TEXT,
    view_count BIGINT DEFAULT 0,
    like_count BIGINT DEFAULT 0,
    comment_count BIGINT DEFAULT 0,
    duration_seconds INTEGER,
    published_at TIMESTAMP,
    views_velocity FLOAT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'discovered',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transcripts table: stores video transcripts
CREATE TABLE IF NOT EXISTS transcripts (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    raw_transcript TEXT,
    cleaned_transcript TEXT,
    timestamps JSONB,
    language_detected VARCHAR(50),
    source VARCHAR(50), -- 'youtube_captions', 'whisper', 'gemini'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scripts table: stores generated Amharic recap scripts
CREATE TABLE IF NOT EXISTS scripts (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    hook_text TEXT,
    main_recap_segments JSONB,
    payoff_text TEXT,
    cta_text TEXT,
    full_script TEXT,
    quality_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audio table: stores generated voice audio metadata
CREATE TABLE IF NOT EXISTS audio (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    script_id INTEGER REFERENCES scripts(id),
    voice_provider VARCHAR(50) DEFAULT 'azure', -- 'azure', 'elevenlabs'
    voice_id VARCHAR(100),
    audio_file_path VARCHAR(500),
    duration_seconds FLOAT,
    loudness_lufs FLOAT,
    quality_check_passed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Renders table: stores final rendered video metadata
CREATE TABLE IF NOT EXISTS renders (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    audio_id INTEGER REFERENCES audio(id),
    output_file_path VARCHAR(500),
    duration_seconds FLOAT,
    scene_alignment_score FLOAT,
    quality_check_passed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Thumbnails table: stores generated thumbnails
CREATE TABLE IF NOT EXISTS thumbnails (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    thumbnail_path VARCHAR(500),
    hook_text_amharic VARCHAR(500),
    is_selected BOOLEAN DEFAULT FALSE,
    heuristic_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploads table: stores YouTube upload metadata
CREATE TABLE IF NOT EXISTS uploads (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(255) REFERENCES videos(video_id),
    render_id INTEGER REFERENCES renders(id),
    thumbnail_id INTEGER REFERENCES thumbnails(id),
    youtube_video_id VARCHAR(255),
    title VARCHAR(500),
    description TEXT,
    tags JSONB,
    chapters JSONB,
    playlist_id VARCHAR(255),
    upload_status VARCHAR(50) DEFAULT 'pending',
    uploaded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Metrics table: stores performance metrics for uploaded videos
CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    upload_id INTEGER REFERENCES uploads(id),
    views BIGINT DEFAULT 0,
    impressions BIGINT DEFAULT 0,
    ctr_percent FLOAT,
    avg_view_duration_seconds FLOAT,
    retention_percent FLOAT,
    likes BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AB Tests table: stores A/B test configurations
CREATE TABLE IF NOT EXISTS ab_tests (
    id SERIAL PRIMARY KEY,
    upload_id INTEGER REFERENCES uploads(id),
    test_type VARCHAR(50), -- 'title', 'thumbnail'
    variant_a TEXT,
    variant_b TEXT,
    variant_c TEXT,
    current_variant VARCHAR(10) DEFAULT 'a',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- Daily Reports table: stores daily summary reports
CREATE TABLE IF NOT EXISTS daily_reports (
    id SERIAL PRIMARY KEY,
    report_date DATE UNIQUE NOT NULL,
    videos_produced INTEGER DEFAULT 0,
    videos_uploaded INTEGER DEFAULT 0,
    total_views BIGINT DEFAULT 0,
    avg_ctr FLOAT,
    avg_retention FLOAT,
    report_json JSONB,
    report_markdown TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Jobs table: stores long-running job state for UI polling (pipeline runs, etc.)
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(64) PRIMARY KEY,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    video_id VARCHAR(255),
    current_step VARCHAR(100),
    progress FLOAT DEFAULT 0,
    request JSONB,
    steps JSONB,
    result JSONB,
    error JSONB,
    events JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_channels_composite_score ON channels(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_views_velocity ON videos(views_velocity DESC);
CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(upload_status);
CREATE INDEX IF NOT EXISTS idx_metrics_recorded_at ON metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
