from locust import HttpUser, task, between

class WebsiteUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def process_task(self):
        self.client.post("https://8000-iz5lc3oxd5dwv9sxwophb-eb8f6cf2.sg1.manus.computer/api/process_task", json={"task_id": "123", "data": "sample_data"})
