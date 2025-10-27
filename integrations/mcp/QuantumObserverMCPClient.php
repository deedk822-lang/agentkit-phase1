<?php
/**
 * Quantum Observer – MCP Client (PHP)
 * Production-ready client for Model Context Protocol (MCP) interoperability.
 * - Context-aware tool discovery and execution
 * - Hardened HTTP operations (timeouts, retries, JSON validation)
 * - Normalized threat assessment schema
 * - Natively compatible with your WP plugin and n8n workflows
 */

final class QuantumObserverMCPClient
{
    /** @var string */
    private $mcpServerUrl;
    /** @var string */
    private $mcpApiKey;
    /** @var array<string, array> */
    private $toolRegistry = [];
    /** @var object|null */
    private $contextManager;

    /**
     * @param string      $mcpServerUrl
     * @param string      $mcpApiKey
     * @param object|null $contextManager
     */
    public function __construct(string $mcpServerUrl, string $mcpApiKey, $contextManager = null)
    {
        $this->mcpServerUrl   = rtrim($mcpServerUrl, '/');
        $this->mcpApiKey      = $mcpApiKey;
        $this->contextManager = $contextManager;
    }

    /**
     * Discover tools from the MCP server (optionally filtered).
     *
     * @param  string|null $threatType
     * @return array<int, array>
     * @throws RuntimeException
     */
    public function discoverTools(?string $threatType = null): array
    {
        $query   = $threatType ? ['threat_type' => $threatType] : [];
        $json    = $this->request('GET', '/tools', $query);
        $success = $json['success'] ?? false;
        if (!$success) {
            throw new RuntimeException('Failed to discover tools');
        }
        $tools = (array)($json['data'] ?? []);
        // Cache registry
        foreach ($tools as $tool) {
            if (!empty($tool['id'])) {
                $this->toolRegistry[$tool['id']] = $tool;
            }
        }
        return $tools;
    }

    /**
     * Execute a tool with rich threat context (auto-parameter mapping supported server-side).
     *
     * @param  string $toolId
     * @param  array  $threatContext
     * @return array<string, mixed>
     * @throws RuntimeException
     */
    public function executeTool(string $toolId, array $threatContext): array
    {
        $payload = [
            'threat_context' => $this->augmentContext($threatContext),
        ];
        $json    = $this->request('POST', "/tools/" . rawurlencode($toolId) . "/execute", $payload);
        if (!($json['success'] ?? false)) {
            $message = $json['message'] ?? 'Failed to execute tool';
            throw new RuntimeException($message);
        }
        return (array)($json['data'] ?? []);
    }

    /**
     * Normalize heterogeneous tool outputs to a standard threat assessment.
     *
     * @param  string               $toolId
     * @param  array<string, mixed> $raw
     * @return array<string, mixed>
     */
    public function normalizeToolOutput(string $toolId, array $raw): array
    {
        // Basic, safe mapping with sensible defaults
        $level       = (int)($raw['threat_level'] ?? $raw['severity'] ?? 0);
        $confidence  = (float)($raw['confidence'] ?? $raw['score'] ?? 0.0);
        $description = (string)($raw['description'] ?? $raw['message'] ?? '');
        $source      = $this->toolRegistry[$toolId]['name'] ?? $toolId;

        return [
            'source'       => $source,
            'threat_level' => max(0, min(10, $level)),
            'confidence'   => max(0.0, min(1.0, $confidence)),
            'description'  => $description,
            'timestamp'    => gmdate('c'),
        ];
    }

    /**
     * Low-level HTTP JSON request with retries and timeouts.
     *
     * @param  'GET'|'POST' $method
     * @param  string       $path
     * @param  array        $params
     * @return array<string, mixed>
     * @throws RuntimeException
     */
    private function request(string $method, string $path, array $params = []): array
    {
        $url = $this->mcpServerUrl . $path;
        $ch  = curl_init();

        if ($method === 'GET' && !empty($params)) {
            $url .= (strpos($url, '?') === false ? '?' : '&') . http_build_query($params);
        }

        $headers = [
            'Accept: application/json',
            'Authorization: Bearer ' . $this->mcpApiKey,
            'User-Agent: QuantumObserver-MCP/1.0',
        ];

        curl_setopt_array($ch, [
            CURLOPT_URL            => $url,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 5,
            CURLOPT_CONNECTTIMEOUT => 2,
            CURLOPT_HTTPHEADER     => $headers,
        ]);

        if ($method === 'POST') {
            $headers[] = 'Content-Type: application/json';
            curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($params, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
        }

        // Basic retry loop (3 attempts)
        $attempts = 0;
        $body     = false;
        do {
            $attempts++;
            $body = curl_exec($ch);
            $errno = curl_errno($ch);
            if ($errno === 0 && $body !== false) {
                break;
            }
            usleep(150000); // 150ms backoff
        } while ($attempts < 3);

        if ($body === false) {
            $err = curl_error($ch);
            curl_close($ch);
            throw new RuntimeException('MCP request failed: ' . $err);
        }

        $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $json = json_decode($body, true);
        if (!is_array($json)) {
            throw new RuntimeException('Invalid MCP JSON response (status ' . $status . ')');
        }

        if ($status < 200 || $status >= 300) {
            $message = $json['message'] ?? ('HTTP ' . $status);
            throw new RuntimeException('MCP error: ' . $message);
        }

        return $json;
    }

    /**
     * Enrich the threat context with session/site metadata if a context manager exists.
     * @param  array $context
     * @return array
     */
    private function augmentContext(array $context): array
    {
        if ($this->contextManager && method_exists($this->contextManager, 'export')) {
            $context['session'] = (array)$this->contextManager->export();
        }
        $context['site'] = $context['site'] ?? [
            'url'        => (function_exists('get_site_url') ? get_site_url() : ''),
            'wp_version' => (function_exists('get_bloginfo') ? get_bloginfo('version') : ''),
        ];
        return $context;
    }
}
