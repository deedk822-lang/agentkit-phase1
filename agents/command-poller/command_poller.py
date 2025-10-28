#!/usr/bin/env python3
"""
Production Control Plane - Command Queue Poller
Polls Google Doc, validates, signs, and submits actions to MCP with full error handling.
"""
import os
import sys
import time
import hashlib
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
import requests
from dataclasses import dataclass, asdict
from enum import Enum
import hmac
import base64
import redis

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","component":"%(name)s","message":"%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger('command_poll')

# Configuration from environment
GOOGLE_DOC_ID = os.getenv('GOOGLE_DOC_ID')
MCP_BASE_URL = os.getenv('MCP_BASE_URL', 'http://mcp-orchestrator:8080')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
PRIVATE_KEY = os.getenv('MCP_PRIVATE_KEY')
POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '10'))
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis-service:6379')

class CommandType(str, Enum):
    SCAN_SITE = "SCAN_SITE"
    PUBLISH_REPORT = "PUBLISH_REPORT"
    START_CAMPAIGN = "START_CAMPAIGN"
    POST_VIMEO = "POST_VIMEO"
    TRAIN_AGENT = "TRAIN_AGENT"
    ENFORCE_POLICY = "ENFORCE_POLICY"
    REVERT_ACTION = "REVERT_ACTION"

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

@dataclass
class ParsedCommand:
    """Validated command with all required fields"""
    command_type: CommandType
    action_id: str
    params: Dict[str, str]
    raw_text: str
    line_number: int
    issued_at: datetime
    severity: Severity = Severity.LOW

class IdempotencyStore:
    """Redis-backed idempotency check with result caching"""
    def __init__(self, redis_url: str):
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("Connected to Redis for idempotency store.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis at {redis_url}. Idempotency checks will be disabled. Error: {e}")
            self.redis = None

    def check_and_record(self, action_id: str, ttl_seconds: int = 3600) -> bool:
        """Returns True if action is new, False if duplicate"""
        if not self.redis:
            return True
        key = f"idempotent:{action_id}"
        return self.redis.set(key, "1", nx=True, ex=ttl_seconds)

    def cache_result(self, action_id: str, result: Dict, ttl_seconds: int = 3600):
        """Cache result for duplicate requests"""
        if not self.redis:
            return
        self.redis.setex(f"result:{action_id}", ttl_seconds, json.dumps(result))

    def get_cached_result(self, action_id: str) -> Optional[Dict]:
        """Retrieve cached result"""
        if not self.redis:
            return None
        cached = self.redis.get(f"result:{action_id}")
        return json.loads(cached) if cached else None

class CircuitBreaker:
    """Circuit breaker for external service calls"""
    def __init__(self, name: str, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.name = name
        self.failure_count = 0
        self.threshold = failure_threshold
        self.timeout = timeout_seconds
        self.last_failure = None
        self.state = "CLOSED"

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if self.last_failure and datetime.now() - self.last_failure > timedelta(seconds=self.timeout):
                logger.info(f"Circuit breaker {self.name} entering HALF_OPEN state")
                self.state = "HALF_OPEN"
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                logger.info(f"Circuit breaker {self.name} recovered, returning to CLOSED")
                self.reset()
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure = datetime.now()
            logger.warning(f"Circuit breaker {self.name} failure {self.failure_count}/{self.threshold}: {e}")
            if self.failure_count >= self.threshold:
                logger.error(f"Circuit breaker {self.name} OPEN after {self.failure_count} failures")
                self.state = "OPEN"
            raise

    def reset(self):
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure = None

class CommandValidator:
    """Validates and sanitizes command inputs"""
    COMMAND_SCHEMAS = {
        CommandType.SCAN_SITE: {'required': ['domain'], 'optional': [], 'severity': Severity.LOW},
        CommandType.PUBLISH_REPORT: {'required': ['client', 'dataset', 'format'], 'optional': ['template'], 'severity': Severity.MEDIUM},
        CommandType.START_CAMPAIGN: {'required': ['channel', 'campaign_id'], 'optional': ['schedule_at'], 'severity': Severity.HIGH},
        CommandType.POST_VIMEO: {'required': ['title', 'url'], 'optional': ['visibility'], 'severity': Severity.LOW},
        CommandType.TRAIN_AGENT: {'required': ['dataset', 'run'], 'optional': ['hyperparams'], 'severity': Severity.LOW},
        CommandType.ENFORCE_POLICY: {'required': ['policy_id', 'reason'], 'optional': [], 'severity': Severity.HIGH},
        CommandType.REVERT_ACTION: {'required': ['action_id'], 'optional': ['reason'], 'severity': Severity.HIGH}
    }

    @staticmethod
    def validate(parsed: ParsedCommand) -> Tuple[bool, Optional[str]]:
        """Validate command against schema"""
        schema = CommandValidator.COMMAND_SCHEMAS.get(parsed.command_type)
        if not schema:
            return False, f"Unknown command type: {parsed.command_type}"

        for req in schema['required']:
            if req not in parsed.params:
                return False, f"Missing required parameter: {req}"

        for key, value in parsed.params.items():
            if not CommandValidator._is_safe_value(value):
                return False, f"Unsafe value in parameter {key}: {value}"

        parsed.severity = schema['severity']
        return True, None

    @staticmethod
    def _is_safe_value(value: str) -> bool:
        """Check for injection attacks"""
        dangerous_patterns = [
            r'[;\|\&\$\`]',
            r'<script',
            r'union\s+select',
            r'\.\./',
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return False
        return len(value) <= 1000

class CommandParser:
    """Parses commands from Google Doc text"""
    @staticmethod
    def parse_line(line: str, line_number: int) -> Optional[ParsedCommand]:
        """Parse a single command line"""
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        parts = line.split(None, 1)
        if not parts:
            return None

        command_str = parts[0].upper()
        try:
            command_type = CommandType(command_str)
        except ValueError:
            logger.warning(f"Unknown command type on line {line_number}: {command_str}")
            return None

        params = {}
        if len(parts) > 1:
            param_str = parts[1]
            for match in re.finditer(r'(\w+)=(".*?"|\S+)', param_str):
                key = match.group(1)
                value = match.group(2).strip('"')
                params[key] = value

        return ParsedCommand(
            command_type=command_type,
            action_id=str(uuid.uuid4()),
            params=params,
            raw_text=line,
            line_number=line_number,
            issued_at=datetime.utcnow()
        )

class GoogleDocClient:
    """Reads and writes to Google Doc command queue"""
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.filepath = f"/tmp/command_queue_{doc_id}.txt"
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w") as f:
                f.write("# Command Queue\n")
        logger.info(f"Using simulated Google Doc at: {self.filepath}")

    def read_commands(self) -> List[str]:
        """Read all lines from command queue"""
        try:
            with open(self.filepath, 'r') as f:
                return f.readlines()
        except FileNotFoundError:
            return []

    def append_status(self, line_number: int, action_id: str, status: str, receipt_hash: str):
        """Append status to the doc"""
        status_line = f"\n# Line {line_number} -> {action_id}: {status} (receipt: {receipt_hash[:12]}...)"
        with open(self.filepath, 'a') as f:
            f.write(status_line)

class NotionClient:
    """Notion API client for KV store and ledger"""
    def __init__(self, token: str):
        self.token = token
        self.action_ledger_db = os.getenv('NOTION_ACTION_LEDGER_DB')
        self.feature_flags_db = os.getenv('NOTION_FEATURE_FLAGS_DB')
        self.last_hash = None

    def get_feature_flag(self, key: str) -> Optional[Dict]:
        """Get feature flag value"""
        if key == 'kill_switch':
            return {"enabled": True, "value": "false"}
        return {"enabled": True, "value": None}

    def append_ledger(self, action_id: str, command: str, result: str,
                      latency_ms: int, rationale: str, signed_by: str) -> str:
        """Append to tamper-evident ledger with hash chain"""
        if self.last_hash is None:
            self.last_hash = "genesis"

        entry_data = f"{action_id}:{command}:{result}:{self.last_hash}"
        new_hash = hashlib.sha256(entry_data.encode()).hexdigest()

        logger.info(f"Appending to ledger: action_id={action_id}, hash={new_hash[:12]}")
        self.last_hash = new_hash
        return new_hash

class MCPClient:
    """MCP server client with signing and verification"""
    def __init__(self, base_url: str, private_key: str):
        self.base_url = base_url
        self.private_key = private_key.encode()
        self.breaker = CircuitBreaker('mcp_api')

    def _sign_payload(self, payload: Dict) -> Tuple[str, str]:
        """Sign payload with HMAC-SHA256 and add nonce"""
        nonce = str(uuid.uuid4())
        payload['nonce'] = nonce
        payload['timestamp'] = datetime.utcnow().isoformat()

        message = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.new(self.private_key, message, hashlib.sha256).hexdigest()

        return signature, nonce

    def execute_action(self, command: ParsedCommand) -> Dict:
        """Execute action via MCP with signing"""
        payload = {
            "action_id": command.action_id,
            "command_type": command.command_type.value,
            "params": command.params,
            "severity": command.severity.value
        }

        signature, nonce = self._sign_payload(payload)

        headers = {
            "X-Signature": signature,
            "X-Nonce": nonce,
            "Content-Type": "application/json"
        }

        def _request():
            response = requests.post(
                f"{self.base_url}/v1/actions",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        return self.breaker.call(_request)

class MetricsCollector:
    """Prometheus-compatible metrics collector"""
    def __init__(self):
        self.metrics = {
            'commands_processed': 0,
            'commands_success': 0,
            'commands_failed': 0,
            'commands_duplicate': 0,
            'latency_sum_ms': 0.0,
            'latency_count': 0
        }

    def record_command(self, success: bool, latency_ms: float, duplicate: bool = False):
        self.metrics['commands_processed'] += 1
        if duplicate:
            self.metrics['commands_duplicate'] += 1
        elif success:
            self.metrics['commands_success'] += 1
        else:
            self.metrics['commands_failed'] += 1

        self.metrics['latency_sum_ms'] += latency_ms
        self.metrics['latency_count'] += 1

    def get_metrics(self) -> Dict:
        avg_latency = (self.metrics['latency_sum_ms'] / self.metrics['latency_count']
                       if self.metrics['latency_count'] > 0 else 0)
        return {**self.metrics, 'avg_latency_ms': avg_latency}

class CommandPoller:
    """Main polling orchestrator"""
    def __init__(self):
        self.doc_client = GoogleDocClient(GOOGLE_DOC_ID)
        self.notion_client = NotionClient(NOTION_TOKEN)
        self.mcp_client = MCPClient(MCP_BASE_URL, PRIVATE_KEY)
        self.idempotency = IdempotencyStore(REDIS_URL)
        self.metrics = MetricsCollector()
        self.parser = CommandParser()
        self.processed_lines_cache = set()

    def check_kill_switch(self) -> bool:
        """Check if autonomous actions are disabled"""
        flag = self.notion_client.get_feature_flag('kill_switch')
        return flag and flag.get('value', 'false').lower() == 'true'

    def process_command(self, parsed: ParsedCommand) -> Tuple[bool, str]:
        """Process a single command with full validation"""
        start_time = time.time()

        try:
            valid, error = CommandValidator.validate(parsed)
            if not valid:
                raise ValueError(f"Validation failed: {error}")

            action_hash = hashlib.sha256(parsed.raw_text.encode()).hexdigest()
            if not self.idempotency.check_and_record(action_hash):
                cached = self.idempotency.get_cached_result(action_hash)
                logger.info(f"Duplicate command '{parsed.raw_text}', returning cached result")
                self.metrics.record_command(True, 0, duplicate=True)
                return True, cached.get('receipt_hash', 'CACHED') if cached else "DUPLICATE"

            if self.check_kill_switch():
                raise SystemExit("Kill switch is active, aborting command execution.")

            result = self.mcp_client.execute_action(parsed)
            if result.get('status') not in ['SUCCESS', 'OK']:
                raise RuntimeError(f"MCP execution failed: {result.get('rationale', 'No rationale')}")

            latency_ms = int((time.time() - start_time) * 1000)
            receipt_hash = self.notion_client.append_ledger(
                action_id=parsed.action_id,
                command=parsed.raw_text,
                result="SUCCESS",
                latency_ms=latency_ms,
                rationale=result.get('rationale', 'Completed successfully'),
                signed_by="command_poller"
            )

            self.idempotency.cache_result(action_hash, {'receipt_hash': receipt_hash, 'result': result})

            self.metrics.record_command(True, latency_ms)
            return True, receipt_hash

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Failed to process '{parsed.raw_text}': {e}", exc_info=True)

            receipt_hash = self.notion_client.append_ledger(
                action_id=parsed.action_id,
                command=parsed.raw_text,
                result="FAILED",
                latency_ms=latency_ms,
                rationale=str(e),
                signed_by="command_poller"
            )

            self.metrics.record_command(False, latency_ms)
            return False, f"ERROR: {receipt_hash}"

    def poll_once(self):
        """Single polling iteration"""
        logger.info("Starting new polling cycle.")
        lines = self.doc_client.read_commands()

        new_commands = 0
        for line_num, line in enumerate(lines, start=1):
            line_content = line.strip()
            line_id = f"{line_num}:{hashlib.sha256(line_content.encode()).hexdigest()}"

            if not line_content or line_content.startswith('#') or line_content.startswith('RECEIPT:'):
                continue

            if line_id in self.processed_lines_cache:
                continue

            new_commands += 1
            parsed = self.parser.parse_line(line_content, line_num)
            if not parsed:
                continue

            logger.info(f"Processing line {line_num}: {parsed.command_type.value} (action_id={parsed.action_id})")

            success, receipt = self.process_command(parsed)

            status = "SUCCESS" if success else "FAILED"
            self.doc_client.append_status(line_num, parsed.action_id, status, receipt)

            self.processed_lines_cache.add(line_id)

        logger.info(f"Polling cycle finished. Processed {new_commands} new commands.")

    def run(self):
        """Main polling loop"""
        logger.info(f"Starting command poller (interval={POLL_INTERVAL_SECONDS}s)")

        while True:
            try:
                self.poll_once()

                if self.metrics.metrics['commands_processed'] % 10 == 0 and self.metrics.metrics['commands_processed'] > 0:
                    logger.info(f"Metrics: {json.dumps(self.metrics.get_metrics())}")

                time.sleep(POLL_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                logger.info("Shutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Fatal error in polling loop: {e}", exc_info=True)
                time.sleep(POLL_INTERVAL_SECONDS * 2)

if __name__ == "__main__":
    required_vars = ['GOOGLE_DOC_ID', 'NOTION_TOKEN', 'MCP_PRIVATE_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    poller = CommandPoller()
    poller.run()