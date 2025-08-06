# EP-0008-1: Sequential Agent Chains - Requirements Document

**Status:** Draft  
**Created:** 2025-08-05  

---

## Problem Statement

**Current Issue:** The current agent system processes alerts using a single specialized agent from start to finish. While this works well for straightforward alerts, there are scenarios where multiple agents working in sequence could provide better analysis through specialized processing stages.

**Impact:** 
- **Limited Specialization**: Single agents must handle data collection, analysis, and response planning simultaneously
- **Missed Opportunities**: No ability to build complex workflows where early agents enrich data for later specialized analysis
- **Reduced Reusability**: Agents cannot be composed into different workflows for different alert types
- **Scalability Concerns**: Complex alert types require increasingly complex single agents rather than composed specialized agents

## Solution Requirements

### Functional Requirements

**Core Functionality:**
- [ ] **REQ-1**: System shall support sequential agent chains for alert processing (single agents are treated as 1-stage chains)
- [ ] **REQ-2**: Agent chains shall be defined using both approaches: built-in chains (defined in code like built-in agents) and configurable chains (defined in YAML configuration)
- [ ] **REQ-3**: Individual agents shall be reusable across multiple different chains (both built-in and configurable)
- [ ] **REQ-4**: Data enrichment shall flow sequentially from earlier agents to later agents in the chain
- [ ] **REQ-5**: Each stage in a sequential chain shall execute one agent and wait for completion before proceeding

**User Interface Requirements:**
- [ ] **REQ-6**: Dashboard shall display progress for each individual agent stage within chain execution
- [ ] **REQ-7**: Historical chain executions shall show stage-by-stage results and timing in alert history
- [ ] **REQ-8**: Chain execution errors shall be displayed with clear indication of which stage failed

**Configuration Requirements:**
- [ ] **REQ-9**: Built-in chains shall be defined in `builtin_config.py` following the same pattern as built-in agents
- [ ] **REQ-10**: Configurable chains shall be defined in YAML configuration with optimized structure including dedicated `agent_chains` section
- [ ] **REQ-11**: Chain configurations shall support mixing built-in and configurable agents within the same chain
- [ ] **REQ-12**: YAML configuration format may be enhanced/modified for better chain support without backward compatibility constraints

**Integration Requirements:**
- [ ] **REQ-13**: Chain orchestration shall integrate with existing WebSocket progress reporting system
- [ ] **REQ-14**: Chain results shall be stored in existing history service with stage-level detail
- [ ] **REQ-15**: API endpoints shall remain unchanged - chains shall be transparent to external users

### Non-Functional Requirements

**Performance Requirements:**
- [ ] **REQ-16**: Sequential chain execution shall provide reasonable user experience without excessive delays
- [ ] **REQ-17**: Chain lookup and orchestration overhead shall be minimal compared to individual agent execution time
- [ ] **REQ-18**: Memory usage shall scale linearly with chain length without significant overhead per stage

**Security Requirements:**
- [ ] **REQ-19**: Agent chains shall respect existing data masking configuration for each agent in the chain
- [ ] **REQ-20**: MCP server access shall be enforced per-agent within chains as configured
- [ ] **REQ-21**: Chain configuration shall be validated at startup to prevent security misconfigurations

**Reliability Requirements:**
- [ ] **REQ-22**: System shall maintain backward compatibility with existing single-agent processing
- [ ] **REQ-23**: Chain execution failures shall not crash the system and shall provide clear error reporting
- [ ] **REQ-24**: Partial chain execution results shall be preserved in history even when later stages fail

## Success Criteria

### Primary Success Criteria
- [ ] Successfully process alerts using multi-agent sequential chains with data enrichment between stages
- [ ] Demonstrate agent reusability by using the same agent in multiple different chain configurations
- [ ] Maintain 100% backward compatibility with existing single-agent alert processing

### Secondary Success Criteria  
- [ ] Chain configuration can be added/modified without code changes
- [ ] Stage-by-stage progress reporting provides clear visibility into chain execution
- [ ] Error handling and recovery works correctly when individual stages fail

## Constraints and Limitations

### Technical Constraints
- Must build on existing BaseAgent architecture without breaking changes
- Must integrate with existing MCP Client, History Service, and WebSocket systems
- Must follow existing dual configuration pattern (built-in + YAML) for consistency with agent architecture
- YAML configuration format may be optimized for chain support (no backward compatibility constraints for config format)

### Compatibility Requirements
- Existing API endpoints and response formats must remain the same
- Current dashboard functionality must continue to work for single-agent processing
- Configuration format may be enhanced for chain support (current format can be updated as needed)

### Dependencies
- **Internal**: BaseAgent class, AgentRegistry, ConfigurationLoader, builtin_config.py, History Service, WebSocket Manager, Dashboard UI
- **External**: No new external dependencies - use existing MCP servers and LLM integrations

## Out of Scope

- Parallel execution within stages (reserved for EP-0008-2)
- Conditional routing or branching workflows (reserved for EP-0008-3)
- New MCP servers or LLM integrations beyond existing capabilities
- Major UI redesign beyond adding chain stage visibility
- Performance optimization beyond maintaining reasonable user experience

---

## AI Notes

### Key Information for Design Phase
- **Primary Focus**: Extending AgentRegistry and creating ChainOrchestrator for sequential execution
- **Architecture Impact**: Medium - adds new orchestration layer but preserves existing agent architecture
- **Integration Complexity**: Moderate - must integrate with WebSocket, History, and Dashboard systems
- **Performance Criticality**: Important but not critical - users expect reasonable response times but not real-time performance

When creating the design document, ensure all requirements above are addressed with specific technical solutions for:
1. Built-in chain definitions in `builtin_config.py` (following existing agent pattern)
2. Optimized YAML chain configuration structure with dedicated `agent_chains` section (format can be enhanced as needed)
3. ChainRegistry service for both built-in and configurable chain lookups
4. ChainOrchestrator service architecture and data flow supporting flexible chain lengths
5. AgentRegistry integration with chain-based agent resolution
6. Integration points with existing progress reporting and history systems
7. Configuration format optimization for better chain usability and clarity