#!/usr/bin/env python3
"""
Command-Poller Agent
Polls a Google Doc (simulated via local file), validates commands,
pushes them onto a Redis bus, and logs to Notion.
"""
import os
import sys
import json
import time
import yaml
import redis
import hashlib
import logging
import pathlib
import datetime
from typing import Dict, List, Optional
from cerberus import Validator

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("poller")

# ---------- config ----------
CONFIG_PATH = pathlib.Path(__file__).parents[1] / "config.yaml"
if not CONFIG_PATH.exists():
    log.critical("config.yaml not found at %s", CONFIG_PATH)
    sys.exit(1)
CFG = yaml.safe_load(CONFIG_PATH.read_text())["command_poller"]

# ---------- Redis ----------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# ---------- command schemas ----------
SCHEMAS = {
    "SCAN_SITE": {"domain": {"type": "string", "required": True}},
    "PUBLISH_REPORT": {
        "client": {"type": "string", "required": True},
        "dataset": {"type": "string", "required": True},
        "format": {"type": "string", "required": True, "allowed": ["pdf", "csv"]},
    },
    "DISTRIBUTE_CONTENT": {"content_file": {"type": "string", "required": True}},
}

# ---------- helpers ----------
def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _hash(cmd: str) -> str:
    return hashlib.sha256(cmd.encode()).hexdigest()[:12]

def _read_google_doc() -> List[str]:
    """Simulated Google Doc reader (local file)."""
    queue_file = pathlib.Path(__file__).parents[1] / "command_queue.txt"
    if not queue_file.exists():
        queue_file.write_text("# Add commands here\n")
    return [l.strip() for l in queue_file.read_text().splitlines() if l.strip() and not l.startswith("#")]

def _log_notion(line: int, cmd: str, status: str, receipt: str):
    """Simulated Notion audit log."""
    log.info("AUDIT line=%s cmd=%s status=%s receipt=%s", line, cmd, status, receipt)

# ---------- core ----------
class Poller:
    def __init__(self):
        self.processed: set[str] = set()

    def validate(self, raw: str) -> Optional[Dict]:
        parts = raw.split()
        cmd_type = parts[0].upper()
        if cmd_type not in SCHEMAS:
            log.warning("Unknown command: %s", cmd_type)
            return None
        params = {p.split("=")[0]: p.split("=")[1] for p in parts[1:] if "=" in p}
        v = Validator(SCHEMAS[cmd_type])
        if not v.validate(params):
            log.warning("Validation failed for %s: %s", cmd_type, v.errors)
            return None
        return {"type": cmd_type, "params": params, "raw": raw}

    def push_to_bus(self, task: Dict):
        """Push validated task onto Redis list (A2A bus)."""
        task["id"] = _hash(task["raw"])
        task["ts"] = _now()
        r.lpush("agent_tasks", json.dumps(task))
        log.info("Pushed task %s to bus", task["id"])

    def run_once(self):
        for line_num, line in enumerate(_read_google_doc(), 1):
            if line in self.processed:
                continue
            task = self.validate(line)
            if not task:
                _log_notion(line_num, line, "FAILED", "invalid")
                continue
            self.push_to_bus(task)
            _log_notion(line_num, line, "SUCCESS", task["id"])
            self.processed.add(line)

    def run_forever(self):
        log.info("Poller started (CTRL-C to stop)")
        try:
            while True:
                self.run_once()
                time.sleep(5)
        except KeyboardInterrupt:
            log.info("Poller stopped")

if __name__ == "__main__":
    Poller().run_forever()
