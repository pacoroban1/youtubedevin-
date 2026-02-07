import os
import subprocess
import tempfile
import unittest

from modules.timing import TimingMatcher


class TestTimingRender(unittest.IsolatedAsyncioTestCase):
    async def test_render_slows_video_when_audio_longer(self):
        tm = TimingMatcher(db=None)

        with tempfile.TemporaryDirectory() as td:
            src_video = os.path.join(td, "src.mp4")
            src_audio = os.path.join(td, "audio.wav")
            out_video = os.path.join(td, "out.mp4")

            # 2s video
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=640x360:rate=30",
                    "-t",
                    "2",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:v",
                    "libx264",
                    src_video,
                ],
                check=True,
            )

            # 12s audio so the >5s mismatch path is exercised.
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-t",
                    "12",
                    src_audio,
                ],
                check=True,
            )

            ok = await tm._render_video(src_video, src_audio, out_video, alignment_map=[])
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(out_video))

            dur = await tm._get_video_duration(out_video)
            # Without setpts this would stay ~2s due to -shortest.
            self.assertGreater(dur, 9.0, f"expected slowed output near audio duration, got {dur}")

