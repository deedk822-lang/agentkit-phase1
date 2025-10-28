#!/usr/bin/env python3
"""
Quantum Observer Command Poller
Autonomous agent that reads Google Docs, executes MCP commands, and writes receipts.
"""

import os
import sys
import time
import json
import hashlib
import hmac
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/poller.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class QuantumObserverPoller:
    def __init__(self):
        self.google_doc_id = os.getenv('GOOGLE_DOC_ID')
        self.mcp_server_url = os.getenv('MCP_SERVER_URL', 'https://qo.deedk822.com/mcp/v1')
        self.mcp_private_key = os.getenv('MCP_PRIVATE_KEY')
        self.notion_token = os.getenv('NOTION_TOKEN')
        self.action_ledger_db = os.getenv('NOTION_ACTION_LEDGER_DB')
        
        if not all([self.google_doc_id, self.mcp_private_key]):
            raise ValueError("Missing required environment variables")
        
        self.docs_service = self._init_google_docs()
        self.processed_commands = set()
        
        logger.info(f"Initialized Quantum Observer Poller")
        logger.info(f"Google Doc ID: {self.google_doc_id}")
        logger.info(f"MCP Server: {self.mcp_server_url}")
    
    def _init_google_docs(self):
        """Initialize Google Docs API service"""
        SCOPES = ['https://www.googleapis.com/auth/documents']
        
        creds = None
        # Load existing credentials
        if os.path.exists('/app/config/token.json'):
            creds = Credentials.from_authorized_user_file('/app/config/token.json', SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Use service account if available
                if os.path.exists('/app/config/service-account.json'):
                    from google.oauth2 import service_account
                    creds = service_account.Credentials.from_service_account_file(
                        '/app/config/service-account.json', scopes=SCOPES)
                else:
                    logger.warning("No credentials found. Manual setup required.")
                    return None
        
        return build('docs', 'v1', credentials=creds)
    
    def read_command_queue(self) -> List[str]:
        """Read commands from Google Doc"""
        try:
            if not self.docs_service:
                logger.warning("Google Docs service not initialized")
                return []
            
            # Get document content
            doc = self.docs_service.documents().get(documentId=self.google_doc_id).execute()
            
            # Extract text content
            content = ''
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for text_run in element['paragraph'].get('elements', []):
                        if 'textRun' in text_run:
                            content += text_run['textRun'].get('content', '')
            
            # Parse commands (one per line)
            lines = content.strip().split('\n')
            commands = []
            
            for line in lines:
                line = line.strip()
                if line and not line.startswith('RECEIPT:') and not line.startswith('#'):
                    # Check if already processed
                    command_hash = hashlib.md5(line.encode()).hexdigest()[:8]
                    if command_hash not in self.processed_commands:
                        commands.append(line)
            
            return commands
            
        except HttpError as error:
            logger.error(f"Google Docs API error: {error}")
            return []
        except Exception as error:
            logger.error(f"Error reading command queue: {error}")
            return []
    
    def parse_command(self, command_line: str) -> Optional[Dict[str, Any]]:
        """Parse command line into structured command"""
        try:
            parts = command_line.split()
            if len(parts) < 2:
                return None
            
            command_type = parts[0]
            params = {}
            
            # Parse key=value parameters
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    params[key] = value
            
            return {
                'type': command_type,
                'params': params,
                'raw': command_line,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as error:
            logger.error(f"Error parsing command '{command_line}': {error}")
            return None
    
    def execute_mcp_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command via MCP server"""
        try:
            # Map command types to MCP tools
            tool_mapping = {
                'SCAN_SITE': 'threat_scan',
                'PUBLISH_REPORT': 'report_publish',
                'START_CAMPAIGN': 'campaign_start',
                'UPLOAD_VIMEO': 'vimeo_upload',
                'UPDATE_NOTION': 'notion_kv'
            }
            
            tool_id = tool_mapping.get(command['type'])
            if not tool_id:
                return {
                    'success': False,
                    'error': f"Unknown command type: {command['type']}"
                }
            
            # Prepare MCP request
            mcp_url = f"{self.mcp_server_url}/tools/{tool_id}/execute"
            
            payload = {
                'threat_context': {
                    **command['params'],
                    'command_type': command['type'],
                    'timestamp': command['timestamp']
                }
            }
            
            # Execute via MCP
            response = requests.post(
                mcp_url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'QuantumObserver-Poller/1.0.0'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    'success': False,
                    'error': f"MCP server error: {response.status_code}",
                    'response': response.text[:500]
                }
                
        except Exception as error:
            logger.error(f"Error executing MCP command: {error}")
            return {
                'success': False,
                'error': str(error)
            }
    
    def write_receipt(self, command: str, result: Dict[str, Any]) -> bool:
        """Write execution receipt back to Google Doc"""
        try:
            if not self.docs_service:
                return False
            
            # Generate receipt
            command_hash = hashlib.md5(command.encode()).hexdigest()[:8]
            result_hash = hashlib.md5(json.dumps(result, sort_keys=True).encode()).hexdigest()[:8]
            
            # Create HMAC signature for integrity
            signature = hmac.new(
                self.mcp_private_key.encode(),
                f"{command_hash}:{result_hash}".encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            receipt = f"RECEIPT: {command_hash} -> {result_hash} [{signature}] @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            # Append receipt to document
            requests_body = [
                {
                    'insertText': {
                        'location': {'index': 1},
                        'text': receipt + '\n'
                    }
                }
            ]
            
            self.docs_service.documents().batchUpdate(
                documentId=self.google_doc_id,
                body={'requests': requests_body}
            ).execute()
            
            # Mark command as processed
            self.processed_commands.add(command_hash)
            
            # Log to Notion Action Ledger
            self.log_to_notion_ledger(command, result, receipt)
            
            return True
            
        except Exception as error:
            logger.error(f"Error writing receipt: {error}")
            return False
    
    def log_to_notion_ledger(self, command: str, result: Dict[str, Any], receipt: str):
        """Log action to Notion Action Ledger database"""
        try:
            if not self.notion_token or not self.action_ledger_db:
                return
            
            notion_url = f"https://api.notion.com/v1/pages"
            
            payload = {
                "parent": {"database_id": self.action_ledger_db},
                "properties": {
                    "Command": {"title": [{"text": {"content": command[:100]}}]},
                    "Status": {"select": {"name": "Success" if result.get('success') else "Failed"}},
                    "Execution_Time": {"number": result.get('execution_time_ms', 0)},
                    "Receipt": {"rich_text": [{"text": {"content": receipt}}]},
                    "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}}
                }
            }
            
            requests.post(
                notion_url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.notion_token}',
                    'Content-Type': 'application/json',
                    'Notion-Version': '2022-06-28'
                },
                timeout=10
            )
            
        except Exception as error:
            logger.error(f"Error logging to Notion: {error}")
    
    def run_cycle(self):
        """Run one polling cycle"""
        try:
            logger.info("Starting polling cycle")
            
            # Read commands from Google Doc
            commands = self.read_command_queue()
            logger.info(f"Found {len(commands)} commands to process")
            
            for command_line in commands:
                logger.info(f"Processing command: {command_line}")
                
                # Parse command
                command = self.parse_command(command_line)
                if not command:
                    logger.warning(f"Failed to parse command: {command_line}")
                    continue
                
                # Execute via MCP
                start_time = time.time()
                result = self.execute_mcp_command(command)
                execution_time = (time.time() - start_time) * 1000
                
                # Add execution metadata
                result['execution_time_ms'] = execution_time
                result['command'] = command
                
                logger.info(f"Command executed in {execution_time:.1f}ms, success: {result.get('success', False)}")
                
                # Write receipt
                if self.write_receipt(command_line, result):
                    logger.info(f"Receipt written for command: {command['type']}")
                else:
                    logger.error(f"Failed to write receipt for command: {command['type']}")
            
            logger.info("Polling cycle completed")
            
        except Exception as error:
            logger.error(f"Error in polling cycle: {error}")
    
    def run_forever(self, interval: int = 5):
        """Run poller continuously"""
        logger.info(f"Starting continuous polling (interval: {interval}s)")
        
        while True:
            try:
                self.run_cycle()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Poller stopped by user")
                break
            except Exception as error:
                logger.error(f"Unexpected error: {error}")
                time.sleep(interval)

def main():
    """Main entry point"""
    try:
        poller = QuantumObserverPoller()
        
        # Run single cycle or continuous based on environment
        if os.getenv('RUN_ONCE', '').lower() == 'true':
            poller.run_cycle()
        else:
            interval = int(os.getenv('POLL_INTERVAL', '5'))
            poller.run_forever(interval)
            
    except Exception as error:
        logger.error(f"Failed to start poller: {error}")
        sys.exit(1)

if __name__ == '__main__':
    main()