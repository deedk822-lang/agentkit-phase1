#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import redis
import requests
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
import hashlib
import hmac

# --- Helper to Read Mounted Secrets ---
def get_secret(secret_name: str) -> str:
    """Reads a secret from the file mounted by the CSI driver."""
    path = f"/mnt/secrets/{secret_name}"
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback to environment variables for local development
        env_var = secret_name.upper().replace('-', '_')
        value = os.getenv(env_var)
        if value:
            return value
        logger.error(f"CRITICAL: Secret file not found at {path} and env var {env_var} not set.")
        return ""

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('command_poller')

# Secrets are loaded from files or environment
NOTION_TOKEN = get_secret("NOTION_TOKEN") or os.getenv("NOTION_TOKEN")
PRIVATE_KEY = get_secret("MCP_PRIVATE_KEY") or os.getenv("MCP_PRIVATE_KEY", "dev-key")
GOOGLE_DOC_ID = get_secret("GOOGLE_DOC_ID") or os.getenv("GOOGLE_DOC_ID")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-orchestrator-service:8080")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-service:6379")

# Redis client for distributed locking
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"CRITICAL: Could not connect to Redis at {REDIS_URL}. High Availability is compromised. Error: {e}")
    # In development, continue without Redis
    redis_client = None

# --- ENUMS ---
class CommandType(str, Enum):
    SCAN_SITE = "SCAN_SITE"
    PUBLISH_REPORT = "PUBLISH_REPORT"
    START_CAMPAIGN = "START_CAMPAIGN"
    CHECK_INTEGRATION_STATUS = "CHECK_INTEGRATION_STATUS"
    REFRESH_TOKEN = "REFRESH_TOKEN"
    CONNECT_INTEGRATION = "CONNECT_INTEGRATION"

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

# --- DATA CLASSES ---
@dataclass
class ParsedCommand:
    line_number: int
    raw_text: str
    command_type: Optional[CommandType]
    params: Dict
    severity: Severity
    valid: bool
    error_message: Optional[str] = None

# --- COMMAND VALIDATOR ---
class Validator:
    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        return bool(domain and '.' in domain and len(domain) > 3)
    
    @staticmethod
    def is_valid_campaign_id(campaign_id: str) -> bool:
        return bool(campaign_id and len(campaign_id) >= 3)
    
    @staticmethod
    def is_valid_service(service: str) -> bool:
        valid_services = ['meta_lead_ads', 'linkedin', 'mailchimp', 'squarespace_commerce']
        return service in valid_services

# --- COMMAND PARSER ---
class CommandParser:
    def __init__(self):
        self.validator = Validator()
    
    def parse_line(self, line_number: int, line: str) -> ParsedCommand:
        line = line.strip()
        
        if not line or line.startswith('#'):
            return ParsedCommand(
                line_number=line_number,
                raw_text=line,
                command_type=None,
                params={},
                severity=Severity.LOW,
                valid=False,
                error_message="Empty or comment line"
            )
        
        # Parse command format: COMMAND_TYPE param1=value1 param2=value2
        parts = line.split()
        if not parts:
            return ParsedCommand(
                line_number=line_number,
                raw_text=line,
                command_type=None,
                params={},
                severity=Severity.LOW,
                valid=False,
                error_message="No command found"
            )
        
        command_str = parts[0].upper()
        try:
            command_type = CommandType(command_str)
        except ValueError:
            return ParsedCommand(
                line_number=line_number,
                raw_text=line,
                command_type=None,
                params={},
                severity=Severity.LOW,
                valid=False,
                error_message=f"Unknown command: {command_str}"
            )
        
        # Parse parameters
        params = {}
        for param_str in parts[1:]:
            if '=' in param_str:
                key, value = param_str.split('=', 1)
                params[key.strip()] = value.strip()
        
        # Validate command and parameters
        valid, error_message, severity = self._validate_command(command_type, params)
        
        return ParsedCommand(
            line_number=line_number,
            raw_text=line,
            command_type=command_type,
            params=params,
            severity=severity,
            valid=valid,
            error_message=error_message
        )
    
    def _validate_command(self, command_type: CommandType, params: Dict) -> tuple[bool, Optional[str], Severity]:
        if command_type == CommandType.SCAN_SITE:
            if 'domain' not in params:
                return False, "Missing domain parameter", Severity.LOW
            if not self.validator.is_valid_domain(params['domain']):
                return False, "Invalid domain format", Severity.LOW
            return True, None, Severity.LOW
        
        elif command_type == CommandType.START_CAMPAIGN:
            if 'campaign_id' not in params:
                return False, "Missing campaign_id parameter", Severity.MEDIUM
            if not self.validator.is_valid_campaign_id(params['campaign_id']):
                return False, "Invalid campaign_id format", Severity.MEDIUM
            return True, None, Severity.MEDIUM
        
        elif command_type == CommandType.CHECK_INTEGRATION_STATUS:
            if 'service' not in params:
                return False, "Missing service parameter", Severity.LOW
            if not self.validator.is_valid_service(params['service']):
                return False, "Invalid service name", Severity.LOW
            return True, None, Severity.LOW
        
        elif command_type == CommandType.REFRESH_TOKEN:
            if 'service' not in params:
                return False, "Missing service parameter", Severity.MEDIUM
            if not self.validator.is_valid_service(params['service']):
                return False, "Invalid service name", Severity.MEDIUM
            return True, None, Severity.MEDIUM
        
        elif command_type == CommandType.CONNECT_INTEGRATION:
            if 'service' not in params:
                return False, "Missing service parameter", Severity.HIGH
            return True, None, Severity.HIGH
        
        return True, None, Severity.LOW

# --- CLIENT CLASSES ---
class GoogleDocClient:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
    
    def read_commands(self) -> List[str]:
        # Simulate reading commands from Google Doc
        # In production, this would use the Google Docs API
        sample_commands = [
            "SCAN_SITE domain=example.com",
            "CHECK_INTEGRATION_STATUS service=meta_lead_ads",
            "# This is a comment",
            "START_CAMPAIGN campaign_id=summer2024",
        ]
        
        logger.info(f"Read {len(sample_commands)} lines from Google Doc {self.doc_id}")
        return sample_commands

class NotionClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.notion.com/v1"
    
    def log_action(self, command: ParsedCommand, result: Dict) -> bool:
        # Simulate logging to Notion
        logger.info(f"Logged action to Notion: {command.command_type} -> {result.get('status', 'unknown')}")
        return True

class MCPClient:
    def __init__(self, base_url: str, private_key: str):
        self.base_url = base_url
        self.private_key = private_key.encode() if isinstance(private_key, str) else private_key
    
    def _sign_payload(self, payload: Dict) -> str:
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(self.private_key, payload_str.encode(), hashlib.sha256)
        return signature.hexdigest()
    
    def execute_command(self, command: ParsedCommand) -> Dict:
        if not command.valid or not command.command_type:
            return {
                "status": "FAILED",
                "error": command.error_message or "Invalid command"
            }
        
        payload = {
            "action_id": f"{command.line_number}_{int(time.time())}",
            "command_type": command.command_type.value,
            "params": command.params,
            "severity": command.severity.value
        }
        
        signature = self._sign_payload(payload)
        headers = {
            "Content-Type": "application/json",
            "X-Signature": signature
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/actions",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"MCP request failed: {response.status_code} {response.text}")
                return {
                    "status": "FAILED",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP request error: {e}")
            return {
                "status": "FAILED",
                "error": str(e)
            }

# --- MAIN COMMAND POLLER ---
class CommandPoller:
    def __init__(self):
        self.doc_client = GoogleDocClient(GOOGLE_DOC_ID) if GOOGLE_DOC_ID else None
        self.notion_client = NotionClient(NOTION_TOKEN) if NOTION_TOKEN else None
        self.mcp_client = MCPClient(MCP_BASE_URL, PRIVATE_KEY)
        self.parser = CommandParser()
        self.processed_lines = set()
    
    def poll_once(self):
        """Single polling iteration with distributed lock to ensure only one
        replica processes commands at a time."""
        
        if redis_client:
            lock_key = "command-poller-lock"
            # Try to acquire the lock, with a 30-second timeout
            lock_acquired = redis_client.set(lock_key, "running", nx=True, ex=30)
            
            if not lock_acquired:
                logger.info("Another poller instance holds the lock. Skipping this cycle.")
                return
            
            logger.info("Lock acquired. Starting poll cycle...")
        
        try:
            if not self.doc_client:
                logger.warning("Google Doc client not configured. Using demo commands.")
                lines = [
                    "SCAN_SITE domain=example.com",
                    "CHECK_INTEGRATION_STATUS service=meta_lead_ads"
                ]
            else:
                lines = self.doc_client.read_commands()
            
            for line_num, line in enumerate(lines, start=1):
                if line_num in self.processed_lines:
                    continue
                
                command = self.parser.parse_line(line_num, line)
                
                if not command.valid:
                    if command.error_message != "Empty or comment line":
                        logger.warning(f"Invalid command on line {line_num}: {command.error_message}")
                    self.processed_lines.add(line_num)
                    continue
                
                logger.info(f"Processing command: {command.command_type} with params {command.params}")
                
                # Execute command via MCP
                result = self.mcp_client.execute_command(command)
                
                # Log to Notion if available
                if self.notion_client:
                    self.notion_client.log_action(command, result)
                
                logger.info(f"Command result: {result.get('status', 'unknown')} - {result.get('rationale', '')}")
                
                self.processed_lines.add(line_num)
        
        finally:
            # Always release the lock
            if redis_client:
                logger.info("Releasing poller lock.")
                redis_client.delete("command-poller-lock")
    
    def run(self):
        logger.info("Starting Command Poller in HA mode...")
        
        while True:
            try:
                self.poll_once()
                time.sleep(30)  # Poll every 30 seconds
            except KeyboardInterrupt:
                logger.info("Shutting down command poller...")
                break
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                time.sleep(60)  # Wait longer on errors

if __name__ == '__main__':
    poller = CommandPoller()
    poller.run()