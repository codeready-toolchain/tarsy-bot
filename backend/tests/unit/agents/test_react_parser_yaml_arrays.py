"""
Test cases for ReAct parser handling of YAML arrays in Action Input.

This reproduces and tests the fix for the issue where YAML arrays in Action Input
are not properly parsed, causing array elements to be lost.
"""

from tarsy.agents.parsers.react_parser import ReActParser


class TestReActParserYAMLArrays:
    """Test ReAct parser handling of YAML array inputs."""
    
    def test_parse_yaml_array_in_action_input(self):
        """Test that YAML arrays in Action Input are properly parsed."""
        action_input = """namespace: production
podName: web-server-abc123
containerName: nginx
commandArgs:
- --verbose
- --config=/etc/app/config.yaml
- --log-level=debug"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert result['namespace'] == 'production'
        assert result['podName'] == 'web-server-abc123'
        assert result['containerName'] == 'nginx'
        assert isinstance(result['commandArgs'], list)
        assert len(result['commandArgs']) == 3
        assert result['commandArgs'][0] == '--verbose'
        assert result['commandArgs'][1] == '--config=/etc/app/config.yaml'
        assert result['commandArgs'][2] == '--log-level=debug'
    
    def test_parse_yaml_mixed_scalar_and_array(self):
        """Test YAML input with both scalar values and arrays."""
        action_input = """namespace: default
labels:
- app=nginx
- env=prod
timeout: 30"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert result['namespace'] == 'default'
        assert isinstance(result['labels'], list)
        assert len(result['labels']) == 2
        assert result['labels'][0] == 'app=nginx'
        assert result['labels'][1] == 'env=prod'
        assert result['timeout'] == 30
    
    def test_parse_yaml_nested_structures(self):
        """Test YAML input with nested structures."""
        action_input = """config:
  host: localhost
  port: 8080
tags:
- backend
- api"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert isinstance(result['config'], dict)
        assert result['config']['host'] == 'localhost'
        assert result['config']['port'] == 8080
        assert isinstance(result['tags'], list)
        assert result['tags'] == ['backend', 'api']
    
    def test_parse_yaml_empty_array(self):
        """Test YAML input with empty array."""
        action_input = """items: []
name: test"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert isinstance(result['items'], list)
        assert len(result['items']) == 0
        assert result['name'] == 'test'
    
    def test_parse_yaml_array_with_special_chars(self):
        """Test YAML array with special characters."""
        action_input = """patterns:
- "*.py"
- '[0-9]+\\.txt'
- /var/log/*.log"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert isinstance(result['patterns'], list)
        assert len(result['patterns']) == 3
        assert result['patterns'][0] == '*.py'
        assert result['patterns'][1] == '[0-9]+\\.txt'
        assert result['patterns'][2] == '/var/log/*.log'
    
    def test_full_react_response_with_yaml_array(self):
        """Test complete ReAct response with YAML array in Action Input."""
        response = """Thought

I need to search for error patterns in the application logs. The log file might be large, so I'll use grep to search for specific error keywords. I'll search case-insensitively for "ERROR" patterns.

Action: kubernetes-server.exec-in-pod

Action Input: namespace: production
podName: web-server-abc123
containerName: app
command:
- grep
- -i
- ERROR
- /var/log/application.log"""
        
        parsed = ReActParser.parse_response(response)
        
        assert parsed.response_type.value == 'thought_action'
        assert parsed.has_action
        assert parsed.tool_call is not None
        assert parsed.tool_call.server == 'kubernetes-server'
        assert parsed.tool_call.tool == 'exec-in-pod'
        assert 'namespace' in parsed.tool_call.parameters
        assert 'command' in parsed.tool_call.parameters
        assert isinstance(parsed.tool_call.parameters['command'], list)
        assert len(parsed.tool_call.parameters['command']) == 4
        assert parsed.tool_call.parameters['command'][0] == 'grep'
        assert parsed.tool_call.parameters['command'][1] == '-i'
    
    def test_backward_compatibility_simple_format(self):
        """Ensure backward compatibility with simple comma/newline separated format."""
        action_input = """namespace: default
podName: nginx-pod
timeout: 30"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert result['namespace'] == 'default'
        assert result['podName'] == 'nginx-pod'
        assert result['timeout'] == 30
    
    def test_backward_compatibility_comma_separated(self):
        """Ensure backward compatibility with comma-separated format."""
        action_input = "namespace: default, podName: nginx-pod, timeout: 30"
        
        result = ReActParser._parse_action_parameters(action_input)
        
        assert result['namespace'] == 'default'
        assert result['podName'] == 'nginx-pod'
        assert result['timeout'] == 30
    
    def test_parse_malformed_yaml_falls_back(self):
        """Test that malformed YAML gracefully falls back to simple parsing."""
        # Invalid YAML: list item without proper parent key
        action_input = """namespace: production
- invalid yaml syntax
podName: web-server"""
        
        result = ReActParser._parse_action_parameters(action_input)
        
        # Should fall back to simple parsing
        assert result is not None
        assert isinstance(result, dict)
        # Simple parser should extract the valid key-value pairs
        assert result['namespace'] == 'production'
        assert result['podName'] == 'web-server'
