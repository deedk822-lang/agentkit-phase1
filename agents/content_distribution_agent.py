#!/usr/bin/env python3
"""
Content-Distribution Agent
Consumes tasks from Redis, loads content file, simulates posting to platforms.
"""
import os
import json
import time
import yaml
import redis
import logging
import pathlib
import argparse
from typing import Dict

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("distributor")

# ---------- config ----------
# The Dockerfile for distributor copies config.yaml to /app, so we don't need parents[1]
CFG = yaml.safe_load(pathlib.Path("config.yaml").read_text())["content_distribution"]
PLATFORMS = CFG["platforms"]

# ---------- Redis ----------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# ---------- core ----------
class Distributor:
    def distribute(self, content: str) -> Dict[str, str]:
        """Simulate posting to every platform."""
        results = {}
        for platform in PLATFORMS:
            log.info("Posting to %s: %.40s...", platform, content)
            results[platform] = "simulated_success"
        return results

    def handle_task(self, task: Dict):
        content_file = pathlib.Path(task["params"]["content_file"])
        if not content_file.exists():
            log.error("Content file not found: %s", content_file)
            return
        content = content_file.read_text()
        results = self.distribute(content)
        log.info("Distribution complete: %s", results)

    def consume_loop(self):
        log.info("Distributor started (CTRL-C to stop)")
        while True:
            _, raw = r.brpop("agent_tasks")  # blocking pop
            task = json.loads(raw)
            if task.get("type") == "DISTRIBUTE_CONTENT":
                self.handle_task(task)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", help="Local test file (bypass Redis)")
    args = parser.parse_args()

    if args.content:
        # Local test mode
        content = pathlib.Path(args.content).read_text()
        Distributor().distribute(content)
    else:
        # Production mode
        Distributor().consume_loop()
