# AgentKit Phase 1 Implementation

A foundational AI agent system built with AgentKit by Inngest, demonstrating multi-agent networks with deterministic routing.

## Features

- 🤖 **Multi-Agent System**: Database Administrator and Security Expert agents
- 🔀 **Deterministic Routing**: State-based agent orchestration
- 🛠️ **Tool Integration**: Shared state management and tool execution
- 🔍 **Development Tools**: Built-in tracing and debugging
- 📊 **Type Safety**: Full TypeScript implementation

## Quick Start

1. **Clone and Install**
   ```bash
   git clone https://github.com/deedk822-lang/agentkit-phase1.git
   cd agentkit-phase1
   npm install
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run Development Server**
   ```bash
   # Terminal 1: Start AgentKit server
   npm run dev
   
   # Terminal 2: Start Inngest dev server
   npm run inngest
   ```

4. **Test Your Agents**
   - Navigate to `http://localhost:8288/functions`
   - Find "DevOps Expert Network"
   - Test with sample queries

## Architecture

### Agent Network Flow
```
User Query → DBA Agent → Security Agent → Combined Response
     ↓            ↓            ↓              ↓
  Initial      Database     Security      Final State
   State      Assessment   Evaluation    with Results
```

### Project Structure
```
src/
├── agents/           # Individual agent implementations
├── networks/         # Multi-agent network configurations  
├── tools/           # Shared tools and utilities
└── index.ts         # Main application entry point
```

## Usage Examples

### Sample Query
```json
{
  "data": {
    "input": "I'm building a financial application that needs to handle millions of transactions. How should I design my PostgreSQL database schema for optimal performance, and what security measures should I implement?"
  }
}
```

### Expected Agent Flow
1. **DBA Agent** analyzes performance requirements and suggests schema optimizations
2. **Security Agent** evaluates security risks and compliance requirements
3. **Network State** combines both perspectives for comprehensive guidance

## Development

- **Build**: `npm run build`
- **Test**: `npm run test`
- **Debug**: Use Inngest dev server UI at `http://localhost:8288`

## Next Steps

This Phase 1 implementation provides the foundation for:
- Advanced tool integrations
- Human-in-the-loop workflows  
- LLM-based routing patterns
- Production deployment

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details.