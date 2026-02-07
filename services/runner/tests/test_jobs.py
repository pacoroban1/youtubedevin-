import unittest

from modules.database import Database
from modules.jobs import JobStore


class TestJobStore(unittest.TestCase):
    def test_create_get_update(self):
        db = Database()
        store = JobStore(db)

        job = store.create_job(
            "unit_test",
            request={"hello": "world"},
            steps={"step_a": {"status": "pending"}},
        )
        self.assertEqual(job.job_type, "unit_test")
        self.assertEqual(job.status, "queued")
        self.assertIsNotNone(job.id)

        store.update_job(job.id, status="running", current_step="step_a", progress=0.25)
        job2 = store.get_job(job.id)
        self.assertEqual(job2.status, "running")
        self.assertEqual(job2.current_step, "step_a")
        self.assertAlmostEqual(job2.progress, 0.25, places=3)

        store.append_event(job.id, "hello")
        job3 = store.get_job(job.id)
        self.assertTrue(isinstance(job3.events, list))
        self.assertGreaterEqual(len(job3.events), 2)

