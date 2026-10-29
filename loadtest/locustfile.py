"""
Load scenarios for the Task API.

Run one scenario by naming its class, e.g.:
  locust -f locustfile.py WriteUsers     (users only create data)
  locust -f locustfile.py ReadUsers      (users only read data)
  locust -f locustfile.py MixedUsers     (realistic mix, the default baseline)
"""
import random
from locust import HttpUser, task, between


def new_task_payload():
    n = random.randint(1, 10_000_000)
    return {"title": f"Task {n}", "description": "load test row " * 5}


class WriteUsers(HttpUser):
    """100 users adding data."""
    wait_time = between(0.2, 1)

    @task
    def create(self):
        self.client.post("/api/tasks", json=new_task_payload(), name="POST /api/tasks")


class ReadUsers(HttpUser):
    """100 users reading data (only existing ids, so cache hits are realistic)."""
    wait_time = between(0.2, 1)

    def on_start(self):
        r = self.client.get("/api/tasks?limit=100", name="setup: GET /api/tasks")
        self.ids = [t["id"] for t in r.json()] if r.status_code == 200 else []

    @task(3)
    def list_tasks(self):
        self.client.get("/api/tasks?limit=50", name="GET /api/tasks")

    @task(5)
    def read_one(self):
        if self.ids:
            self.client.get(f"/api/tasks/{random.choice(self.ids)}", name="GET /api/tasks/{id}")


class ReadHeavyUsers(HttpUser):
    """Typical web traffic: about 90% reads, 10% writes."""
    wait_time = between(0.2, 1)

    def on_start(self):
        r = self.client.get("/api/tasks?limit=100", name="setup: GET /api/tasks")
        self.ids = [t["id"] for t in r.json()] if r.status_code == 200 else []

    @task(8)
    def list_tasks(self):
        self.client.get("/api/tasks?limit=50", name="GET /api/tasks")

    @task(10)
    def read_one(self):
        if self.ids:
            self.client.get(f"/api/tasks/{random.choice(self.ids)}", name="GET /api/tasks/{id}")

    @task(1)
    def update(self):
        if self.ids:
            self.client.patch(f"/api/tasks/{random.choice(self.ids)}",
                              json={"done": random.choice([True, False])},
                              name="PATCH /api/tasks/{id}")

    @task(1)
    def create(self):
        self.client.post("/api/tasks", json=new_task_payload(), name="POST /api/tasks")


class MixedUsers(HttpUser):
    """Realistic mix: mostly reads, some writes and updates."""
    wait_time = between(0.2, 1)

    def on_start(self):
        self.ids = []
        for _ in range(3):
            r = self.client.post("/api/tasks", json=new_task_payload(), name="POST /api/tasks")
            if r.ok:
                self.ids.append(r.json()["id"])

    @task(5)
    def list_tasks(self):
        self.client.get("/api/tasks?limit=50", name="GET /api/tasks")

    @task(4)
    def read_one(self):
        if self.ids:
            self.client.get(f"/api/tasks/{random.choice(self.ids)}", name="GET /api/tasks/{id}")

    @task(2)
    def create(self):
        r = self.client.post("/api/tasks", json=new_task_payload(), name="POST /api/tasks")
        if r.ok:
            self.ids.append(r.json()["id"])

    @task(2)
    def update(self):
        if self.ids:
            self.client.patch(f"/api/tasks/{random.choice(self.ids)}",
                              json={"done": random.choice([True, False])},
                              name="PATCH /api/tasks/{id}")
