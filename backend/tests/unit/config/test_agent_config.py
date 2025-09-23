"""
Comprehensive tests for ConfigurationLoader class in agent_config.py.

Tests cover file loading, validation, error handling, and all private methods.
"""

import os
import tempfile
from unittest.mock import Mock, mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from tarsy.config.agent_config import ConfigurationLoader
from tarsy.config.exceptions import ConfigurationError
from tarsy.models.agent_config import (
    AgentConfigModel,
    CombinedConfigModel,
    MCPServerConfigModel,
)


@pytest.mark.unit
class TestConfigurationLoaderInitialization:
    """Test ConfigurationLoader initialization."""
    
    def test_initialization_success(self):
        """Test successful initialization with valid path."""
        loader = ConfigurationLoader("/path/to/config.yaml")
        
        assert loader.config_file_path == "/path/to/config.yaml"
        assert isinstance(loader.BUILTIN_AGENT_CLASSES, (list, set))
        assert isinstance(loader.BUILTIN_MCP_SERVERS, (list, set))
    
    @patch('tarsy.config.agent_config.get_builtin_agent_class_names')
    @patch('tarsy.config.agent_config.get_builtin_mcp_server_ids')
    def test_initialization_with_builtin_configs(self, mock_mcp_ids, mock_agent_names):
        """Test initialization loads builtin configurations."""
        mock_agent_names.return_value = ["KubernetesAgent", "ConfigurableAgent"]
        mock_mcp_ids.return_value = ["kubernetes-server", "monitoring-server"]
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        assert loader.BUILTIN_AGENT_CLASSES == ["KubernetesAgent", "ConfigurableAgent"]
        assert loader.BUILTIN_MCP_SERVERS == ["kubernetes-server", "monitoring-server"]


@pytest.mark.unit
class TestConfigurationLoaderFileHandling:
    """Test file loading and parsing functionality."""
    
    def test_load_missing_file_gracefully(self):
        """Test graceful handling of missing configuration file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_path = os.path.join(temp_dir, "missing.yaml")
            loader = ConfigurationLoader(non_existent_path)
            
            config = loader.load_and_validate()
            
            assert isinstance(config, CombinedConfigModel)
            assert config.agents == {}
            assert config.mcp_servers == {}
    
    def test_load_empty_file(self):
        """Test loading empty YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            assert isinstance(config, CombinedConfigModel)
            assert config.agents == {}
            assert config.mcp_servers == {}
        finally:
            os.unlink(temp_path)
    
    def test_load_valid_config_file(self):
        """Test loading valid configuration file."""
        valid_config = {
            "agents": {
                "security-agent": {
                    "mcp_servers": ["security-server"],
                    "custom_instructions": "Handle security alerts"
                }
            },
            "mcp_servers": {
                "security-server": {
                    "server_id": "security-server",
                    "server_type": "security",
                    "transport": {
                        "type": "stdio",
                        "command": "python",
                        "args": ["-m", "security.mcp"]
                    },
                    "enabled": True
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(valid_config, f)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            assert len(config.agents) == 1
            assert len(config.mcp_servers) == 1
            assert "security-agent" in config.agents
            assert "security-server" in config.mcp_servers
        finally:
            os.unlink(temp_path)
    
    def test_load_invalid_yaml_format(self):
        """Test error handling for invalid YAML format."""
        invalid_yaml = "agents:\n  - invalid: yaml: structure"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
            
            assert "Invalid YAML format" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    def test_load_non_dict_root(self):
        """Test error when config file root is not a dictionary."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("- not a dictionary")
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
            
            assert "root must be a dictionary" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    def test_permission_error_handling(self):
        """Test permission error handling."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("agents: {}")
            temp_path = f.name
        
        try:
            # Remove read permissions
            os.chmod(temp_path, 0o000)
            
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
            
            assert ("Permission denied" in str(exc_info.value) or 
                    "is not readable" in str(exc_info.value))
        finally:
            # Restore permissions and clean up
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)
    
    def test_unicode_decode_error(self):
        """Test handling of Unicode decode errors."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.yaml', delete=False) as f:
            f.write(b'\xff\xfe invalid utf-8')
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
            
            assert "invalid UTF-8 encoding" in str(exc_info.value)
        finally:
            os.unlink(temp_path)


@pytest.mark.unit
class TestConfigurationLoaderValidation:
    """Test configuration validation functionality."""
    
    @patch('tarsy.config.agent_config.get_builtin_mcp_server_ids')
    def test_validate_mcp_server_references_success(self, mock_builtin_servers):
        """Test successful MCP server reference validation."""
        mock_builtin_servers.return_value = ["builtin-server"]
        
        config = CombinedConfigModel(
            agents={
                "test-agent": AgentConfigModel(
                    mcp_servers=["builtin-server", "custom-server"]
                )
            },
            mcp_servers={
                "custom-server": MCPServerConfigModel(
                    server_id="custom-server",
                    server_type="custom",
                    transport={"type": "stdio", "command": "test"},
                    enabled=True
                )
            }
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        loader._validate_mcp_server_references(config)  # Should not raise
    
    @patch('tarsy.config.agent_config.get_builtin_mcp_server_ids')
    def test_validate_mcp_server_references_failure(self, mock_builtin_servers):
        """Test MCP server reference validation failure."""
        mock_builtin_servers.return_value = ["builtin-server"]
        
        config = CombinedConfigModel(
            agents={
                "test-agent": AgentConfigModel(
                    mcp_servers=["nonexistent-server"]
                )
            },
            mcp_servers={}
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ConfigurationError) as exc_info:
            loader._validate_mcp_server_references(config)
        
        assert "references unknown MCP server" in str(exc_info.value)
        assert "nonexistent-server" in str(exc_info.value)
    
    @patch('tarsy.config.agent_config.get_builtin_agent_class_names')
    @patch('tarsy.config.agent_config.get_builtin_mcp_server_ids')
    def test_check_naming_conflicts_agent_name(self, mock_mcp_ids, mock_agent_names):
        """Test agent name conflict detection."""
        mock_agent_names.return_value = ["KubernetesAgent"]
        mock_mcp_ids.return_value = []
        
        config = CombinedConfigModel(
            agents={
                "KubernetesAgent": AgentConfigModel(
                    mcp_servers=["test-server"]
                )
            },
            mcp_servers={}
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ConfigurationError) as exc_info:
            loader._check_naming_conflicts(config)
        
        assert "conflicts with built-in agent class" in str(exc_info.value)
    
    @patch('tarsy.config.agent_config.get_builtin_agent_class_names')
    @patch('tarsy.config.agent_config.get_builtin_mcp_server_ids')
    def test_check_naming_conflicts_mcp_server(self, mock_mcp_ids, mock_agent_names):
        """Test MCP server name conflict detection."""
        mock_agent_names.return_value = []
        mock_mcp_ids.return_value = ["kubernetes-server"]
        
        config = CombinedConfigModel(
            agents={},
            mcp_servers={
                "kubernetes-server": MCPServerConfigModel(
                    server_id="kubernetes-server",
                    server_type="kubernetes",
                    transport={"type": "stdio", "command": "test"},
                    enabled=True
                )
            }
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ConfigurationError) as exc_info:
            loader._check_naming_conflicts(config)
        
        assert "conflicts with built-in MCP server" in str(exc_info.value)
    
    def test_validate_configuration_completeness_no_alert_types(self):
        """Test configuration completeness validation - alert types are now optional."""
        # Create agent config without alert types - should now be valid since they're optional
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"]  # Only mcp_servers are required now
        )
        
        config = CombinedConfigModel(
            agents={"test-agent": agent_config},
            mcp_servers={}
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        # Should not raise an error anymore since alert_types are optional
        try:
            loader._validate_configuration_completeness(config)
        except ConfigurationError:
            pytest.fail("Validation should not fail when agent has no alert_types (they are now optional)")
    
    def test_validate_configuration_completeness_no_mcp_servers(self):
        """Test configuration completeness validation - missing MCP servers."""
        # Create a valid config first, then manipulate it to bypass Pydantic validation
        agent_config = AgentConfigModel(
            mcp_servers=["temp"]
        )
        # Bypass Pydantic validation by directly setting the attribute
        agent_config.mcp_servers = []
        
        config = CombinedConfigModel(
            agents={"test-agent": agent_config},
            mcp_servers={}
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ConfigurationError) as exc_info:
            loader._validate_configuration_completeness(config)
        
        assert "has no MCP servers configured" in str(exc_info.value)
    
    def test_validate_configuration_completeness_no_transport(self):
        """Test configuration completeness validation - missing transport."""
        # Create a valid config first, then manipulate it
        server_config = MCPServerConfigModel(
            server_id="test-server",
            server_type="test",
            transport={"type": "stdio", "command": "test"},
            enabled=True
        )
        # Bypass Pydantic validation by directly setting the attribute to None
        server_config.transport = None
        
        config = CombinedConfigModel(
            agents={},
            mcp_servers={"test-server": server_config}
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ConfigurationError) as exc_info:
            loader._validate_configuration_completeness(config)
        
        assert "has no transport configured" in str(exc_info.value)
    
    def test_validate_configuration_completeness_disabled_server_warning(self, caplog):
        """Test warning for disabled servers that are referenced."""
        config = CombinedConfigModel(
            agents={
                "test-agent": AgentConfigModel(
                    mcp_servers=["disabled-server"]
                )
            },
            mcp_servers={
                "disabled-server": MCPServerConfigModel(
                    server_id="disabled-server",
                    server_type="test",
                    transport={"type": "stdio", "command": "test"},
                    enabled=False  # Disabled server
                )
            }
        )
        
        loader = ConfigurationLoader("/test/config.yaml")
        loader._validate_configuration_completeness(config)
        
        # Check that warning was logged
        assert "references disabled MCP servers" in caplog.text


@pytest.mark.unit
class TestConfigurationLoaderPrivateMethods:
    """Test private methods of ConfigurationLoader."""
    
    def test_validate_config_file_path_missing_file(self):
        """Test validation of missing file path."""
        loader = ConfigurationLoader("/nonexistent/file.yaml")
        loader._validate_config_file_path()  # Should not raise for missing file
    
    def test_validate_config_file_path_directory_not_file(self):
        """Test validation when path is a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            loader = ConfigurationLoader(temp_dir)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader._validate_config_file_path()
            
            assert "is not a file" in str(exc_info.value)
    
    @patch('os.access')
    def test_validate_config_file_path_not_readable(self, mock_access):
        """Test validation when file is not readable."""
        mock_access.return_value = False
        
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader._validate_config_file_path()
            
            assert "is not readable" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @patch('builtins.open', mock_open(read_data="agents: {}\nmcp_servers: {}"))
    def test_load_yaml_file_success(self):
        """Test successful YAML file loading."""
        loader = ConfigurationLoader("/test/config.yaml")
        result = loader._load_yaml_file()
        
        assert result == {"agents": {}, "mcp_servers": {}}
    
    def test_validate_configuration_structure_success(self):
        """Test successful configuration structure validation."""
        raw_config = {
            "agents": {
                "test-agent": {
                    "mcp_servers": ["test-server"]
                }
            },
            "mcp_servers": {}
        }
        
        loader = ConfigurationLoader("/test/config.yaml")
        config = loader._validate_configuration_structure(raw_config)
        
        assert isinstance(config, CombinedConfigModel)
        assert len(config.agents) == 1
    
    def test_validate_configuration_structure_validation_error(self):
        """Test configuration structure validation with invalid data."""
        raw_config = {
            "agents": {
                "test-agent": {
                    "mcp_servers": "not a list"  # Should be a list
                }
            }
        }
        
        loader = ConfigurationLoader("/test/config.yaml")
        
        with pytest.raises(ValidationError):
            loader._validate_configuration_structure(raw_config)
    
    def test_detect_circular_dependencies_placeholder(self):
        """Test circular dependency detection (currently a placeholder)."""
        config = CombinedConfigModel(agents={}, mcp_servers={})
        loader = ConfigurationLoader("/test/config.yaml")
        
        loader._detect_circular_dependencies(config)  # Should not raise


@pytest.mark.unit
class TestConfigurationLoaderErrorFormatting:
    """Test error formatting methods."""
    
    def test_format_yaml_error_with_problem_mark(self):
        """Test YAML error formatting with line/column information."""
        # Create a mock YAML error with problem_mark
        error = yaml.YAMLError("test error")
        error.problem_mark = Mock()
        error.problem_mark.line = 4  # 0-based
        error.problem_mark.column = 10  # 0-based
        
        loader = ConfigurationLoader("/test/config.yaml")
        formatted = loader._format_yaml_error(error)
        
        assert "line 5, column 11" in formatted  # Should be 1-based
        assert "test error" in formatted
        assert "YAML validator" in formatted
    
    def test_format_yaml_error_mapping_values_suggestion(self):
        """Test YAML error formatting with mapping values suggestion."""
        error = yaml.YAMLError("mapping values are not allowed here")
        
        loader = ConfigurationLoader("/test/config.yaml")
        formatted = loader._format_yaml_error(error)
        
        assert "missing colons" in formatted
        assert "proper indentation" in formatted
    
    def test_format_yaml_error_unmatched_brackets_suggestion(self):
        """Test YAML error formatting with unmatched brackets suggestion."""
        error = yaml.YAMLError("could not find expected ']'")
        
        loader = ConfigurationLoader("/test/config.yaml")
        formatted = loader._format_yaml_error(error)
        
        assert "unmatched brackets" in formatted
        assert "properly closed" in formatted
    
    def test_format_yaml_error_invalid_character_suggestion(self):
        """Test YAML error formatting with invalid character suggestion."""
        error = yaml.YAMLError("found character that cannot start any token")
        
        loader = ConfigurationLoader("/test/config.yaml")
        formatted = loader._format_yaml_error(error)
        
        assert "invalid characters" in formatted
        assert "UTF-8 encoding" in formatted
    
    def test_format_validation_error_comprehensive(self):
        """Test comprehensive Pydantic validation error formatting."""
        # Create a real validation error by attempting to validate invalid data
        try:
            CombinedConfigModel(
                agents={
                    "test-agent": {
                        "mcp_servers": []  # Empty list (too short)
                    }
                },
                mcp_servers={
                    "test-server": {
                        "server_id": "test-server",
                        "server_type": "test",
                        "enabled": "not a boolean",  # Should be boolean
                        "transport": {"type": "stdio", "command": "test"}
                    }
                }
            )
        except ValidationError as error:
            loader = ConfigurationLoader("/test/config.yaml")
            formatted = loader._format_validation_error(error)
            
            assert "Configuration validation failed" in formatted
            assert "Validation errors" in formatted
            assert "total)" in formatted


@pytest.mark.unit
class TestGetChainConfigs:
    """Test get_chain_configs functionality."""
    
    def test_get_chain_configs_success(self):
        """Test successful chain configuration retrieval."""
        valid_config = {
            "agents": {},
            "mcp_servers": {},
            "agent_chains": {
                "test-chain": {
                    "alert_types": ["test-alert"],
                    "stages": [
                        {
                            "name": "analysis",
                            "agent": "TestAgent",
                            "iteration_strategy": "react"
                        }
                    ],
                    "description": "Test chain description"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(valid_config, f)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            chain_configs = loader.get_chain_configs()
            
            assert "test-chain" in chain_configs
            chain_config = chain_configs["test-chain"]
            assert chain_config["alert_types"] == ["test-alert"]
            assert len(chain_config["stages"]) == 1
            assert chain_config["stages"][0]["name"] == "analysis"
            assert chain_config["description"] == "Test chain description"
        finally:
            os.unlink(temp_path)
    
    def test_get_chain_configs_empty_chains(self):
        """Test chain configuration retrieval with no chains."""
        valid_config = {
            "agents": {},
            "mcp_servers": {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(valid_config, f)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            chain_configs = loader.get_chain_configs()
            
            assert chain_configs == {}
        finally:
            os.unlink(temp_path)
    
    def test_get_chain_configs_error_handling(self, caplog):
        """Test chain configuration error handling."""
        # Create invalid file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content:")
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            chain_configs = loader.get_chain_configs()
            
            assert chain_configs == {}
            assert "Failed to load chain configurations" in caplog.text
        finally:
            os.unlink(temp_path)


@pytest.mark.unit
class TestConfigurationLoaderIntegration:
    """Integration tests for ConfigurationLoader."""
    
    def test_full_configuration_loading_workflow(self):
        """Test complete configuration loading workflow."""
        complete_config = {
            "agents": {
                "security-agent": {
                    "mcp_servers": ["security-scanner"],
                    "custom_instructions": "Focus on security analysis",
                    "iteration_strategy": "react"
                }
            },
            "mcp_servers": {
                "security-scanner": {
                    "server_id": "security-scanner",
                    "server_type": "security",
                    "transport": {
                        "type": "stdio",
                        "command": "python",
                        "args": ["-m", "security.scanner"]
                    },
                    "enabled": True
                }
            },
            "agent_chains": {
                "security-chain": {
                    "alert_types": ["security-incident"],
                    "stages": [
                        {
                            "name": "initial-analysis",
                            "agent": "security-agent",
                            "iteration_strategy": "react"
                        }
                    ],
                    "description": "Security incident analysis chain"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(complete_config, f)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            # Test main configuration loading
            config = loader.load_and_validate()
            assert len(config.agents) == 1
            assert len(config.mcp_servers) == 1
            assert len(config.agent_chains) == 1
            
            # Test chain configuration retrieval
            chain_configs = loader.get_chain_configs()
            assert len(chain_configs) == 1
            assert "security-chain" in chain_configs
            
        finally:
            os.unlink(temp_path)
    
    def test_edge_case_handling_comprehensive(self):
        """Test comprehensive edge case handling."""
        loader = ConfigurationLoader("/nonexistent/file.yaml")
        
        # Missing file should return empty config
        config = loader.load_and_validate()
        assert config.agents == {}
        assert config.mcp_servers == {}
        
        # Chain configs should also handle missing file
        chain_configs = loader.get_chain_configs()
        assert chain_configs == {}
