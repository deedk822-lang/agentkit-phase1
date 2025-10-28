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

# Test configuration
MCP_BASE_URL = os.getenv('MCP_BASE_URL', 'http://localhost:8080')
PRIVATE_KEY = os.getenv('MCP_PRIVATE_KEY', 'dev-key-change-in-prod').encode()

@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None

class IntegrationTestSuite:
    """Tests for integration management capabilities."""

    def __init__(self):
        self.results: List[TestResult] = []
        self.session = requests.Session()

    def sign_payload(self, payload: Dict) -> str:
        """Signs a payload for MCP requests."""
        payload['timestamp'] = datetime.utcnow().isoformat()
        message = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.new(PRIVATE_KEY, message, hashlib.sha256).hexdigest()
        return signature

    def run_test(self, test_name: str, test_func):
        """Runs a single test and records the result."""
        print(f"\\n\\U0001f9ea Running: {test_name}")
        start_time = time.time()
        try:
            test_func()
            duration = (time.time() - start_time) * 1000
            self.results.append(TestResult(test_name, True, duration))
            print(f"\\u2705 PASSED ({duration:.2f}ms)")
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.results.append(TestResult(test_name, False, duration, str(e)))
            print(f"\\u274c FAILED: {e}")
            raise

    # ========================================================================
    # INTEGRATION MANAGEMENT TESTS
    # ========================================================================

    def test_check_integration_status_allowed(self):
        """Tests that CHECK_INTEGRATION_STATUS is a low-risk, allowed action."""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'CHECK_INTEGRATION_STATUS',
            'params': {'service': 'mailchimp'},
            'severity': 'LOW'
        }

        signature = self.sign_payload(payload.copy())

        response = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload,
            headers={'X-Signature': signature},
            timeout=10
        )

        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert data['status'] == 'SUCCESS', f"Action should have succeeded but got status: {data['status']}"
        assert data['tool_result']['integration_status'] == 'CONNECTED'

    def test_refresh_token_needs_approval(self):
        """Tests that REFRESH_TOKEN is a medium-risk action requiring judge approval."""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'REFRESH_TOKEN',
            'params': {'service': 'google'},
            'severity': 'MEDIUM'  # Severity is key here
        }

        signature = self.sign_payload(payload.copy())

        response = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload,
            headers={'X-Signature': signature},
            timeout=25  # Judges can be slow
        )

        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()

        # If a Mistral API key is present, we expect judge decisions
        if os.getenv('MISTRAL_API_KEY'):
            assert 'judge_decisions' in data, "Judge decisions should be present when MISTRAL_API_KEY is set"
            assert data['status'] in ['SUCCESS', 'NEEDS_APPROVAL'], f"Expected SUCCESS or NEEDS_APPROVAL, got: {data['status']}"
        else:
            # If no key, the action should succeed without judges
            assert data['status'] == 'SUCCESS', f"Expected SUCCESS when no judge is configured, got: {data['status']}"

    def test_connect_integration_is_blocked(self):
        """Tests that CONNECT_INTEGRATION is a high-risk action that is blocked by policy."""
        action_id = str(uuid.uuid4())
        payload = {
            'action_id': action_id,
            'command_type': 'CONNECT_INTEGRATION',
            'params': {'service': 'salesforce'},
            'severity': 'HIGH'
        }

        signature = self.sign_payload(payload.copy())

        response = self.session.post(
            f"{MCP_BASE_URL}/v1/actions",
            json=payload,
            headers={'X-Signature': signature},
            timeout=10
        )

        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        assert data['status'] == 'BLOCKED', f"Action should have been blocked but got status: {data['status']}"
        assert 'policy: New integrations require manual' in data['rationale'], "Rationale should explain the policy block"

def run_integration_tests():
    suite = IntegrationTestSuite()

    # Run integration management tests
    suite.run_test("Check Integration Status (Allowed)", suite.test_check_integration_status_allowed)
    suite.run_test("Refresh Token (Needs Approval)", suite.test_refresh_token_needs_approval)
    suite.run_test("Connect Integration (Blocked)", suite.test_connect_integration_is_blocked)

    print("\\n" + "="*50)
    print("Integration Management Test Summary")
    print("="*50)

    passed_tests = [r for r in suite.results if r.passed]
    failed_tests = [r for r in suite.results if not r.passed]

    print(f"Total Tests: {len(suite.results)}")
    print(f"Passed: {len(passed_tests)}")
    print(f"Failed: {len(failed_tests)}")

    if failed_tests:
        print("\\nFailed Tests:")
        for result in failed_tests:
            print(f"- {result.name}: {result.error}")

    return len(failed_tests) == 0

if __name__ == "__main__":
    if not run_integration_tests():
        sys.exit(1)
