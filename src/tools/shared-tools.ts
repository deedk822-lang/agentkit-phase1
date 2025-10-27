import { createTool } from '@inngest/agent-kit';
import { z } from 'zod';

export const finalizeResponseTool = createTool({
  name: 'finalize_response',
  description: 'Combine all agent responses and mark the task as complete',
  parameters: z.object({
    summary: z.string().describe('Summary of all agent contributions'),
    recommendations: z.array(z.string()).describe('Key recommendations'),
  }),
  handler: async ({ summary, recommendations }, { network }) => {
    if (!network?.state.kv) return 'No network state available';
    
    network.state.kv.set('final_summary', summary);
    network.state.kv.set('recommendations', recommendations);
    network.state.kv.set('task_completed', true);
    
    return 'Response finalized successfully';
  },
});

export const analyzeContextTool = createTool({
  name: 'analyze_context',
  description: 'Analyze the current network state and provide context',
  parameters: z.object({
    context_type: z.enum(['initial', 'progress', 'final']).describe('Type of context analysis'),
  }),
  handler: async ({ context_type }, { network }) => {
    if (!network?.state.kv) return 'No network state available';
    
    const hasDbAnswer = network.state.kv.has('dba_answer');
    const hasSecurityAnswer = network.state.kv.has('security_answer');
    
    const context = {
      type: context_type,
      dba_completed: hasDbAnswer,
      security_completed: hasSecurityAnswer,
      timestamp: new Date().toISOString(),
    };
    
    network.state.kv.set(`context_${context_type}`, JSON.stringify(context));
    
    return `Context analysis completed: ${JSON.stringify(context)}`;
  },
});