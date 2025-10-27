import { createAgent, anthropic, createTool } from '@inngest/agent-kit';
import { z } from 'zod';

export const dbaAgent = createAgent({
  name: 'Database Administrator',
  description: 'Provides expert support for managing PostgreSQL databases',
  system: 
    'You are a PostgreSQL expert database administrator. ' +
    'You only provide answers to questions related to PostgreSQL database schema, indexes, and extensions. ' +
    'Always call the save_answer tool when providing a response.',
  model: anthropic({
    model: 'claude-3-5-haiku-latest',
    defaultParameters: {
      max_tokens: 1000,
    },
  }),
  tools: [
    createTool({
      name: 'save_answer',
      description: 'Save the database administration answer to the state',
      parameters: z.object({
        answer: z.string().describe('The database administration answer'),
        category: z.string().describe('Category: schema, performance, or troubleshooting'),
      }),
      handler: async ({ answer, category }, { network }) => {
        if (!network?.state.kv) return 'No network state available';
        
        network.state.kv.set('dba_answer', answer);
        network.state.kv.set('dba_category', category);
        
        return `Database answer saved successfully in category: ${category}`;
      },
    }),
  ],
});