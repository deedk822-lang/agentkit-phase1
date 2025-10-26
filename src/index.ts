import { createServer } from '@inngest/agent-kit/server';
import { config } from 'dotenv';
import { devOpsNetwork } from './networks/dev-ops-network.js';
import { dbaAgent } from './agents/database-agent.js';
import { securityAgent } from './agents/security-agent.js';

// Load environment variables
config();

// Validate required environment variables
if (!process.env.ANTHROPIC_API_KEY && !process.env.OPENAI_API_KEY) {
  console.error('❌ Error: Please set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env file');
  process.exit(1);
}

// Create the AgentKit server
const server = createServer({
  agents: [dbaAgent, securityAgent],
  networks: [devOpsNetwork],
});

const PORT = process.env.PORT || 3000;

// Start the server
server.listen(PORT, () => {
  console.log('\n🚀 AgentKit Phase 1 Server Started Successfully!');
  console.log('=' .repeat(50));
  console.log(`📡 Server running on: http://localhost:${PORT}`);
  console.log(`📊 Inngest endpoint: http://localhost:${PORT}/api/inngest`);
  console.log('\n🛠️  Development Commands:');
  console.log(`   npx inngest-cli@latest dev -u http://localhost:${PORT}/api/inngest`);
  console.log('\n🔧 Testing:');
  console.log('   Open: http://localhost:8288/functions');
  console.log('   Find: "DevOps Expert Network" function');
  console.log('\n📋 Available Agents:');
  console.log('   • Database Administrator (PostgreSQL expert)');
  console.log('   • Database Security Expert (Security & compliance)');
  console.log('\n✨ Ready to process queries!');
  console.log('=' .repeat(50));
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down AgentKit server...');
  console.log('👋 Thanks for using AgentKit Phase 1!');
  process.exit(0);
});

// Handle uncaught errors
process.on('unhandledRejection', (reason, promise) => {
  console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
});

process.on('uncaughtException', (error) => {
  console.error('❌ Uncaught Exception:', error);
  process.exit(1);
});