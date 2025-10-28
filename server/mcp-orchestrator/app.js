import express from 'express';
import cors from 'cors';
import rateLimit from 'express-rate-limit';
import helmet from 'helmet';
import compression from 'compression';
import { createHash, randomBytes } from 'crypto';

const app = express();
const PORT = process.env.PORT || 8080;

// Security middleware
app.use(helmet());
app.use(compression());
app.use(cors({
  origin: process.env.CORS_ORIGINS?.split(',') || ['https://qo.deedk822.com'],
  credentials: true
}));

// Rate limiting
const limiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 100, // limit each IP to 100 requests per windowMs
  message: { error: 'Rate limit exceeded' }
});
app.use(limiter);

// Body parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Request logging
app.use((req, res, next) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${req.method} ${req.path} - ${req.ip}`);
  next();
});

import threat_scan from '../../mcp/tools/threat_scan.js';
import report_publish from '../../mcp/tools/report_publish.js';
import campaign_start from '../../mcp/tools/campaign_start.js';
import vimeo_upload from '../../mcp/tools/vimeo_upload.js';
import notion_kv from '../../mcp/tools/notion_kv.js';

// Tool registry
const tools = {
  threat_scan,
  report_publish,
  campaign_start,
  vimeo_upload,
  notion_kv
};

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    tools_registered: Object.keys(tools),
    version: '1.0.0',
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    env: process.env.NODE_ENV || 'development',
    components: {
      "validator": "ok",
      "judge": "ok"
    }
  });
});

// Tool discovery
app.get('/mcp/v1/tools', (req, res) => {
  const { threat_type } = req.query;
  
  const toolList = Object.keys(tools).map(id => ({
    id,
    name: tools[id].metadata?.name || id,
    description: tools[id].metadata?.description || '',
    capabilities: tools[id].metadata?.capabilities || [],
    threat_types: tools[id].metadata?.threat_types || ['general']
  })).filter(tool => 
    !threat_type || tool.threat_types.includes(threat_type)
  );
  
  res.json({
    success: true,
    data: toolList,
    count: toolList.length
  });
});

// Tool execution
app.post('/mcp/v1/tools/:toolId/execute', async (req, res) => {
  const { toolId } = req.params;
  const { threat_context } = req.body;
  
  if (!tools[toolId]) {
    return res.status(404).json({
      success: false,
      message: `Tool ${toolId} not found`
    });
  }
  
  try {
    const startTime = Date.now();
    const result = await tools[toolId].execute(threat_context || {});
    const latency = Date.now() - startTime;
    
    res.json({
      success: true,
      tool_result: result,
      execution_time_ms: latency,
      tool_id: toolId,
      action_id: threat_context.action_id,
      status: 'SUCCESS',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error(`Tool ${toolId} execution failed:`, error);
    res.status(500).json({
      success: false,
      message: error.message,
      tool_id: toolId
    });
  }
});

// Validation endpoint
app.post('/mcp/v1/validate', async (req, res) => {
  const { command_type, params } = req.body;
  
  try {
    // Load policies from Notion
    const policies = await tools.notion_kv.execute({
      operation: 'get_policies',
      command_type
    });
    
    // Validate against policies
    const validation = validateCommand(command_type, params, policies.data);
    
    res.json({
      success: true,
      valid: validation.valid,
      confidence: validation.confidence,
      violations: validation.violations,
      approved_actions: validation.approved_actions
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      message: error.message
    });
  }
});

function validateCommand(command_type, params, policies) {
  const violations = [];
  let confidence = 1.0;
  
  // Basic validation logic
  if (command_type === 'START_CAMPAIGN' && params.spend > 5000) {
    violations.push('Spend exceeds policy limit');
    confidence *= 0.3;
  }
  
  if (command_type === 'PUBLISH_REPORT' && !['pdf', 'html'].includes(params.format)) {
    violations.push('Invalid report format');
    confidence *= 0.5;
  }
  
  return {
    valid: violations.length === 0,
    confidence,
    violations,
    approved_actions: violations.length === 0 ? ['PROCEED'] : ['REQUEST_APPROVAL']
  };
}

// Error handling
app.use((error, req, res, next) => {
  console.error('Unhandled error:', error);
  res.status(500).json({
    success: false,
    message: 'Internal server error',
    timestamp: new Date().toISOString()
  });
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('Received SIGTERM, shutting down gracefully');
  server.close(() => {
    console.log('Process terminated');
    process.exit(0);
  });
});

const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Quantum Observer MCP Server running on port ${PORT}`);
  console.log(`📊 Health check: http://localhost:${PORT}/health`);
  console.log(`🔧 Tools endpoint: http://localhost:${PORT}/mcp/v1/tools`);
});

export default app;