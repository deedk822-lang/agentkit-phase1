import { createAgent, anthropic, createTool } from '@inngest/agent-kit';
import { z } from 'zod';

export const securityAgent = createAgent({
  name: 'Database Security Expert',
  description: 'Provides expert guidance on PostgreSQL security, access control, and compliance',
  system: 
    'You are a PostgreSQL security expert. ' +
    'You only provide answers to questions related to PostgreSQL security topics such as ' +
    'encryption, access control, audit logging, and compliance best practices. ' +
    'Always call the save_security_answer tool when providing a response.',
  model: anthropic({
    model: 'claude-3-5-haiku-latest',
    defaultParameters: {
      max_tokens: 1000,
    },
  }),
  tools: [
    createTool({
      name: 'save_security_answer',
      description: 'Save the security answer to the state',
      parameters: z.object({
        answer: z.string().describe('The security-related answer'),
        risk_level: z.enum(['low', 'medium', 'high']).describe('Security risk level'),
        compliance_notes: z.string().optional().describe('Compliance considerations'),
      }),
      handler: async ({ answer, risk_level, compliance_notes }, { network }) => {
        if (!network?.state.kv) return 'No network state available';
        
        network.state.kv.set('security_answer', answer);
        network.state.kv.set('risk_level', risk_level);
        if (compliance_notes) {
          network.state.kv.set('compliance_notes', compliance_notes);
        }
        
        return `Security answer saved with risk level: ${risk_level}`;
      },
    }),
  ],
});