#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import redis
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

# --- Helper to Read Mounted Secrets ---
def get_secret(secret_name: str) -> str:
    """Reads a secret from the file mounted by the CSI driver."""
    path = f"/mnt/secrets/{secret_name}"
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"CRITICAL: Secret file not found at {path}. Check the CSI driver and SecretProviderClass.")
        sys.exit(1)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('command_poller')

# Secrets are now loaded from files
NOTION_TOKEN = get_secret("NOTION_TOKEN")
PRIVATE_KEY = get_secret("MCP_PRIVATE_KEY")
GOOGLE_DOC_ID = get_secret("GOOGLE_DOC_ID")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-orchestrator:8080")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-service:6379")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))

# Redis client for distributed locking
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"CRITICAL: Could not connect to Redis at {REDIS_URL}. High Availability is compromised. Error: {e}")
    sys.exit(1)

# --- Data Classes and Enums ---
class CommandType(Enum):
    EXTRACT = "EXTRACT"
    EXECUTE = "EXECUTE"
    LEARN = "LEARN"

class Severity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class ParsedCommand:
    line_num: int
    raw_line: str
    command_type: CommandType
    severity: Severity
    payload: str

# --- Clients ---
class GoogleDocClient:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        # Mock implementation for reading commands
        self.mock_commands = [
            "[EXTRACT|LOW] https://example.com/article1",
            "[EXECUTE|HIGH] /usr/local/bin/run_maintenance_script.sh --all",
            "This is just a comment, ignore.",
            "[LEARN|MEDIUM] New feature release notes located at /docs/new_feature.md",
            "[EXTRACT|CRITICAL] https://internal.security.alert/critical_vulnerability"
        ]

    def read_commands(self) -> List[str]:
        logger.info(f"Reading commands from Google Doc: {self.doc_id}")
        # In a real implementation, this would use the Google Docs API
        return self.mock_commands

class NotionClient:
    def __init__(self, token):
        self.token = token

    def store_extraction(self, content: str):
        logger.info(f"Storing extracted content to Notion: {content[:50]}...")
        # Mock implementation
        pass

class MCPClient:
    def __init__(self, base_url, private_key):
        self.base_url = base_url
        self.private_key = private_key

    def send_command(self, command: ParsedCommand):
        logger.info(f"Sending command to MCP Orchestrator: {command.command_type.value} - {command.payload}")
        # Mock implementation
        pass

# --- Core Logic ---
class CommandParser:
    def parse_line(self, line_num: int, line: str) -> Optional[ParsedCommand]:
        line = line.strip()
        if not line.startswith("[") or "]" not in line:
            return None
        try:
            parts = line[1:].split(']')
            meta = parts[0].split('|')
            command_type = CommandType[meta[0].upper()]
            severity = Severity[meta[1].upper()]
            payload = parts[1].strip()
            return ParsedCommand(line_num, line, command_type, severity, payload)
        except (KeyError, IndexError):
            logger.warning(f"Line {line_num}: Could not parse command: '{line}'")
            return None

class CommandPoller:
    def __init__(self):
        self.doc_client = GoogleDocClient(GOOGLE_DOC_ID)
        self.notion_client = NotionClient(NOTION_TOKEN)
        self.mcp_client = MCPClient(MCP_BASE_URL, PRIVATE_KEY)
        self.parser = CommandParser()
        self.processed_lines = set()

    def poll_once(self):
        """
        Single polling iteration with a distributed lock to ensure only one
        replica processes commands at a time.
        """
        lock_key = "command-poller-lock"
        lock_acquired = redis_client.set(lock_key, "running", nx=True, ex=30)

        if not lock_acquired:
            logger.info("Another poller instance holds the lock. Skipping this cycle.")
            return

        logger.info("Lock acquired. Starting poll cycle...")
        try:
            lines = self.doc_client.read_commands()
            for i, line in enumerate(lines, start=1):
                if i in self.processed_lines:
                    continue

                command = self.parser.parse_line(i, line)
                if command:
                    logger.info(f"Processing new command from line {i}: {command.command_type.value}")
                    if command.command_type == CommandType.EXTRACT:
                        self.notion_client.store_extraction(command.payload)
                    else:
                        self.mcp_client.send_command(command)
                self.processed_lines.add(i)
        except Exception as e:
            logger.error(f"An error occurred during the poll cycle: {e}", exc_info=True)
        finally:
            logger.info("Releasing poller lock.")
            redis_client.delete(lock_key)

    def run(self):
        logger.info("Starting Command Poller in HA mode...")
        while True:
            self.poll_once()
            logger.info(f"Sleeping for {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    poller = CommandPoller()
    poller.run()
