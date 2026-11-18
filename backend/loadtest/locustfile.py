import json
import os
import random
from locust import HttpUser, task, between

CONTEXT_PATH = os.path.join(os.path.dirname(__file__), "test_context.json")
TOKENS = []
COURSE_IDS = []

if os.path.exists(CONTEXT_PATH):
    with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        TOKENS = data.get("tokens", [])
        COURSE_IDS = data.get("course_ids", [])

QUESTIONS = [
    "How does Raft handle a split vote during leader election?",
    "What is the Log Matching Property in Raft?",
    "How does Consistent Hashing distribute keys around a ring?",
    "What is Hinted Handoff in Amazon Dynamo?",
    "What is the purpose of Merkle Trees in anti-entropy?",
    "How do vector clocks detect concurrent write conflicts?",
    "What are the three core states of a Raft server node?",
    "Why does Dynamo use sloppy quorums rather than strict quorums?",
]


class ClassVaultUser(HttpUser):
    wait_time = between(0.1, 0.4)

    def on_start(self):
        self.token = random.choice(TOKENS) if TOKENS else ""
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.course_id = random.choice(COURSE_IDS) if COURSE_IDS else None

    @task(6)
    def ask_chat_rag(self):
        """Ask course question via RAG."""
        if not self.course_id or not self.token:
            return
        question = random.choice(QUESTIONS)
        with self.client.post(
            f"/courses/{self.course_id}/chat",
            json={"question": question},
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(4)
    def browse_courses(self):
        """Browse courses list."""
        with self.client.get("/courses", headers=self.headers, catch_response=True) as response:
            if response.status_code in (200, 429):
                response.success()
            else:
                response.failure(f"Failed browsing courses: {response.status_code}")

    @task(3)
    def get_course_detail(self):
        """Fetch course detail."""
        if not self.course_id:
            return
        with self.client.get(f"/courses/{self.course_id}", headers=self.headers, catch_response=True) as response:
            if response.status_code in (200, 403, 404, 429):
                response.success()
            else:
                response.failure(f"Failed getting course: {response.status_code}")

    @task(2)
    def check_health(self):
        """Check system health probe."""
        self.client.get("/health")
