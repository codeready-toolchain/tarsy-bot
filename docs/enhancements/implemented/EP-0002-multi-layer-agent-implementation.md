# EP-0002: Multi-Layer Agent Architecture - Implementation Plan

**Status:** Approved  
**Created:** 2025-07-23  
**Phase:** Implementation Ready
**Requirements Document:** `docs/enhancements/approved/EP-0002-multi-layer-agent-requirements.md`
**Design Document:** `docs/enhancements/approved/EP-0002-multi-layer-agent-design.md`

---

## Implementation Overview

### Implementation Summary
**COMPLETE REPLACEMENT APPROACH**: Transform the monolithic AlertService into a multi-layer agent architecture by completely replacing the AlertService class with AlertOrchestrator. No legacy code will be preserved - the entire AlertService implementation will be replaced with new agent-based orchestration logic while maintaining identical API endpoints for external compatibility.

The implementation introduces an inheritance-based system where agents extend BaseAgent with domain-specific configurations and MCP server assignments, starting with a KubernetesAgent for namespace-related alerts.

### Implementation Goals
- Implement inheritance-based BaseAgent abstract class with common processing logic
- Create specialized KubernetesAgent for namespace-related alerts with focused MCP server subset
- Build AlertOrchestrator to completely replace AlertService with delegation logic
- Establish AgentRegistry for static alert type to agent class mappings  
- Create MCPServerRegistry as simple static map for MCP server management with embedded instructions
- Maintain full backward compatibility with existing API endpoints (while completely replacing internal implementation)

### Implementation Strategy
**CRITICAL**: This is a complete code replacement, NOT an extension or wrapper approach. The existing AlertService class will be entirely removed and replaced with AlertOrchestrator implementation.

### Implementation Constraints
- Must maintain existing API endpoint contracts without breaking changes (same interface, completely new implementation)
- Cannot modify external MCP server interfaces or LLM provider APIs
- Must preserve existing WebSocket communication patterns and real-time updates
- Implementation must use existing Python/FastAPI technology stack
- Agent delegation overhead must be minimal (< 5ms processing time impact)

### Success Criteria
- [ ] Kubernetes agent processes "NamespaceTerminating" alerts with identical quality to current system (REQ-2.4)
- [ ] Orchestrator layer successfully delegates alerts to appropriate specialized agents (REQ-2.1)
- [ ] Alert type to agent mapping is defined in configuration files and loaded at startup without requiring code changes (REQ-2.2)
- [ ] All existing API endpoints continue to work without modification (REQ-2.11)
- [ ] Processing status display indicates which agent is currently handling an alert (REQ-2.9)
- [ ] System returns clear error message when no specialized agent is available (REQ-2.24)
- [ ] Agents only access their assigned MCP server subset, not the complete global list (REQ-2.8)
- [ ] Agent failures do not affect processing of alerts by other agent types (REQ-2.22)

## Phase 1: Foundation & Core Architecture

### Phase 1 Overview
**Dependencies:** None  
**Goal:** Establish the foundational architecture with BaseAgent, MCPServerRegistry, and AgentRegistry components

#### Step 1.1: Create BaseAgent Abstract Class
**Goal:** Implement the abstract base class that provides common processing logic for all agents

**Files to Create/Modify:**
- `backend/app/agents/__init__.py` (new)
- `backend/app/agents/base_agent.py` (new)

**AI Prompt:** `Implement Step 1.1 of EP-0002: Create BaseAgent abstract class with common processing logic, abstract methods for mcp_servers() and custom_instructions(), and standard process_alert() implementation.`

**Tasks:**
- [ ] Create agents package structure with __init__.py
- [ ] Implement BaseAgent abstract class using Python ABC
- [ ] Define abstract method mcp_servers() -> List[str] for agent-specific MCP server ID selection
- [ ] Define abstract method custom_instructions() -> str for optional agent-specific guidance
- [ ] Implement common process_alert(alert, runbook, callback) method with iterative LLM analysis
- [ ] Add dependency injection constructor for LLM client, MCP client, progress callback, and MCP registry
- [ ] Implement three-tier instruction composition logic: _compose_instructions() method combining general + MCP server instructions + custom instructions
- [ ] Add _get_general_instructions() method with universal SRE guidance
- [ ] Add comprehensive error handling and logging

**Dependencies:**
- Python abc module for abstract base classes
- Existing LLM and MCP integration patterns

**Validation Criteria:**
- [ ] BaseAgent class is properly abstract and cannot be instantiated directly
- [ ] Abstract methods mcp_servers() and custom_instructions() are correctly defined
- [ ] Common process_alert() method includes all shared processing logic
- [ ] Three-tier instruction composition (_compose_instructions) works correctly
- [ ] _get_general_instructions() provides universal SRE guidance
- [ ] Dependency injection works correctly in constructor with MCP registry
- [ ] Error handling covers all failure scenarios with clear messages

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.agents.base_agent import BaseAgent; print('BaseAgent imported successfully')"
python -c "from abc import ABC; from tarsy.agents.base_agent import BaseAgent; print('BaseAgent is abstract:', BaseAgent.__abstractmethods__)"
pytest tests/unit/test_base_agent.py -v
```

**Rollback Plan:**
- Remove agents package and BaseAgent class if integration issues occur

#### Step 1.2: Create MCPServerRegistry
**Goal:** Implement global MCP server registry with embedded instructions for reuse across agents

**Files to Create/Modify:**
- `backend/app/services/mcp_server_registry.py` (new)
- `backend/app/models/mcp_config.py` (new)

**AI Prompt:** `Implement Step 1.2 of EP-0002: Create simple static MCPServerRegistry as a pre-defined map for MCP server configurations with embedded instructions, loaded once at startup.`

**Tasks:**
- [ ] Create MCPServerConfig data model with server_id, server_type, connection_params, instructions (embedded LLM instructions)
- [ ] Implement simple static MCPServerRegistry class - just a dictionary wrapper loaded once at startup
- [ ] Add get_server_configs(server_ids: List[str]) method for simple dictionary lookups of agent-specific subsets
- [ ] Add basic validate_server_ids(server_ids: List[str]) method for configuration validation  
- [ ] Implement configuration parsing from settings with embedded instruction support - no runtime changes
- [ ] Include comprehensive embedded LLM instructions for kubernetes, argocd, and aws server types with operational guidance
- [ ] Ensure registry is immutable after initialization - no dynamic server management

**Dependencies:**
- Step 1.1 must be complete for integration with BaseAgent
- Existing configuration system patterns

**Validation Criteria:**
- [ ] MCPServerRegistry loads static configuration once at startup from application settings
- [ ] get_server_configs() performs simple dictionary lookups and returns requested configurations with embedded instructions
- [ ] Basic server configuration validation works for all server types including instruction validation
- [ ] Embedded LLM instructions are properly associated with each server configuration at load time
- [ ] Registry handles missing or invalid server IDs gracefully with simple error messages
- [ ] Registry is immutable after initialization - no runtime modification methods available
- [ ] Simple dictionary lookup performance for agent-specific server subsets

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.services.mcp_server_registry import MCPServerRegistry; registry = MCPServerRegistry(); print('Registry created successfully')"
python -c "from tarsy.models.mcp_config import MCPServerConfig; print('MCPServerConfig model available')"
pytest tests/unit/test_mcp_server_registry.py -v
```

**Rollback Plan:**
- Remove MCPServerRegistry and related models if configuration issues occur

#### Step 1.3: Create AgentRegistry and AgentFactory
**Goal:** Implement agent registry for alert type mappings and factory for agent instantiation

**Files to Create/Modify:**
- `backend/app/services/agent_registry.py` (new)
- `backend/app/services/agent_factory.py` (new)

**AI Prompt:** `Implement Step 1.3 of EP-0002: Create simple static AgentRegistry as a pre-defined map for alert type to agent class mappings and AgentFactory with static class resolution, both loaded once at startup.`

**Tasks:**
- [ ] Implement simple static AgentRegistry class - just a dictionary wrapper with alert type to agent class mappings loaded once
- [ ] Add get_agent_for_alert_type(alert_type: str) -> Optional[str] method for simple dictionary lookup
- [ ] Implement simple static AgentFactory class with pre-defined agent class to Python class mappings
- [ ] Add create_agent(agent_class_name: str) -> BaseAgent method with dependency injection - simple class resolution
- [ ] Maintain static registry of available agent classes (KubernetesAgent, etc.) - no runtime changes
- [ ] Add basic error handling for unknown agent classes with simple error messages
- [ ] Include basic configuration validation for agent registry entries at initialization only

**Dependencies:**
- Step 1.1 must be complete (BaseAgent dependency)
- Step 1.2 must be complete (MCPServerRegistry dependency)

**Validation Criteria:**
- [ ] AgentRegistry loads static alert type to agent class mappings once at startup from configuration
- [ ] get_agent_for_alert_type() performs simple dictionary lookup and returns correct agent class name or None
- [ ] AgentFactory resolves class names to instantiated agents with all dependencies injected using static class mappings
- [ ] Basic error handling provides clear messages for unknown agent classes
- [ ] Basic configuration validation prevents invalid registry entries at initialization
- [ ] Both registries are immutable after initialization - no runtime modification methods

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.services.agent_registry import AgentRegistry; registry = AgentRegistry(); print('AgentRegistry created successfully')"
python -c "from tarsy.services.agent_factory import AgentFactory; print('AgentFactory imported successfully')"
pytest tests/unit/test_agent_registry.py -v
pytest tests/unit/test_agent_factory.py -v
```

**Rollback Plan:**
- Remove AgentRegistry and AgentFactory if class resolution issues occur

### Phase 1 Completion Criteria
- [ ] BaseAgent abstract class provides complete foundation for agent inheritance
- [ ] MCPServerRegistry manages global MCP server configurations with embedded instructions
- [ ] AgentRegistry and AgentFactory provide complete agent lifecycle management
- [ ] All unit tests pass for foundation components
- [ ] Configuration system supports all new registry requirements

## Phase 2: Specialized Agent Implementation

### Phase 2 Overview

**Dependencies:** Phase 1 completion  
**Goal:** Implement KubernetesAgent and update configuration system for agent support

#### Step 2.1: Implement KubernetesAgent
**Goal:** Create specialized Kubernetes agent that inherits from BaseAgent

**Files to Create/Modify:**
- `backend/app/agents/kubernetes_agent.py` (new)

**AI Prompt:** `Implement Step 2.1 of EP-0002: Create KubernetesAgent class inheriting from BaseAgent with kubernetes-specific MCP server configuration and custom instructions.`

**Tasks:**
- [ ] Create KubernetesAgent class inheriting from BaseAgent
- [ ] Implement mcp_servers() method returning ["kubernetes-server"] for MCP server subset assignment
- [ ] Implement custom_instructions() method returning empty string (no custom instructions for initial implementation)
- [ ] Ensure agent retrieves and uses Kubernetes server instructions from MCP registry (embedded in server config)
- [ ] Verify three-tier instruction composition: General (BaseAgent) + MCP server (registry) + Custom (none initially)
- [ ] Include error handling specific to Kubernetes operations
- [ ] Add logging with Kubernetes-specific context information
- [ ] Validate agent works with namespace termination scenarios using focused kubernetes-server tools only

**Dependencies:**
- Phase 1 completion (BaseAgent, MCPServerRegistry, AgentFactory)
- Kubernetes MCP server must be available in global registry

**Validation Criteria:**
- [ ] KubernetesAgent correctly inherits from BaseAgent
- [ ] mcp_servers() returns only kubernetes-server ID for focused tool subset
- [ ] custom_instructions() returns empty string (no custom instructions initially)
- [ ] Agent retrieves Kubernetes server instructions from MCP registry correctly
- [ ] Agent composes final instructions from General + MCP server + Custom (empty) sources
- [ ] Agent processes namespace termination alerts correctly using only kubernetes-server tools
- [ ] Error handling provides Kubernetes-specific error context
- [ ] Logging includes agent-specific information and instruction composition details

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.agents.kubernetes_agent import KubernetesAgent; from tarsy.agents.base_agent import BaseAgent; print('KubernetesAgent inherits from BaseAgent:', issubclass(KubernetesAgent, BaseAgent))"
python -c "from tarsy.agents.kubernetes_agent import KubernetesAgent; agent = KubernetesAgent(None, None, None, None); print('MCP servers:', agent.mcp_servers()); print('Custom instructions empty:', agent.custom_instructions() == '')"
pytest tests/unit/test_kubernetes_agent.py -v
```

**Rollback Plan:**
- Remove KubernetesAgent and fall back to BaseAgent direct usage

#### Step 2.2: Update Configuration System
**Goal:** Extend configuration system to support agent registry and MCP server registry

**Files to Create/Modify:**
- `backend/app/config/settings.py` (modify)
- `backend/env.template` (modify)

**AI Prompt:** `Implement Step 2.2 of EP-0002: Update configuration system to support agent registry mappings and MCP server registry with embedded instructions, completely replacing existing mcp_servers configuration to eliminate duplication and establish single source of truth.`

**Tasks:**
- [ ] Add simple static agent_registry configuration section to settings.py - just a dictionary of alert type to agent mappings
- [ ] Add simple static mcp_server_registry configuration section with comprehensive embedded LLM instructions - loaded once at startup
- [ ] **CRITICAL**: Remove existing mcp_servers field from settings.py to eliminate duplication - MCP Server Registry is the ONLY source of truth
- [ ] **CRITICAL**: Remove existing get_mcp_config() method from settings.py - replaced by MCP Server Registry lookups
- [ ] Update env.template with simple example configurations showing static registry patterns
- [ ] Add basic configuration validation for registry entries at application startup only
- [ ] Include default static configuration mapping "NamespaceTerminating" to KubernetesAgent with kubernetes-server
- [ ] Add code comments explaining simple static registry pattern and three-tier instruction composition
- [ ] Ensure no MCP server configuration duplication - MCP Server Registry as single source of truth

**Dependencies:**
- Step 2.1 must be complete (KubernetesAgent needs to be referenced in configuration)

**Validation Criteria:**
- [ ] Configuration system loads simple static agent registry settings correctly as a dictionary
- [ ] MCP server registry configuration loads as static dictionary with comprehensive embedded LLM instructions for each server
- [ ] **CRITICAL**: Existing mcp_servers field has been completely removed from settings.py (no duplication)
- [ ] **CRITICAL**: Existing get_mcp_config() method has been completely removed from settings.py (no duplication)
- [ ] Basic configuration validation prevents invalid entries at startup and ensures instruction completeness
- [ ] Default static configuration correctly maps "NamespaceTerminating" to KubernetesAgent with kubernetes-server assignment
- [ ] Three-tier instruction composition is properly configured in static setup (general + MCP + custom)
- [ ] MCP Server Registry is the ONLY source for MCP server configurations - no other configuration source exists
- [ ] No runtime configuration changes possible - all registries are immutable after startup

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.config.settings import Settings; settings = Settings(); print('Agent registry loaded:', hasattr(settings, 'agent_registry'))"
python -c "from tarsy.config.settings import Settings; settings = Settings(); print('MCP server registry loaded:', hasattr(settings, 'mcp_server_registry'))"
python -c "from tarsy.config.settings import Settings; settings = Settings(); print('OLD mcp_servers REMOVED:', not hasattr(settings, 'mcp_servers'))"
python -c "from tarsy.config.settings import Settings; settings = Settings(); print('OLD get_mcp_config REMOVED:', not hasattr(settings, 'get_mcp_config'))"
pytest tests/unit/test_settings.py -v
```

**Rollback Plan:**
- Revert configuration changes and use hardcoded agent mappings

#### Step 2.3: Integration Testing for Agent Components
**Goal:** Validate integration between all agent components

**Files to Create/Modify:**
- `backend/tests/integration/test_agent_integration.py` (new)

**AI Prompt:** `Implement Step 2.3 of EP-0002: Create comprehensive integration tests for BaseAgent, KubernetesAgent, registries, and configuration system, with special focus on three-tier instruction composition validation.`

**Tasks:**
- [ ] Create integration test for complete agent lifecycle
- [ ] Test agent registry to factory to instance creation flow
- [ ] Validate MCP server registry integration with agents including instruction retrieval
- [ ] Test three-tier instruction composition across component boundaries (BaseAgent + MCP registry + KubernetesAgent)
- [ ] Test configuration loading and agent instantiation with instruction management
- [ ] Verify agent-specific MCP server subset assignment (KubernetesAgent gets only kubernetes-server)
- [ ] Validate KubernetesAgent custom_instructions() returns empty string as expected
- [ ] Test error scenarios and error message clarity

**Dependencies:**
- Step 2.1 and 2.2 must be complete

**Validation Criteria:**
- [ ] All agent components integrate correctly
- [ ] Configuration drives agent behavior as expected
- [ ] Error handling works across component boundaries
- [ ] Agent-specific MCP server subsets are correctly assigned
- [ ] Integration tests provide comprehensive coverage

**Success Check:**
```bash
# Commands to verify this step
cd backend
pytest tests/integration/test_agent_integration.py -v
```

**Rollback Plan:**
- Fix integration issues or simplify component interactions

### Phase 2 Completion Criteria
- [ ] KubernetesAgent successfully inherits from BaseAgent with specialized behavior
- [ ] Configuration system supports all agent and MCP server registry requirements
- [ ] **CRITICAL**: MCP configuration migration complete - existing mcp_servers and get_mcp_config() completely removed, MCP Server Registry is the only source
- [ ] Integration tests validate complete agent component interaction
- [ ] Agent-specific MCP server subsets are correctly configured and assigned
- [ ] Error handling provides clear agent-specific error messages

## Phase 3: Orchestrator Implementation

### Phase 3 Overview

**Dependencies:** Phase 2 completion  
**Goal:** Refactor AlertService to AlertOrchestrator with agent delegation logic

#### Step 3.1: Create AlertOrchestrator
**Goal:** Implement orchestrator that replaces AlertService with agent delegation

**Files to Create/Modify:**
- `backend/app/services/alert_orchestrator.py` (new)
- `backend/app/services/alert_service.py` (completely replace with AlertOrchestrator implementation)

**AI Prompt:** `Implement Step 3.1 of EP-0002: Create AlertOrchestrator and completely replace AlertService with new agent delegation logic. Remove all legacy AlertService code and replace with orchestrator-based implementation that maintains API compatibility.`

**Tasks:**
- [ ] Create AlertOrchestrator class with agent delegation logic
- [ ] Implement process_alert() method with orchestration workflow
- [ ] Add runbook download integration (reuse existing RunbookService)
- [ ] Implement agent selection via AgentRegistry
- [ ] Add agent instantiation via AgentFactory
- [ ] Include progress reporting through WebSocket manager
- [ ] Add comprehensive error handling for delegation failures
- [ ] **CRITICAL**: Completely replace AlertService class with AlertOrchestrator implementation - remove all legacy code
- [ ] Ensure AlertOrchestrator provides same public interface as original AlertService for API compatibility

**Dependencies:**
- Phase 2 completion (all agent components must be available)
- Existing RunbookService and WebSocketManager integration

**Validation Criteria:**
- [ ] AlertOrchestrator successfully delegates alerts to appropriate agents
- [ ] Runbook download and distribution to agents works correctly
- [ ] Progress reporting includes agent-specific information
- [ ] Error handling provides clear indication of orchestrator vs agent failures
- [ ] **CRITICAL**: AlertService class has been completely replaced with AlertOrchestrator implementation - no legacy code remains
- [ ] AlertOrchestrator provides identical public interface as original AlertService for API compatibility

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.services.alert_orchestrator import AlertOrchestrator; orchestrator = AlertOrchestrator(); print('AlertOrchestrator created successfully')"
pytest tests/unit/test_alert_orchestrator.py -v
```

**Rollback Plan:**
- Revert alert_service.py from git backup if orchestrator implementation fails

#### Step 3.2: Update FastAPI Application Integration
**Goal:** Integrate AlertOrchestrator with FastAPI application and WebSocket manager

**Files to Create/Modify:**
- `backend/app/main.py` (modify)
- `backend/app/services/websocket_manager.py` (modify)

**AI Prompt:** `Implement Step 3.2 of EP-0002: Update FastAPI application to use AlertOrchestrator instead of AlertService, ensuring all endpoints and WebSocket functionality continue working.`

**Tasks:**
- [ ] Update main.py dependency injection to use AlertOrchestrator (which has completely replaced AlertService)
- [ ] Update progress callback integration for agent-specific updates
- [ ] Modify WebSocket manager to handle agent information in status updates  
- [ ] Update ProcessingStatus model to include current_agent field
- [ ] Ensure all existing API endpoints continue working without modification (same interface, completely new implementation)
- [ ] Add agent information to progress reporting
- [ ] Test WebSocket real-time updates with agent context

**Dependencies:**
- Step 3.1 must be complete (AlertOrchestrator implementation)
- Existing WebSocket and API integration patterns

**Validation Criteria:**
- [ ] All existing API endpoints work without modification
- [ ] WebSocket updates include agent information
- [ ] Progress reporting correctly shows current processing agent
- [ ] ProcessingStatus includes agent-specific details
- [ ] No breaking changes to existing API contracts

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.main import tarsy; print('FastAPI app updated successfully')"
pytest tests/integration/test_api_integration.py -v
```

**Rollback Plan:**
- Revert FastAPI application and alert_service.py from git backup if integration issues occur

#### Step 3.3: End-to-End Integration Testing
**Goal:** Validate complete end-to-end flow from API to agent processing

**Files to Create/Modify:**
- `backend/tests/integration/test_e2e_processing.py` (new)

**AI Prompt:** `Implement Step 3.3 of EP-0002: Create comprehensive end-to-end tests for complete alert processing flow from API endpoint through orchestrator to agent processing and result return.`

**Tasks:**
- [ ] Create end-to-end test for namespace termination alert processing
- [ ] Test complete API → Orchestrator → KubernetesAgent → Result flow
- [ ] Validate WebSocket progress updates throughout processing
- [ ] Test error scenarios with clear error message propagation
- [ ] Verify agent-specific MCP server usage in processing
- [ ] Test unknown alert type error handling

**Dependencies:**
- Step 3.2 must be complete (full FastAPI integration)

**Validation Criteria:**
- [ ] Complete end-to-end processing works for supported alert types
- [ ] WebSocket progress updates work throughout entire flow
- [ ] Error scenarios provide appropriate error messages
- [ ] Agent-specific processing details are included in results
- [ ] Unknown alert types return clear error messages

**Success Check:**
```bash
# Commands to verify this step
cd backend
pytest tests/integration/test_e2e_processing.py -v
```

**Rollback Plan:**
- Address integration issues or simplify orchestration logic

### Phase 3 Completion Criteria
- [ ] **CRITICAL**: AlertOrchestrator has completely replaced AlertService - no legacy AlertService code remains
- [ ] FastAPI application integration maintains all existing API functionality with completely new internal implementation
- [ ] End-to-end processing works correctly for supported alert types
- [ ] WebSocket progress reporting includes agent-specific information
- [ ] Error handling provides clear indication of failure points

## Phase 4: Documentation & Finalization

### Phase 4 Overview
**Dependencies:** Phase 3 completion  
**Goal:** Complete documentation, final validation, and deployment preparation

#### Step 4.1: Code Documentation
**Goal:** Add comprehensive docstrings and inline documentation

**Files to Create/Modify:**
- `backend/app/agents/base_agent.py` (modify - add docstrings)
- `backend/app/agents/kubernetes_agent.py` (modify - add docstrings)
- `backend/app/services/alert_orchestrator.py` (modify - add docstrings)
- `backend/app/services/agent_registry.py` (modify - add docstrings)
- `backend/app/services/agent_factory.py` (modify - add docstrings)
- `backend/app/services/mcp_server_registry.py` (modify - add docstrings)

**AI Prompt:** `Implement Step 4.1 of EP-0002: Add comprehensive docstrings and inline documentation for all agent-related classes, methods, and key implementation details.`

**Tasks:**
- [ ] Add comprehensive docstrings to BaseAgent abstract class
- [ ] Document KubernetesAgent implementation and usage patterns
- [ ] Add docstrings to AlertOrchestrator delegation logic
- [ ] Document registry classes and their configuration patterns
- [ ] Include usage examples in docstrings
- [ ] Add inline comments for key implementation sections

**Dependencies:**
- Phase 3 completion

**Validation Criteria:**
- [ ] All public methods have comprehensive docstrings
- [ ] Class documentation includes usage patterns and examples
- [ ] Abstract method requirements are clearly documented
- [ ] Configuration patterns are well documented

**Success Check:**
```bash
# Commands to verify this step
cd backend
python -c "from tarsy.agents.base_agent import BaseAgent; help(BaseAgent)" | head -20
python -c "import pydoc; pydoc.help('tarsy.agents.kubernetes_agent')" | head -20
```

**Rollback Plan:**
- Documentation is non-breaking, no rollback needed

#### Step 4.2: Update Main Documentation
**Goal:** Update project documentation to reflect multi-layer architecture

**Files to Create/Modify:**
- `docs/design.md` (modify)
- `README.md` (modify)

**AI Prompt:** `Implement Step 4.2 of EP-0002: Update main project documentation to reflect the new multi-layer agent architecture, including configuration examples and usage patterns.`

**Tasks:**
- [ ] Update system architecture section in docs/design.md
- [ ] Update README.md with new architecture overview
- [ ] Add configuration documentation for agent registry and MCP server registry
- [ ] Include examples of adding new agents
- [ ] Document error handling and troubleshooting

**Dependencies:**
- Step 4.1 must be complete

**Validation Criteria:**
- [ ] Documentation accurately reflects implemented architecture
- [ ] Configuration examples are complete and correct
- [ ] Usage patterns are clearly explained
- [ ] Troubleshooting guidance is provided

**Success Check:**
```bash
# Commands to verify this step
grep -q "multi-layer agent architecture" docs/design.md
grep -q "AlertOrchestrator" README.md
```

**Rollback Plan:**
- Revert documentation changes if inconsistencies found

#### Step 4.3: Final Validation and Deployment Preparation
**Goal:** Complete final validation and prepare for deployment

**Files to Create/Modify:**
- `docs/enhancements/implemented/EP-0002-requirements.md` (move)
- `docs/enhancements/implemented/EP-0002-design.md` (move)
- `docs/enhancements/implemented/EP-0002-implementation.md` (move)

**AI Prompt:** `Implement Step 4.3 of EP-0002: Complete final validation of all implementation components and prepare for deployment by running comprehensive test suite.`

**Tasks:**
- [ ] Run complete test suite with all unit and integration tests
- [ ] Validate configuration examples and documentation
- [ ] Perform final end-to-end processing validation
- [ ] Verify API endpoint compatibility with completely new internal implementation
- [ ] Move EP documents to implemented directory
- [ ] Update enhancement registry and status

**Dependencies:**
- Step 4.2 must be complete

**Validation Criteria:**
- [ ] All tests pass successfully
- [ ] Documentation is accurate and complete
- [ ] Configuration examples work correctly
- [ ] End-to-end processing validates successfully
- [ ] API endpoint compatibility confirmed (same interface, completely new implementation)

**Success Check:**
```bash
# Commands to verify this step
cd backend
pytest tests/ -v --tb=short
python -c "from tarsy.services.alert_orchestrator import AlertOrchestrator; from tarsy.agents.kubernetes_agent import KubernetesAgent; print('All components importable')"
```

**Rollback Plan:**
- Address any final validation issues before marking complete

### Phase 4 Completion Criteria
- [ ] All code has comprehensive documentation
- [ ] Main project documentation reflects new architecture
- [ ] Final validation confirms all functionality works correctly
- [ ] EP documents are moved to implemented directory

## Testing Strategy

### Test Plans
The testing strategy follows the design document's approach of using **mock services only** for all tests, ensuring fast execution, predictable results, and comprehensive coverage without external dependencies.

### Mock Service Strategy
All tests use mocked external services as defined in the design document:

```python
# Mock Dependencies for Unit Tests
class MockLLMClient:
    def process_with_tools(self, instructions, tools): 
        return "Mock analysis result"

class MockMCPClient:
    def list_tools(self): 
        return ["kubectl", "helm"]
    def call_tool(self, tool, args): 
        return "Mock tool output"

class MockGitHubClient:
    def download_runbook(self, alert_type): 
        return "# Mock runbook content"

class MockProgressCallback:
    def __call__(self, status): 
        self.last_status = status

# Integration Test Fixture
@pytest.fixture
def integration_test_services():
    """Provides fully mocked external services for integration tests"""
    return {
        'github_client': MockGitHubClient(),
        'llm_client': MockLLMClient(), 
        'mcp_client': MockMCPClient(),
        'progress_callback': MockProgressCallback(),
        'websocket_manager': MockWebSocketManager()
    }
```

### Test Execution
Tests are executed at each phase using mocks only to ensure incremental validation and early detection of integration issues.

#### Unit Tests (Mock Services Only)
- [ ] BaseAgent abstract class functionality and abstract method enforcement
- [ ] KubernetesAgent inheritance and method implementations (including empty custom_instructions())
- [ ] AgentRegistry alert type to agent class mapping logic
- [ ] AgentFactory class resolution and dependency injection
- [ ] AlertOrchestrator delegation and error handling logic
- [ ] MCPServerRegistry configuration loading and server subset retrieval with embedded instructions
- [ ] Three-tier instruction composition logic in BaseAgent (general + MCP server + custom)

#### Integration Tests (Mock Services Only)
- [ ] Agent lifecycle from registry lookup to factory instantiation
- [ ] MCP server registry integration with agent MCP server subsets including instruction retrieval
- [ ] Configuration system integration with all registries and instruction management
- [ ] Three-tier instruction composition integration (BaseAgent + MCP registry + agent custom)
- [ ] AlertOrchestrator to agent delegation with progress callbacks
- [ ] WebSocket manager integration with agent-specific progress updates
- [ ] Error propagation across component boundaries
- [ ] Agent-specific MCP server subset assignment and instruction composition validation

Example integration test approach:
```python
@pytest.mark.integration 
async def test_kubernetes_alert_full_flow(integration_test_services):
    """Test complete flow: Alert → KubernetesAgent → Result"""
    services = integration_test_services
    services['llm_client'].set_response("Namespace finalizers removed")
    
    orchestrator = AlertOrchestrator(services)
    alert = Alert(type="NamespaceTerminating")
    result = await orchestrator.process_alert(alert)
    
    assert result.status == "completed"
    assert result.agent_used == "KubernetesAgent"
    assert services['progress_callback'].was_called()

@pytest.mark.integration
async def test_instruction_composition_integration(integration_test_services):
    """Test that KubernetesAgent composes instructions correctly from multiple sources"""
    # Setup mock MCP registry with Kubernetes server instructions
    mock_registry = MockMCPServerRegistry()
    mock_registry.add_server_config(MCPServerConfig(
        server_id="kubernetes-server",
        server_type="kubernetes", 
        instructions="For Kubernetes operations: be careful with cluster-scoped listings..."
    ))
    
    # Create KubernetesAgent with registry
    kubernetes_agent = KubernetesAgent(
        llm_client=integration_test_services['llm_client'],
        mcp_client=integration_test_services['mcp_client'],
        progress_callback=integration_test_services['progress_callback'],
        mcp_registry=mock_registry
    )
    
    # Verify instruction composition
    composed_instructions = kubernetes_agent._compose_instructions()
    
    # Should contain all three tiers
    assert "General SRE Agent Instructions" in composed_instructions  # General
    assert "For Kubernetes operations:" in composed_instructions      # MCP server
    # Custom instructions should be empty for KubernetesAgent initially
    assert "Agent-Specific Instructions" not in composed_instructions
```

#### End-to-End Tests (Mock Services Only)
- [ ] Complete alert processing flow from API endpoint to agent result
- [ ] WebSocket progress updates throughout entire processing lifecycle
- [ ] Error scenarios with appropriate error message propagation
- [ ] Agent-specific MCP server usage validation in processing (kubernetes-server only for KubernetesAgent)
- [ ] Three-tier instruction composition in end-to-end processing (general + MCP server + custom)
- [ ] Unknown alert type error handling with clear user feedback

## Resource Requirements

### Technical Resources
- **Development Environment**: Existing Python/FastAPI development stack
- **Testing Environment**: Current test infrastructure with expanded test coverage
- **Documentation Tools**: Existing documentation workflow and tools

### External Dependencies
- No new external dependencies required
- Existing LLM provider, MCP server, and GitHub integrations must remain stable

## Timeline & Milestones

### Overall Timeline
- **Phase 1**: Foundation & Core Architecture
- **Phase 2**: Specialized Agent Implementation  
- **Phase 3**: Orchestrator Implementation
- **Phase 4**: Documentation & Finalization

### Key Milestones
- [ ] **Phase 1 Complete**: Foundation architecture established
- [ ] **Phase 2 Complete**: KubernetesAgent and configuration ready
- [ ] **Phase 3 Complete**: Full orchestration and API integration working
- [ ] **Phase 4 Complete**: Documentation complete and deployment ready

### Critical Path
BaseAgent Implementation → KubernetesAgent Creation → AlertOrchestrator Development → FastAPI Integration → End-to-End Validation

## Documentation Updates Required

### Main Documentation Updates

#### design.md Updates
- [ ] **Section 1.1**: Update system architecture diagram with agent layers
- [ ] **Section 2.3**: Add agent component specifications and interactions
- [ ] **Section 3.1**: Update data flow diagrams to include agent delegation
- [ ] **New Section**: Agent inheritance patterns and specialization approach

#### Other Documentation
- [ ] **README.md**: Update with multi-layer architecture overview and examples
- [ ] **API Documentation**: Add agent-specific fields to processing status responses

## Success Metrics

### Success Metrics
- **Processing Quality**: Kubernetes agent achieves same analysis quality as current system
- **Usability**: Clear error messages for all failure scenarios

---

## Implementation Checklist

### Pre-Implementation
- [ ] Requirements document approved
- [ ] Design document approved  
- [ ] Implementation plan approved
- [ ] Development environment ready
- [ ] Test framework prepared

### During Implementation
- [ ] Follow step-by-step process with validation at each step
- [ ] Run tests after each major component implementation
- [ ] Update progress regularly with checklist completion
- [ ] Escalate issues promptly if validation fails
- [ ] Document decisions and implementation notes

### Post-Implementation
- [ ] All unit, integration, and end-to-end tests passing
- [ ] Documentation updated and reviewed
- [ ] Success metrics achieved and validated
- [ ] Code review completed and approved
- [ ] Implementation marked complete in enhancement registry

---

## AI Implementation Guide

### Step-by-Step Execution
1. **Implement each step individually** using the specific AI prompt provided
2. **Validate each step** using the success check commands before proceeding  
3. **Run tests continuously** to catch integration issues early
4. **Update progress** by checking off completed tasks and validation criteria
5. **Escalate issues** if validation fails or rollback plans need to be executed

### Troubleshooting
- If a step fails validation, execute the rollback plan immediately
- Review dependencies and ensure they are correctly implemented
- Check for configuration issues or missing imports
- Update timeline if delays occur due to unexpected issues

---

## Completion Criteria

### Final Success Criteria
- [ ] All requirements from requirements document are implemented and validated
- [ ] All design elements from design document are correctly implemented
- [ ] Kubernetes agent processes namespace alerts with identical quality to current system
- [ ] All existing API endpoints continue working without modification (same interface, completely new implementation)
- [ ] **CRITICAL**: AlertService has been completely replaced by AlertOrchestrator - no legacy AlertService code remains
- [ ] Agent delegation overhead is minimal and meets performance requirements  
- [ ] Three-tier instruction composition works correctly (General + MCP Server + Custom instructions)
- [ ] MCP Server Registry serves as single source of truth for all server configurations and instructions
- [ ] **CRITICAL**: No MCP server configuration duplication - existing mcp_servers and get_mcp_config() completely removed from settings.py
- [ ] Agent Registry and MCP Registry are implemented as simple static maps loaded once at startup with no runtime modifications
- [ ] KubernetesAgent uses only kubernetes-server subset and composes instructions correctly
- [ ] Error handling provides clear messages for all failure scenarios
- [ ] Documentation is comprehensive and accurate

### Implementation Complete
When all phases are complete and all success criteria are met, this EP implementation is considered complete and can be moved to the implemented directory.

**Final AI Prompt:**
```
Review EP-0002 implementation completion by running final validation tests, confirming all success criteria are met, and moving all three documents (requirements, design, implementation) to the implemented directory.
``` 