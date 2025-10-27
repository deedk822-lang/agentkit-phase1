import { createNetwork } from '@inngest/agent-kit';
import { dbaAgent } from '../agents/database-agent.js';
import { securityAgent } from '../agents/security-agent.js';

export interface NetworkState {
  dba_answer?: string;
  dba_category?: string;
  security_answer?: string;
  risk_level?: 'low' | 'medium' | 'high';
  compliance_notes?: string;
  final_summary?: string;
  recommendations?: string[];
  task_completed?: boolean;
  context_initial?: string;
  context_progress?: string;
  context_final?: string;
}

export const devOpsNetwork = createNetwork<NetworkState>({
  name: 'DevOps Expert Network',
  agents: [dbaAgent, securityAgent],
  router: ({ network }) => {
    const state = network?.state.kv;
    
    if (!state) {
      console.log('🚀 Starting with DBA Agent - no state available');
      return dbaAgent;
    }
    
    // Step 1: Get database administration input first
    if (!state.has('dba_answer')) {
      console.log('📊 Routing to DBA Agent - database analysis needed');
      return dbaAgent;
    }
    
    // Step 2: Get security assessment
    if (state.has('dba_answer') && !state.has('security_answer')) {
      console.log('🔒 Routing to Security Agent - security analysis needed');
      return securityAgent;
    }
    
    // Step 3: Task completed when both agents have responded
    if (state.has('dba_answer') && state.has('security_answer')) {
      console.log('✅ Network execution complete - both agents have responded');
      return undefined; // End the network execution
    }
    
    console.log('🔄 Fallback to DBA Agent');
    return dbaAgent; // Fallback
  },
});