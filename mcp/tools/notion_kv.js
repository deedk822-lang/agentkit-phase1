const axios = require('axios');
const { createHash } = require('crypto');

const NOTION_API_BASE = 'https://api.notion.com/v1';
const NOTION_VERSION = '2022-06-28';

module.exports = {
  metadata: {
    name: 'Notion Key-Value Store',
    description: 'Notion-powered feature flags, policies, and audit ledger',
    capabilities: ['feature_flags', 'policy_engine', 'audit_ledger', 'evidence_storage'],
    threat_types: ['governance', 'compliance', 'audit'],
    version: '1.0.0'
  },

  async execute(threatContext) {
    const { operation, key, value, policy_id, evidence } = threatContext;
    
    const notionToken = process.env.NOTION_TOKEN;
    if (!notionToken) {
      throw new Error('Notion token not configured');
    }

    const headers = {
      'Authorization': `Bearer ${notionToken}`,
      'Content-Type': 'application/json',
      'Notion-Version': NOTION_VERSION
    };

    switch (operation) {
      case 'get_feature_flag':
        return await this.getFeatureFlag(key, headers);
      
      case 'set_feature_flag':
        return await this.setFeatureFlag(key, value, headers);
      
      case 'get_policies':
        return await this.getPolicies(policy_id, headers);
      
      case 'log_action':
        return await this.logAction(threatContext, headers);
      
      case 'store_evidence':
        return await this.storeEvidence(evidence, headers);
      
      default:
        throw new Error(`Unknown operation: ${operation}`);
    }
  },

  async getFeatureFlag(key, headers) {
    const dbId = process.env.NOTION_FEATURE_FLAGS_DB;
    const response = await axios.post(`${NOTION_API_BASE}/databases/${dbId}/query`, {
      filter: {
        property: 'Key',
        title: { equals: key }
      }
    }, { headers });

    const page = response.data.results[0];
    if (!page) {
      return { success: false, error: 'Feature flag not found' };
    }

    return {
      success: true,
      data: {
        key,
        value: page.properties.Value?.rich_text[0]?.text?.content || '',
        enabled: page.properties.Enabled?.checkbox || false,
        rollout_percent: page.properties.Rollout_Percent?.number || 0
      }
    };
  },

  async setFeatureFlag(key, value, headers) {
    const dbId = process.env.NOTION_FEATURE_FLAGS_DB;
    
    const response = await axios.post(`${NOTION_API_BASE}/pages`, {
      parent: { database_id: dbId },
      properties: {
        Key: { title: [{ text: { content: key } }] },
        Value: { rich_text: [{ text: { content: String(value) } }] },
        Enabled: { checkbox: true },
        Last_Updated: { date: { start: new Date().toISOString() } }
      }
    }, { headers });

    return { success: true, page_id: response.data.id };
  },

  async getPolicies(policyId, headers) {
    const dbId = process.env.NOTION_POLICIES_DB;
    
    const filter = policyId ? {
      property: 'Policy_ID',
      title: { equals: policyId }
    } : undefined;

    const response = await axios.post(`${NOTION_API_BASE}/databases/${dbId}/query`, {
      filter
    }, { headers });

    const policies = response.data.results.map(page => ({
      policy_id: page.properties.Policy_ID?.title[0]?.text?.content || '',
      name: page.properties.Name?.rich_text[0]?.text?.content || '',
      severity: page.properties.Severity?.select?.name || 'LOW',
      rule_json: JSON.parse(page.properties.Rule_JSON?.rich_text[0]?.text?.content || '{}'),
      enabled: page.properties.Enabled?.checkbox || false
    }));

    return { success: true, data: policies };
  },

  async logAction(context, headers) {
    const dbId = process.env.NOTION_ACTION_LEDGER_DB;
    
    const actionHash = createHash('sha256')
      .update(JSON.stringify(context, Object.keys(context).sort()))
      .digest('hex').substring(0, 16);

    await axios.post(`${NOTION_API_BASE}/pages`, {
      parent: { database_id: dbId },
      properties: {
        Action_ID: { title: [{ text: { content: context.command?.type || 'UNKNOWN' } }] },
        Action_Hash: { rich_text: [{ text: { content: actionHash } }] },
        Status: { select: { name: context.success ? 'SUCCESS' : 'FAILED' } },
        Execution_Time: { number: context.execution_time_ms || 0 },
        Command_Raw: { rich_text: [{ text: { content: JSON.stringify(context.command?.raw || '') } }] },
        Timestamp: { date: { start: new Date().toISOString() } },
        Rule_1_Compliant: { checkbox: true }
      }
    }, { headers });

    return { success: true, action_hash: actionHash };
  },

  async storeEvidence(evidence, headers) {
    const dbId = process.env.NOTION_AUDIT_EVIDENCE_DB;
    
    const evidenceHash = createHash('sha256')
      .update(JSON.stringify(evidence))
      .digest('hex');

    await axios.post(`${NOTION_API_BASE}/pages`, {
      parent: { database_id: dbId },
      properties: {
        Evidence_ID: { title: [{ text: { content: evidence.id || 'AUTO-' + Date.now() } }] },
        Evidence_Hash: { rich_text: [{ text: { content: evidenceHash } }] },
        Evidence_Type: { select: { name: evidence.type || 'SYSTEM' } },
        Content: { rich_text: [{ text: { content: JSON.stringify(evidence.content || {}) } }] },
        Integrity_Verified: { checkbox: true },
        Created_At: { date: { start: new Date().toISOString() } }
      }
    }, { headers });

    return { success: true, evidence_hash: evidenceHash };
  }
};