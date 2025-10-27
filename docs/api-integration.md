# API Integration Guide

## Groq Integration

### Setup
```javascript
const { Groq } = require('groq-sdk');
const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });
```

### Threat Detection
```javascript
const threatAnalysis = await groq.chat.completions.create({
  messages: [
    {
      role: 'system',
      content: 'You are a quantum security analyst. Analyze threats in <200ms.'
    },
    {
      role: 'user',
      content: `System logs: ${JSON.stringify(logs)}`
    }
  ],
  model: 'llama-3.3-70b-versatile',
  temperature: 0.1,
  max_tokens: 1000,
  response_format: { type: 'json_object' }
});
```

## Mistral Agents Integration

### Agent Creation
```javascript
const agentResponse = await axios.post('https://api.mistral.ai/v1/agents', {
  name: 'Security Remediation Agent',
  instructions: 'Generate security patches with Monte Carlo validation.',
  connectors: ['code_execution', 'web_search'],
  model: 'codestral-latest'
}, {
  headers: {
    'Authorization': `Bearer ${process.env.MISTRAL_API_KEY}`,
    'Content-Type': 'application/json'
  }
});
```

### Conversation Processing
```javascript
const conversation = await axios.post('https://api.mistral.ai/v1/conversations', {
  agent_id: agentId
});

const response = await axios.post('https://api.mistral.ai/v1/conversations/message', {
  conversation_id: conversation.data.id,
  role: 'user',
  content: 'Analyze this security threat and provide remediation'
});
```

## GitHub API Integration

### Issue Creation
```javascript
const { Octokit } = require('@octokit/rest');
const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

const issue = await octokit.rest.issues.create({
  owner: 'deedk822-lang',
  repo: 'agentkit-phase1',
  title: `🚨 Security Threat - Severity ${severity}`,
  body: threatDescription,
  labels: ['security', 'quantum-observer', 'auto-generated'],
  assignees: ['deedk822-lang']
});
```

### Webhook Triggers
```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/owner/repo/dispatches \
  -d '{"event_type": "security_threat", "client_payload": {"severity": 8}}'
```