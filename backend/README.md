# SRE AI Agent Backend

An intelligent Site Reliability Engineering (SRE) agent that automates incident response using AI and Model Control Protocol (MCP) servers for system integration.

## Overview

The SRE AI Agent backend is built with FastAPI and leverages the LangChain framework for AI orchestration. It processes alerts, investigates issues using various monitoring tools, and provides comprehensive analysis and remediation recommendations.

## Features

- **Intelligent Alert Processing**: AI-powered analysis of system alerts
- **MCP Integration**: Seamless integration with monitoring and management tools via MCP servers
- **Multi-LLM Support**: Compatible with OpenAI, Google Gemini, and Grok models
- **LangGraph Workflows**: Sophisticated agent workflows for complex investigations
- **Real-time Progress**: WebSocket-based progress updates during alert processing
- **Runbook Integration**: Automatic runbook retrieval and integration

## Architecture

The backend uses a modern, modular architecture:

```
├── app/
│   ├── agents/              # LangGraph-based SRE agents
│   ├── config/              # Configuration management
│   ├── integrations/        # External service integrations
│   │   ├── llm/            # LangChain LLM clients
│   │   └── mcp/            # MCP client and tools
│   ├── models/              # Pydantic data models
│   ├── services/            # Business logic services
│   └── utils/               # Utility functions
```

## Quick Start

### Prerequisites

- Python 3.11+
- API keys for desired LLM providers
- MCP servers (e.g., Kubernetes MCP server)

### Installation

1. Clone the repository and navigate to the backend directory
2. Install dependencies:
   ```bash
   pip install -e .
   ```

3. Copy the environment template:
   ```bash
   cp env.template .env
   ```

4. Configure your environment variables in `.env`:
   - LLM API keys (OpenAI, Gemini, Grok)
   - MCP server configurations
   - Other service settings

### Running the Service

Start the FastAPI server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive documentation at `http://localhost:8000/docs`.

## Configuration

### Environment Variables

Key configuration options (see `env.template` for complete list):

- `DEFAULT_LLM_PROVIDER`: Primary LLM provider (openai/gemini/grok)
- `OPENAI_API_KEY`: OpenAI API key
- `GEMINI_API_KEY`: Google Gemini API key
- `GROK_API_KEY`: Grok API key
- `MAX_LLM_MCP_ITERATIONS`: Maximum investigation iterations
- `LOG_LEVEL`: Logging level (INFO/DEBUG/WARNING/ERROR)

### MCP Servers

Configure MCP servers in your environment or settings file. Example for Kubernetes:

```python
mcp_servers = {
    "kubernetes": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-kubernetes"],
        "enabled": True
    }
}
```

## API Endpoints

### Core Endpoints

- `POST /alerts`: Submit an alert for processing
- `GET /processing-status/{alert_id}`: Get processing status
- `WebSocket /ws/{alert_id}`: Real-time progress updates
- `GET /health`: Health check
- `GET /alert-types`: Supported alert types

### Example Usage

Submit an alert:
```bash
curl -X POST "http://localhost:8000/alerts" \
  -H "Content-Type: application/json" \
  -d '{
    "alert": "HighMemoryUsage",
    "severity": "high",
    "environment": "production",
    "cluster": "https://k8s.example.com",
    "namespace": "web-app",
    "pod": "web-app-pod-123",
    "message": "Memory usage exceeded 85%",
    "runbook": "https://github.com/company/runbooks/blob/main/memory.md"
  }'
```

## LangChain Integration

The service heavily leverages LangChain for:

- **Prompt Templates**: Structured prompts for different analysis types
- **Tool Integration**: MCP tools wrapped as LangChain Tools
- **Agent Workflows**: LangGraph-based investigation workflows
- **Memory Management**: Conversation memory for context retention
- **Multi-LLM Support**: Abstracted LLM interfaces

## Development

### Project Structure

- `app/agents/sre_agent.py`: Main SRE agent using LangGraph
- `app/services/langchain_alert_service.py`: Alert processing service
- `app/integrations/mcp/mcp_tools.py`: MCP to LangChain Tools conversion
- `app/integrations/llm/langchain_client.py`: LangChain LLM client

### Testing

Run the integration test:
```bash
python test_langchain_refactor.py
```

### Contributing

1. Follow the existing code structure and patterns
2. Use type hints throughout
3. Add comprehensive logging
4. Update tests for new functionality
5. Follow the established error handling patterns

## Monitoring and Logging

The service provides comprehensive logging:

- **Application logs**: General service operations
- **LLM communications**: Detailed LLM request/response logging
- **MCP communications**: MCP tool call logging
- **Performance metrics**: Processing times and success rates

Log levels can be configured via the `LOG_LEVEL` environment variable.

## Troubleshooting

### Common Issues

1. **No LLM model available**: Check API key configuration
2. **MCP server connection failed**: Verify MCP server installation and configuration
3. **Runbook download failed**: Check runbook URL accessibility
4. **High memory usage**: Monitor and adjust `MAX_LLM_MCP_ITERATIONS`

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
```

This provides detailed information about:
- LLM requests and responses
- MCP tool calls and results
- Agent workflow execution
- Error stack traces

## Performance

The service is optimized for:
- **Concurrent processing**: Multiple alerts can be processed simultaneously
- **Efficient workflows**: LangGraph provides optimized execution paths
- **Resource management**: Proper cleanup and resource pooling
- **Caching**: Intelligent caching of MCP tool schemas and results

## Security

- **API key protection**: Environment-based configuration
- **Input validation**: Comprehensive Pydantic model validation
- **Error handling**: Sanitized error responses
- **Resource limits**: Configurable iteration and processing limits

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs for detailed error information
3. Consult the API documentation at `/docs`
4. Create an issue in the project repository 