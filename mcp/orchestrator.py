#!/usr/bin/env python3
import os
import json
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from flask import Flask, request, jsonify
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('mcp_orchestrator')
app = Flask(__name__)

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
PRIVATE_KEY = get_secret("MCP_PRIVATE_KEY").encode() if get_secret("MCP_PRIVATE_KEY") else os.getenv('MCP_PRIVATE_KEY', 'dev-key-change-in-prod').encode()
GROQ_API_KEY = get_secret("GROQ_API_KEY") or os.getenv('GROQ_API_KEY')
MISTRAL_API_KEY = get_secret("MISTRAL_API_KEY") or os.getenv('MISTRAL_API_KEY')
APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')

# --- ENHANCED ENUMS AND DATA MODELS ---
class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class ActionResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"

class CommandType(str, Enum):
    SCAN_SITE = "SCAN_SITE"
    PUBLISH_REPORT = "PUBLISH_REPORT"
    START_CAMPAIGN = "START_CAMPAIGN"
    CHECK_INTEGRATION_STATUS = "CHECK_INTEGRATION_STATUS"
    REFRESH_TOKEN = "REFRESH_TOKEN"
    CONNECT_INTEGRATION = "CONNECT_INTEGRATION"

@dataclass
class ValidationResult:
    risk_score: float
    short_summary: str
    compressed_proof: str
    passed: bool

@dataclass
class JudgeDecision:
    judge_id: str
    score: float
    rationale: str
    approved: bool

# --- GROQ VALIDATOR ---
class GroqValidator:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
    
    def validate_command(self, command_type: str, params: Dict) -> ValidationResult:
        if not self.api_key:
            return ValidationResult(0.5, "No API key", "Skipped validation", True)
        
        prompt = f"""Analyze this command for security risks:
Type: {command_type}
Params: {json.dumps(params)}

Respond with JSON: {{"risk_score": 0.0-1.0, "summary": "brief summary", "proof": "evidence", "safe": true/false}}"""
        
        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                try:
                    data = json.loads(content)
                    return ValidationResult(
                        risk_score=data.get("risk_score", 0.5),
                        short_summary=data.get("summary", "Groq validation complete"),
                        compressed_proof=data.get("proof", "AI analysis"),
                        passed=data.get("safe", True)
                    )
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.error(f"Groq validation error: {e}")
        
        return ValidationResult(0.3, "Validation error", "Failed to validate", True)

# --- MISTRAL JUDGE ---
class MistralJudge:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.mistral.ai/v1/chat/completions"
    
    def judge_action(self, command_type: str, params: Dict, validation: ValidationResult) -> List[JudgeDecision]:
        if not self.api_key:
            return [JudgeDecision("fallback", 0.7, "No API key available", True)]
        
        judges = ["security", "compliance", "business"]
        decisions = []
        
        for judge_id in judges:
            prompt = f"""You are a {judge_id} expert. Evaluate this action:
Command: {command_type}
Params: {json.dumps(params)}
Risk Assessment: {validation.short_summary} (score: {validation.risk_score})

Respond with JSON: {{"score": 0.0-1.0, "rationale": "reasoning", "approved": true/false}}"""
            
            try:
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "mistral-small-latest",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    try:
                        data = json.loads(content)
                        decisions.append(JudgeDecision(
                            judge_id=judge_id,
                            score=data.get("score", 0.5),
                            rationale=data.get("rationale", "Analysis complete"),
                            approved=data.get("approved", True)
                        ))
                        continue
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.error(f"Mistral judge {judge_id} error: {e}")
            
            # Fallback decision
            decisions.append(JudgeDecision(judge_id, 0.5, "Judge unavailable", True))
        
        return decisions

# --- TOOL EXECUTOR ---
class ToolExecutor:
    def _call_apps_script(self, action: str, params: Dict) -> Dict:
        if not APPS_SCRIPT_URL:
            return {"status": "simulated", "message": "Apps Script URL not configured"}

        payload = {"action": action, **params}
        try:
            response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Apps Script call failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def execute_scan_site(self, domain: str) -> Dict:
        return {"domain": domain, "grade": "A", "status": "simulated"}
    
    def execute_start_campaign(self, channel: str, campaign_id: str) -> Dict:
        logger.info(f"Initiating campaign {campaign_id} on {channel} via Apps Script...")
        return self._call_apps_script("meta_campaign", {"campaign_name": campaign_id})
    
    def execute_check_integration_status(self, service: str) -> Dict:
        logger.info(f"Checking status for integration: {service}")
        return self._call_apps_script("get_integration_status", {"service": service})
    
    def execute_refresh_token(self, service: str) -> Dict:
        logger.info(f"Refreshing token for service: {service}")
        return self._call_apps_script("refresh_token", {"service": service})
    
    def execute_connect_integration(self, service: str, requires_human: bool = True) -> Dict:
        logger.warning(f"Preparing to connect new service: {service}. This action requires human approval.")
        return {
            "service": service,
            "status": "PENDING_HUMAN_ACTION",
            "message": "Connection prepared. A human operator must complete the OAuth flow.",
            "next_steps_url": f"https://admin.mailchimp.com/integrations/add/{service}"
        }

# --- ACTION ORCHESTRATOR ---
class ActionOrchestrator:
    def __init__(self):
        self.validator = GroqValidator(GROQ_API_KEY) if GROQ_API_KEY else None
        self.judge = MistralJudge(MISTRAL_API_KEY) if MISTRAL_API_KEY else None
        self.executor = ToolExecutor()
        
        self.tool_map = {
            "SCAN_SITE": self.executor.execute_scan_site,
            "START_CAMPAIGN": self.executor.execute_start_campaign,
            "CHECK_INTEGRATION_STATUS": self.executor.execute_check_integration_status,
            "REFRESH_TOKEN": self.executor.execute_refresh_token,
            "CONNECT_INTEGRATION": self.executor.execute_connect_integration,
        }
    
    def _get_policies_for_command(self, command_type: str) -> Dict:
        default_policies = {
            "START_CAMPAIGN": {
                "max_spend": 10000,
                "allowed_channels": ["linkedin", "meta", "mailchimp"]
            },
            "CHECK_INTEGRATION_STATUS": {
                "description": "Low-risk read-only operation. Always allowed.",
                "allowed": True
            },
            "REFRESH_TOKEN": {
                "description": "Medium-risk state-changing operation. Requires judge approval.",
                "require_judge_approval": True,
                "max_frequency_per_hour": 5
            },
            "CONNECT_INTEGRATION": {
                "description": "High-risk operation creating new permissions. Must be blocked for human review.",
                "action": "BLOCK",
                "reason": "New integrations require manual security and permissions review."
            }
        }
        return default_policies.get(command_type, {})
    
    def execute_action(self, action_id: str, command_type: str, params: Dict, severity: Severity) -> Dict:
        result = {
            "action_id": action_id,
            "command_type": command_type,
            "status": ActionResult.FAILED.value,
            "rationale": "",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Step 1: Policy Pre-Check
        policy_rules = self._get_policies_for_command(command_type)
        if policy_rules.get("action") == "BLOCK":
            result["status"] = ActionResult.BLOCKED.value
            result["rationale"] = f"Action blocked by policy: {policy_rules.get('reason')}"
            logger.warning(f"Action {action_id} ({command_type}) was permanently blocked by policy.")
            return result
        
        # Step 2: Groq micro-validation
        validation = None
        if self.validator:
            validation = self.validator.validate_command(command_type, params)
            result["validation"] = {
                "risk_score": validation.risk_score,
                "summary": validation.short_summary,
                "passed": validation.passed
            }
            if not validation.passed:
                result["status"] = ActionResult.BLOCKED.value
                result["rationale"] = f"Failed validation: {validation.short_summary}"
                return result
        
        # Step 3: Judge evaluation for MEDIUM+ severity
        if severity in [Severity.MEDIUM, Severity.HIGH] and self.judge and validation:
            judge_decisions = self.judge.judge_action(command_type, params, validation)
            result["judge_decisions"] = [
                {
                    "judge_id": jd.judge_id,
                    "score": jd.score,
                    "rationale": jd.rationale,
                    "approved": jd.approved
                } for jd in judge_decisions
            ]
            
            # Require majority approval
            approved_count = sum(1 for jd in judge_decisions if jd.approved)
            if approved_count < len(judge_decisions) / 2:
                result["status"] = ActionResult.NEEDS_APPROVAL.value
                result["rationale"] = "Majority judge approval required"
                return result
        
        # Step 4: Execute tool
        try:
            tool_func = self.tool_map.get(command_type)
            if not tool_func:
                raise ValueError(f"Unknown command type: {command_type}")
            
            tool_result = tool_func(**params)
            result["tool_result"] = tool_result
            result["status"] = ActionResult.SUCCESS.value
            if not result.get("rationale"):
                result["rationale"] = "Action completed successfully"
        except Exception as e:
            logger.error(f"Tool execution failed for {action_id}: {e}", exc_info=True)
            result["status"] = ActionResult.FAILED.value
            result["rationale"] = f"Execution error: {str(e)}"
        
        return result

# Initialize orchestrator
orchestrator = ActionOrchestrator()

# --- FLASK ENDPOINTS ---
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "groq_validator": bool(GROQ_API_KEY),
            "mistral_judge": bool(MISTRAL_API_KEY),
            "apps_script": bool(APPS_SCRIPT_URL)
        }
    })

@app.route('/v1/actions', methods=['POST'])
def execute_action_endpoint():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON payload"}), 400
        
        # Basic validation
        required_fields = ['action_id', 'command_type', 'params']
        for field in required_fields:
            if field not in payload:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Signature verification (simplified for demo)
        signature = request.headers.get('X-Signature')
        if signature:
            # In production, implement proper HMAC verification
            logger.info(f"Signature verification: {signature[:20]}...")
        
        result = orchestrator.execute_action(
            action_id=payload['action_id'],
            command_type=payload['command_type'],
            params=payload['params'],
            severity=Severity(payload.get('severity', 'LOW'))
        )
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Action endpoint error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/v1/validate', methods=['POST'])
def validate_endpoint():
    try:
        payload = request.get_json()
        if not payload or 'command_type' not in payload or 'params' not in payload:
            return jsonify({"error": "Invalid payload"}), 400
        
        if not orchestrator.validator:
            return jsonify({"error": "Validator not configured"}), 500
        
        validation = orchestrator.validator.validate_command(
            payload['command_type'], payload['params']
        )
        
        return jsonify({
            "risk_score": validation.risk_score,
            "summary": validation.short_summary,
            "proof": validation.compressed_proof,
            "passed": validation.passed
        })
    
    except Exception as e:
        logger.error(f"Validate endpoint error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)