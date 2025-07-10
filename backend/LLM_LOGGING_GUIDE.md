# LLM Communication Logging Guide

This guide explains the comprehensive logging system implemented for all LLM communications in the SRE AI Agent.

## Overview

The system now logs **all** LLM communications with detailed information including:
- Complete prompts and responses
- Timing information
- Error details
- Provider information
- Request/response metadata

## Log Files

### Primary Log Files
- `logs/llm_communications.log` - Dedicated LLM communication logs
- `logs/sre_agent.log` - General application logs including LLM activity
- `logs/mcp_communications.log` - MCP tool communications

### Log Rotation
- LLM communications log: 50MB max size, 10 backup files
- General logs: 10MB max size, 5 backup files
- Automatic rotation when size limits are reached

## LLM Clients and Logging

### 1. LLMManager/LLMClient (`app/integrations/llm/client.py`)

The original LLM client has comprehensive logging with:

**Request Logging:**
```
=== LLM REQUEST [openai] [ID: abc123] ===
Request ID: abc123
Provider: openai
Model: gpt-4-1106-preview
Temperature: 0.3
--- MESSAGES ---
Message 1 [SYSTEM]:
You are an expert SRE...
---
Message 2 [USER]:
Alert: HighMemoryUsage...
---
=== END REQUEST [ID: abc123] ===
```

**Response Logging:**
```
=== LLM RESPONSE [openai] [ID: abc123] ===
Request ID: abc123
Response length: 1250 characters
--- RESPONSE CONTENT ---
Based on the alert analysis...
=== END RESPONSE [ID: abc123] ===
```

**Error Logging:**
```
=== LLM ERROR [openai] [ID: abc123] ===
Request ID: abc123
Error: API rate limit exceeded
=== END ERROR [ID: abc123] ===
```

### 2. LangChainLLMClient (`app/integrations/llm/langchain_client.py`)

The newer LangChain client has enhanced logging with:

**Interaction Summary:**
```
LLM Communication - openai (analyze_alert): success in 2.340s
```

**Detailed Logging:**
```
LLM Interaction Data: {
  "timestamp": 1704067200.123,
  "provider": "openai",
  "method": "analyze_alert",
  "duration_seconds": 2.340,
  "prompt_length": 1500,
  "response_length": 1250,
  "status": "success"
}
```

**Request/Response Content:**
```
LLM Request to openai:
Alert Information:
Alert: HighMemoryUsage
Severity: warning
...

LLM Response from openai:
Based on the alert analysis, the high memory usage...
```

## Logging Levels

### DEBUG Level
- Full prompt and response content
- Detailed interaction metadata
- Request/response timing
- Tool parameter details

### INFO Level
- Interaction summaries
- Success/failure status
- Provider and method information
- Duration metrics

### ERROR Level
- Exception details
- API errors
- Configuration issues
- Fallback activations

## Monitoring LLM Communications

### Real-time Monitoring
```bash
# Watch LLM communications
tail -f logs/llm_communications.log

# Watch all application logs
tail -f logs/sre_agent.log

# Filter for specific provider
grep "openai" logs/llm_communications.log

# Filter for errors
grep "ERROR" logs/llm_communications.log
```

### Log Analysis Examples

**Find slow requests:**
```bash
grep "duration_seconds" logs/llm_communications.log | grep -E "[5-9]\.[0-9]+" | head -10
```

**Count requests by provider:**
```bash
grep "LLM Communication" logs/llm_communications.log | grep -o "openai\|gemini\|grok" | sort | uniq -c
```

**Find failed requests:**
```bash
grep "status.*error" logs/llm_communications.log
```

## Testing the Logging System

Use the provided test script to verify logging:

```bash
cd backend
python test_llm_logging.py
```

This will:
1. Test both LLM clients
2. Generate sample communications
3. Verify logging is working
4. Show log file locations

## Log Configuration

The logging configuration is in `app/utils/logger.py`:

```python
"llm_communications": {
    "class": "logging.handlers.RotatingFileHandler",
    "level": "DEBUG",
    "formatter": "detailed",
    "filename": "logs/llm_communications.log",
    "maxBytes": 52428800,  # 50MB
    "backupCount": 10,
},
```

## Privacy and Security

### Sensitive Information
- API keys are **never** logged
- Only prompt content and responses are logged
- Request IDs are used for correlation

### Log Security
- Ensure log files have appropriate permissions
- Consider log retention policies
- Monitor log file sizes and disk usage

## Troubleshooting

### Common Issues

**No logs appearing:**
- Check log level configuration
- Verify `logs/` directory exists
- Ensure proper permissions

**Missing LLM communications:**
- Verify LLM client initialization
- Check API key configuration
- Look for initialization errors

**Large log files:**
- Monitor log rotation settings
- Consider shorter retention periods
- Implement log archiving

### Debug Mode
Enable debug mode for maximum verbosity:

```python
setup_logging("DEBUG")
```

## Log Format Examples

### Successful Alert Analysis
```
2024-01-01 12:00:00 [INFO] sre_agent.integrations.llm.langchain_client: Starting alert analysis with openai
2024-01-01 12:00:00 [DEBUG] sre_agent.integrations.llm.langchain_client: Full prompt for openai:
Alert Information:
Alert: HighMemoryUsage
Severity: warning
...
2024-01-01 12:00:02 [INFO] sre_agent.integrations.llm.langchain_client: LLM Communication - openai (analyze_alert): success in 2.340s
2024-01-01 12:00:02 [DEBUG] sre_agent.integrations.llm.langchain_client: LLM Response from openai:
Based on the alert analysis...
```

### Error Scenario
```
2024-01-01 12:00:00 [ERROR] sre_agent.integrations.llm.langchain_client: LLM async invocation failed for openai (analyze_alert): API rate limit exceeded
2024-01-01 12:00:00 [INFO] sre_agent.integrations.llm.langchain_client: LLM Interaction Data: {
  "timestamp": 1704067200.123,
  "provider": "openai",
  "method": "analyze_alert",
  "duration_seconds": 0.150,
  "prompt_length": 1500,
  "response_length": 0,
  "status": "error",
  "error": "API rate limit exceeded"
}
```

## Integration with Monitoring

### Metrics to Monitor
- Request frequency by provider
- Average response times
- Error rates
- Token usage (if available)

### Alerting
Consider setting up alerts for:
- High error rates
- Slow response times
- API quota exhaustion
- Unusual traffic patterns

## Best Practices

1. **Regular Log Review**: Check logs regularly for errors and performance issues
2. **Log Retention**: Implement appropriate log retention policies
3. **Monitoring**: Set up automated monitoring for log files
4. **Security**: Protect log files containing prompt/response data
5. **Performance**: Monitor log file sizes and rotation

## Log File Locations

All logs are stored in the `logs/` directory:
```
logs/
├── llm_communications.log      # Primary LLM communication log
├── llm_communications.log.1    # Rotated backup
├── sre_agent.log              # General application log
├── sre_agent_errors.log       # Error-specific log
└── mcp_communications.log     # MCP tool communications
``` 