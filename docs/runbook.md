# Runbook: Integration Management

This document outlines the procedures for managing third-party integrations via the MCP Orchestrator. These actions are designed to be initiated by an autonomous agent and are governed by a set of policies to ensure security and stability.

## 1. Overview of Integration Commands

The MCP Orchestrator supports three primary commands for managing integrations:

- `CHECK_INTEGRATION_STATUS`: A low-risk, read-only command to verify the status of a connected service.
- `REFRESH_TOKEN`: A medium-risk command that attempts to refresh an expired or expiring OAuth token. This action is subject to judge approval.
- `CONNECT_INTEGRATION`: A high-risk command to initiate a new integration. This action is always blocked by policy and requires manual human intervention.

---

## 2. Standard Operating Procedures (SOPs)

### SOP-INT-01: Checking Integration Status

**Objective:** To safely verify the connectivity and status of a third-party service (e.g., Mailchimp, Meta).

**Command:**
```json
{
  "action_id": "status-check-mailchimp-123",
  "command_type": "CHECK_INTEGRATION_STATUS",
  "params": {
    "service": "mailchimp"
  },
  "severity": "LOW"
}
```

**Execution Flow:**
1. The agent dispatches the `CHECK_INTEGRATION_STATUS` command.
2. The MCP Orchestrator validates the command. Since this is a low-risk, read-only action, it bypasses judge evaluation.
3. The orchestrator calls the Apps Script bridge, which queries the target service's API.
4. The bridge returns the connection status.

**Expected Outcome:**
- **Status:** `SUCCESS`
- **Tool Result:**
  ```json
  {
    "status": "success",
    "integration_status": "CONNECTED",
    "last_checked": "..."
  }
  ```
- **Alerts:** None. This is a silent, routine check.

### SOP-INT-02: Refreshing an Access Token

**Objective:** To refresh an OAuth 2.0 access token for a service to restore API connectivity.

**Command:**
```json
{
  "action_id": "token-refresh-google-456",
  "command_type": "REFRESH_TOKEN",
  "params": {
    "service": "google"
  },
  "severity": "MEDIUM"
}
```

**Execution Flow:**
1. The agent identifies a failing API call and dispatches the `REFRESH_TOKEN` command.
2. The orchestrator validates the command. Due to its `MEDIUM` severity, it is sent for judge evaluation.
3. A panel of AI judges (e.g., security, compliance, business) reviews the request.
4. If a majority of judges approve, the orchestrator proceeds. Otherwise, the action status is set to `NEEDS_APPROVAL` and a human is alerted.
5. The orchestrator calls the Apps Script bridge, which executes the token refresh flow with the service.

**Expected Outcome:**
- **Status:** `SUCCESS` (if approved) or `NEEDS_APPROVAL` (if rejected).
- **Tool Result (on success):**
  ```json
  {
    "status": "success",
    "message": "Token for google refreshed successfully.",
    "new_token_expires_in": 3600
  }
  ```
- **Alerts:** A notification should be sent to the operations team channel if the judges do not approve the action.

### SOP-INT-03: Handling a New Integration Request

**Objective:** To safely handle a request from the agent to connect a new third-party service.

**Command:**
```json
{
  "action_id": "connect-salesforce-789",
  "command_type": "CONNECT_INTEGRATION",
  "params": {
    "service": "salesforce"
  },
  "severity": "HIGH"
}
```

**Execution Flow:**
1. The agent determines that a new integration is required and dispatches the `CONNECT_INTEGRATION` command.
2. The orchestrator's policy engine immediately intercepts the command.
3. The action is permanently blocked because the policy for `CONNECT_INTEGRATION` is set to `BLOCK`.

**Expected Outcome:**
- **Status:** `BLOCKED`
- **Rationale:** "Action blocked by policy: New integrations require manual security and permissions review."
- **Alerts:** A high-priority alert must be sent to the security and engineering teams. The alert should include the service requested and the agent that initiated the request.

---

## 3. Emergency Procedures

### Emergency-INT-E01: Unauthorized Token Refresh

- **Symptom:** Logs show repeated, unapproved `REFRESH_TOKEN` attempts.
- **Action:**
  1. Immediately place the `command-poller` service into a paused state.
  2. Manually revoke the potentially compromised credentials from the third-party service's admin panel.
  3. Investigate the agent's decision-making logs to identify the root cause of the spurious requests.
  4. Escalate to the security team for a full audit.

### Emergency-INT-E02: Policy Bypass for New Integration

- **Symptom:** A new integration appears connected without following the manual approval process. This indicates a severe failure in the policy enforcement layer.
- **Action:**
  1. **System Halt:** Trigger the master shut-off switch for the MCP Orchestrator to prevent any further actions.
  2. **Disconnect:** Manually disconnect the unauthorized integration from the third-party service.
  3. **Audit:** Review orchestrator logs, deployment history, and policy files to understand how the block was bypassed. This is a critical security incident.
  4. **Post-Mortem:** A full post-mortem is required before bringing the system back online.
