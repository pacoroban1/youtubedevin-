"""
Quiz Content Generator Engine
Automated quiz video creation - "Find the odd one" style.
High engagement with medium RPM.
"""

import os
import asyncio
import json
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import httpx


class QuizContentGenerator:
    """
    Generates quiz-style content like "Find the odd one" videos.
    
    Features:
    - Multiple quiz formats
    - Auto-generated questions
    - Visual puzzle creation
    - Multi-language support
    - Engagement optimization
    - Answer reveal timing
    """
    
    # Quiz format templates
    QUIZ_FORMATS = {
        "find_odd": {
            "name": "Find the Odd One",
            "description": "Find the different item among similar ones",
            "difficulty_levels": ["easy", "medium", "hard", "expert"],
            "time_per_question": 10,
            "rpm_estimate": 4
        },
        "spot_difference": {
            "name": "Spot the Difference",
            "description": "Find differences between two images",
            "difficulty_levels": ["easy", "medium", "hard"],
            "time_per_question": 15,
            "rpm_estimate": 5
        },
        "emoji_puzzle": {
            "name": "Emoji Puzzle",
            "description": "Guess the word/movie/song from emojis",
            "difficulty_levels": ["easy", "medium", "hard"],
            "time_per_question": 12,
            "rpm_estimate": 4
        },
        "trivia": {
            "name": "Trivia Quiz",
            "description": "General knowledge questions",
            "difficulty_levels": ["easy", "medium", "hard", "expert"],
            "time_per_question": 8,
            "rpm_estimate": 3
        },
        "brain_teaser": {
            "name": "Brain Teaser",
            "description": "Logic puzzles and riddles",
            "difficulty_levels": ["medium", "hard", "expert"],
            "time_per_question": 20,
            "rpm_estimate": 5
        },
        "visual_math": {
            "name": "Visual Math",
            "description": "Math puzzles with images",
            "difficulty_levels": ["easy", "medium", "hard"],
            "time_per_question": 15,
            "rpm_estimate": 4
        },
    }
    
    # Topic categories for quiz content
    TOPICS = {
        "animals": ["dogs", "cats", "birds", "fish", "insects", "wild animals"],
        "food": ["fruits", "vegetables", "desserts", "drinks", "fast food"],
        "flags": ["european", "asian", "african", "american", "oceanian"],
        "logos": ["tech", "cars", "sports", "fashion", "food brands"],
        "movies": ["action", "comedy", "horror", "animation", "classic"],
        "music": ["pop", "rock", "hip hop", "classical", "country"],
        "sports": ["football", "basketball", "tennis", "olympics", "extreme"],
        "geography": ["capitals", "landmarks", "mountains", "rivers", "islands"],
        "science": ["space", "chemistry", "biology", "physics", "inventions"],
        "history": ["ancient", "medieval", "modern", "wars", "leaders"],
    }
    
    def __init__(self, db):
        self.db = db
        self.output_dir = os.getenv("MEDIA_DIR", "/app/media")
        self.quiz_dir = os.path.join(self.output_dir, "quiz")
        os.makedirs(self.quiz_dir, exist_ok=True)
        
        # API keys
        self.openai_key = os.getenv("OPENAI_API_KEY")
        
        # Video settings
        self.resolution = "1920x1080"
        self.fps = 30
        
        # Sound effects paths
        self.sfx_dir = os.path.join(self.output_dir, "sfx")
        os.makedirs(self.sfx_dir, exist_ok=True)
        
    async def generate_quiz_video(
        self,
        format_type: str,
        topic: str,
        num_questions: int = 10,
        difficulty: str = "medium",
        language: str = "en",
        include_timer: bool = True,
        include_score: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a complete quiz video.
        
        Args:
            format_type: Quiz format (find_odd, trivia, etc.)
            topic: Topic category
            num_questions: Number of questions
            difficulty: Difficulty level
            language: Language code
            include_timer: Show countdown timer
            include_score: Show running score
            
        Returns:
            Generated video info
        """
        format_config = self.QUIZ_FORMATS.get(format_type, self.QUIZ_FORMATS["find_odd"])
        
        # Generate questions
        questions = await self._generate_questions(
            format_type,
            topic,
            num_questions,
            difficulty,
            language
        )
        
        # Generate visuals for each question
        visuals = await self._generate_visuals(questions, format_type)
        
        # Create video segments
        segments = []
        for i, (question, visual) in enumerate(zip(questions, visuals)):
            segment = await self._create_question_segment(
                question,
                visual,
                i + 1,
                num_questions,
                format_config["time_per_question"],
                include_timer,
                include_score
            )
            segments.append(segment)
            
        # Concatenate segments
        output_filename = f"quiz_{format_type}_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        output_path = os.path.join(self.quiz_dir, output_filename)
        
        final_video = await self._concatenate_segments(segments, output_path)
        
        # Add intro and outro
        final_video = await self._add_quiz_intro_outro(
            final_video,
            format_config["name"],
            topic,
            difficulty,
            output_path
        )
        
        # Generate metadata
        metadata = await self._generate_quiz_metadata(
            format_type,
            topic,
            difficulty,
            num_questions,
            language
        )
        
        # Save to database
        video_id = await self.db.fetchval("""
            INSERT INTO quiz_videos 
            (format_type, topic, difficulty, num_questions, language, video_path, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            RETURNING id
        """, format_type, topic, difficulty, num_questions, language, 
            final_video, json.dumps(metadata))
            
        return {
            "video_id": video_id,
            "format": format_type,
            "topic": topic,
            "difficulty": difficulty,
            "num_questions": num_questions,
            "video_path": final_video,
            "metadata": metadata,
            "rpm_estimate": format_config["rpm_estimate"],
            "questions": questions
        }
        
    async def _generate_questions(
        self,
        format_type: str,
        topic: str,
        num_questions: int,
        difficulty: str,
        language: str
    ) -> List[Dict[str, Any]]:
        """Generate quiz questions using AI."""
        if not self.openai_key:
            return self._generate_fallback_questions(format_type, topic, num_questions)
            
        format_config = self.QUIZ_FORMATS.get(format_type, {})
        
        prompt = f"""Generate {num_questions} {format_config.get('name', format_type)} quiz questions about {topic}.

Difficulty: {difficulty}
Language: {language}

For each question, provide:
1. The question/puzzle description
2. The options (if applicable)
3. The correct answer
4. A brief explanation

Format as JSON array with objects containing:
- "question": string
- "options": array of strings (if applicable)
- "correct_answer": string or index
- "explanation": string
- "visual_hint": string (description for image generation)

Make questions engaging and appropriate for YouTube audience."""

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_key}"},
                    json={
                        "model": "gpt-4",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.8,
                    },
                    timeout=60.0
                )
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Parse JSON from response
                import re
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    questions = json.loads(json_match.group())
                    return questions[:num_questions]
                    
            except Exception as e:
                print(f"Error generating questions: {e}")
                
        return self._generate_fallback_questions(format_type, topic, num_questions)
        
    def _generate_fallback_questions(
        self,
        format_type: str,
        topic: str,
        num_questions: int
    ) -> List[Dict[str, Any]]:
        """Generate fallback questions without AI."""
        questions = []
        
        # Simple templates for different formats
        templates = {
            "find_odd": [
                {"question": "Find the odd one out", "options": ["A", "B", "C", "D"], "correct_answer": 2},
                {"question": "Which one doesn't belong?", "options": ["A", "B", "C", "D"], "correct_answer": 1},
            ],
            "trivia": [
                {"question": f"What is the capital of {topic}?", "options": ["A", "B", "C", "D"], "correct_answer": 0},
                {"question": f"Which {topic} is the largest?", "options": ["A", "B", "C", "D"], "correct_answer": 2},
            ],
            "emoji_puzzle": [
                {"question": "Guess the movie from emojis", "options": ["Movie A", "Movie B", "Movie C"], "correct_answer": 1},
            ],
        }
        
        template_list = templates.get(format_type, templates["trivia"])
        
        for i in range(num_questions):
            template = template_list[i % len(template_list)].copy()
            template["explanation"] = f"The correct answer is option {template['correct_answer'] + 1}"
            template["visual_hint"] = f"{topic} related image"
            questions.append(template)
            
        return questions
        
    async def _generate_visuals(
        self,
        questions: List[Dict[str, Any]],
        format_type: str
    ) -> List[str]:
        """Generate visual assets for questions."""
        visuals = []
        
        for i, question in enumerate(questions):
            visual_path = os.path.join(
                self.quiz_dir,
                f"visual_{i}_{datetime.now().timestamp()}.png"
            )
            
            # Create visual based on format
            if format_type == "find_odd":
                await self._create_find_odd_visual(question, visual_path)
            elif format_type == "emoji_puzzle":
                await self._create_emoji_visual(question, visual_path)
            else:
                await self._create_generic_visual(question, visual_path)
                
            visuals.append(visual_path)
            
        return visuals
        
    async def _create_find_odd_visual(
        self,
        question: Dict[str, Any],
        output_path: str
    ):
        """Create visual for find the odd one quiz."""
        # Use ffmpeg to create a grid of images
        # For now, create a placeholder
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={self.resolution}:d=1",
            "-vf", f"drawtext=text='Find the Odd One':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=100",
            "-frames:v", "1",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
    async def _create_emoji_visual(
        self,
        question: Dict[str, Any],
        output_path: str
    ):
        """Create visual for emoji puzzle."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={self.resolution}:d=1",
            "-vf", f"drawtext=text='Emoji Puzzle':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=100",
            "-frames:v", "1",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
    async def _create_generic_visual(
        self,
        question: Dict[str, Any],
        output_path: str
    ):
        """Create generic quiz visual."""
        question_text = question.get("question", "Question")[:50]
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={self.resolution}:d=1",
            "-vf", f"drawtext=text='{question_text}':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-frames:v", "1",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
    async def _create_question_segment(
        self,
        question: Dict[str, Any],
        visual_path: str,
        question_num: int,
        total_questions: int,
        time_seconds: int,
        include_timer: bool,
        include_score: bool
    ) -> str:
        """Create video segment for a single question."""
        segment_path = visual_path.replace(".png", "_segment.mp4")
        
        # Build filter complex
        filters = []
        
        # Question number overlay
        filters.append(f"drawtext=text='Question {question_num}/{total_questions}':fontsize=36:fontcolor=yellow:x=50:y=50")
        
        # Timer overlay
        if include_timer:
            filters.append(f"drawtext=text='%{{eif\\:({time_seconds}-t)\\:d}}':fontsize=72:fontcolor=red:x=w-150:y=50:enable='lt(t,{time_seconds})'")
            
        filter_str = ",".join(filters) if filters else "null"
        
        # Create segment with question display + answer reveal
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", visual_path,
            "-t", str(time_seconds + 3),  # Extra 3 seconds for answer reveal
            "-vf", filter_str,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            segment_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        return segment_path
        
    async def _concatenate_segments(
        self,
        segments: List[str],
        output_path: str
    ) -> str:
        """Concatenate video segments."""
        # Create concat file
        concat_file = os.path.join(self.quiz_dir, "concat_list.txt")
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")
                
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        # Cleanup
        os.unlink(concat_file)
        for segment in segments:
            if os.path.exists(segment):
                os.unlink(segment)
                
        return output_path
        
    async def _add_quiz_intro_outro(
        self,
        video_path: str,
        quiz_name: str,
        topic: str,
        difficulty: str,
        output_path: str
    ) -> str:
        """Add intro and outro to quiz video."""
        # For now, just add text overlay at start
        temp_output = output_path.replace(".mp4", "_final.mp4")
        
        intro_text = f"{quiz_name}"
        subtitle_text = f"{topic.title()} - {difficulty.title()}"
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"drawtext=text='{intro_text}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-50:enable='lt(t,3)',drawtext=text='{subtitle_text}':fontsize=48:fontcolor=yellow:x=(w-text_w)/2:y=(h-text_h)/2+50:enable='lt(t,3)'",
            "-c:a", "copy",
            temp_output
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        # Replace original
        if os.path.exists(temp_output):
            os.rename(temp_output, output_path)
            
        return output_path
        
    async def _generate_quiz_metadata(
        self,
        format_type: str,
        topic: str,
        difficulty: str,
        num_questions: int,
        language: str
    ) -> Dict[str, Any]:
        """Generate YouTube metadata for quiz video."""
        format_config = self.QUIZ_FORMATS.get(format_type, {})
        format_name = format_config.get("name", format_type.replace("_", " ").title())
        
        title = f"{format_name} - {topic.title()} Edition | {difficulty.title()} | Can You Beat It?"
        
        description = f"""Test your skills with this {format_name} quiz!

Topic: {topic.title()}
Difficulty: {difficulty.title()}
Questions: {num_questions}

How many can you get right? Comment your score below!

Rules:
- Watch each question carefully
- Try to answer before the timer runs out
- No cheating! 😄

Like and subscribe for more quizzes!

#quiz #{format_type.replace('_', '')} #{topic} #brainteaser #puzzle"""

        tags = [
            format_name.lower(),
            "quiz",
            topic,
            "brain teaser",
            "puzzle",
            "find the odd one",
            "test your brain",
            f"{difficulty} quiz",
            "riddles",
            "challenge"
        ]
        
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "category": "Entertainment",
            "language": language
        }
        
    def get_available_formats(self) -> List[Dict[str, Any]]:
        """Get list of available quiz formats."""
        return [
            {
                "code": code,
                **config
            }
            for code, config in self.QUIZ_FORMATS.items()
        ]
        
    def get_available_topics(self) -> Dict[str, List[str]]:
        """Get list of available topics."""
        return self.TOPICS
        
    async def generate_batch_quizzes(
        self,
        formats: List[str],
        topics: List[str],
        num_per_combo: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple quiz videos in batch.
        
        Args:
            formats: List of quiz formats
            topics: List of topics
            num_per_combo: Number of videos per format/topic combination
            
        Returns:
            List of generated video info
        """
        results = []
        
        for format_type in formats:
            for topic in topics:
                for _ in range(num_per_combo):
                    try:
                        result = await self.generate_quiz_video(
                            format_type=format_type,
                            topic=topic,
                            num_questions=10,
                            difficulty=random.choice(["easy", "medium", "hard"])
                        )
                        results.append(result)
                    except Exception as e:
                        print(f"Error generating {format_type}/{topic}: {e}")
                        
        return results
