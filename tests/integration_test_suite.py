import os
import sys
import time
import json
import uuid
import hashlib
import hmac
import requests
from datetime import datetime
from typing import Dict, List, Optional
import pytest
from dataclasses import dataclass

# --- Test Suite Content from Agentkitpazz1.txt (Lines 257-500) ---

# Test configuration
# We will use the default values for the test, as the services will run on localhost
MCP_BASE_URL = os.getenv('MCP_BASE_URL', 'http://localhost:8080')
WP_BASE_URL = os.getenv('WP_BASE_URL', 'http://localhost:8000')
# The MCP_PRIVATE_KEY is a mock key, but we need to ensure it matches the one used in mcp_api.py
PRIVATE_KEY = os.getenv('MCP_PRIVATE_KEY', 'test-key').encode()
NOTION_TOKEN = os.getenv('NOTION_TOKEN') # Not used in the tests, but included for completeness


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None


class IntegrationTestSuite:
    """Comprehensive integration tests"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.session = requests.Session()
    
    def sign_payload(self, payload: Dict) -> tuple[str, str]:
        """Sign payload for MCP requests"""
        nonce = str(uuid.uuid4())
        payload['nonce'] = nonce
        payload['timestamp'] = datetime.utcnow().isoformat()
        
        # Ensure payload is sorted for consistent signature generation
        message = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.new(PRIVATE_KEY, message, hashlib.sha256).hexdigest()
        
        return signature, nonce
    
    def run_test(self, test_name: str, test_func):
        """Run a single test and record result"""
        print(f"\n🧪 Running: {test_name}")
        start = time.time()
        
        try:
            test_func()
            duration_ms = (time.time() - start) * 1000
            self.results.append(TestResult(test_name, True, duration_ms))
            print(f"✅ PASSED ({duration_ms:.2f}ms)")
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(TestResult(test_name, False, duration_ms, str(e)))
            print(f"❌ FAILED: {e}")
            raise # Re-raise to stop the script if a critical test fails
    
    # ========================================================================
    # HEALTH CHECKS
    # ========================================================================
    
    def test_mcp_health(self):
        """Test MCP orchestrator health endpoint"""
        response = self.session.get(f"{MCP_BASE_URL}/health", timeout=5)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        
        data = response.json()
        assert data['status'] == 'healthy', f"Status not healthy: {data}"
        assert 'components' in data, "Missing components in health check"
    
    def test_wp_scan_endpoint(self):
        """Test WordPress live scan endpoint"""
        response = self.session.get(f"{WP_BASE_URL}/wp-json/qo/v1/scan", timeout=5)
        assert response.status_code == 200, f"Scan failed: {response.status_code}"
        
        data = response.json()
        assert 'grade' in data, "Missing grade in scan result"
        # The mock is designed to be fast, but we check the requirement from the test file
        assert data['response_time_ms'] < 200, f"Scan too slow: {data['response_time_ms']}ms"
    
    # ========================================================================
    # COMMAND VALIDATION
    # ========================================================================
    
    def test_scan_site_command(self):
        """Test SCAN_SITE command execution"""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'SCAN_SITE',
            'params': {'domain': 'example.com'},
            'severity': 'LOW'
        }
        
        signature, nonce = self.sign_payload(payload)
        
        response = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload,
            headers={
                'X-Signature': signature,
                'X-Nonce': nonce,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        assert response.status_code == 200, f"Action failed: {response.text}"
        
        data = response.json()
        assert data['action_id'] == action_id, "Action ID mismatch"
        assert data['status'] == 'SUCCESS', f"Action not successful: {data['status']}"
        assert 'tool_result' in data, "Missing tool result"
    
    def test_validation_only(self):
        """Test validation endpoint without execution"""
        payload = {
            'command_type': 'START_CAMPAIGN',
            'params': {
                'channel': 'linkedin',
                'campaign_id': 'test_123'
            }
        }
        
        response = self.session.post(
            f"{MCP_BASE_URL}/v1/validate",
            json=payload,
            timeout=5
        )
        
        assert response.status_code == 200, f"Validation failed: {response.text}"
        
        data = response.json()
        assert 'risk_score' in data, "Missing risk score"
        assert 'passed' in data, "Missing validation result"
        assert 0 <= data['risk_score'] <= 1, "Invalid risk score range"
    
    # ========================================================================
    # IDEMPOTENCY TESTS
    # ========================================================================
    
    def test_duplicate_action_handling(self):
        """Test that duplicate actions are handled correctly"""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'SCAN_SITE',
            'params': {'domain': 'duplicate-test.com'},
            'severity': 'LOW'
        }
        
        # We need a copy that will be used for the first request's signature
        payload_copy1 = payload.copy()
        signature1, nonce1 = self.sign_payload(payload_copy1)
        
        # First request
        response1 = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload_copy1,
            headers={
                'X-Signature': signature1,
                'X-Nonce': nonce1,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        assert response1.status_code == 200, "First request failed"
        
        # Wait a moment
        time.sleep(0.5)
        
        # Duplicate request with same action_id. We need a new nonce/timestamp for the second request
        # The test suite's original logic was slightly flawed here, as it re-signed the same payload object
        # which would update the nonce/timestamp. We must ensure the second request has a different signature.
        payload_dup = payload.copy()
        signature2, nonce2 = self.sign_payload(payload_dup) # This generates a new nonce/timestamp
        
        response2 = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload_dup,
            headers={
                'X-Signature': signature2,
                'X-Nonce': nonce2,
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        # Should succeed but indicate duplicate/cached
        assert response2.status_code == 200, "Duplicate request failed"
        # Check for the cached status we implemented
        data2 = response2.json()
        assert data2['status'] == 'SUCCESS_CACHED', f"Duplicate action did not return cached status: {data2['status']}"
    
    # ========================================================================
    # POLICY & JUDGE TESTS
    # ========================================================================
    
    def test_medium_severity_requires_judges(self):
        """Test that MEDIUM severity actions trigger judge evaluation"""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'PUBLISH_REPORT',
            'params': {
                'client': 'test_client',
                'dataset': 'test_data',
                'format': 'pdf'
            },
            'severity': 'MEDIUM'
        }
        
        signature, nonce = self.sign_payload(payload)
        
        response = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload,
            headers={
                'X-Signature': signature,
                'X-Nonce': nonce,
                'Content-Type': 'application/json'
            },
            timeout=30  # Judges take longer
        )
        
        assert response.status_code == 200, f"Action failed: {response.text}"
        
        data = response.json()
        assert 'judge_decisions' in data, "Missing judge decisions"
        assert len(data['judge_decisions']) >= 3, "Expected at least 3 judges"
        
        for decision in data['judge_decisions']:
            assert 'judge_id' in decision
            assert 'approved' in decision
            assert 'rationale' in decision

def run_all_tests():
    suite = IntegrationTestSuite()
    
    # Health Checks
    suite.run_test("MCP Health Check", suite.test_mcp_health)
    suite.run_test("WordPress Scan Endpoint Check", suite.test_wp_scan_endpoint)
    
    # Command Validation
    suite.run_test("SCAN_SITE Command Execution", suite.test_scan_site_command)
    suite.run_test("Validation Only Endpoint", suite.test_validation_only)
    
    # Idempotency
    suite.run_test("Duplicate Action Handling", suite.test_duplicate_action_handling)
    
    # Policy & Judges
    suite.run_test("Medium Severity Judge Evaluation", suite.test_medium_severity_requires_judges)
    
    print("\n" + "="*50)
    print("Integration Test Summary")
    print("="*50)
    
    passed = [r for r in suite.results if r.passed]
    failed = [r for r in suite.results if not r.passed]
    
    print(f"Total Tests: {len(suite.results)}")
    print(f"Passed: {len(passed)}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print("\nFailed Tests:")
        for r in failed:
            print(f"- {r.name}: {r.error}")
            
    return len(failed) == 0

if __name__ == "__main__":
    if not run_all_tests():
        sys.exit(1)

