# EP-0015: MCP Server Tool Call Result Summarization

## Implementation Status 🚧

**✅ COMPLETE: Phase 1** - Prompt System Integration  
**✅ COMPLETE: Phase 2** - Foundation Components
**✅ COMPLETE: Phase 3** - MCP Client Integration  
**✅ COMPLETE: Phase 4** - Agent Integration  
**✅ COMPLETE: Phase 5** - Configuration and Testing  
**✅ COMPLETE: Phase 6** - Dashboard Integration  

## Problem Statement

Large MCP Server tool call results cause system bottlenecks in the **conversation flow**:

1. **Context Window Bloat**: Large observations consume excessive LLM context tokens in ReAct conversations
2. **Conversation History Growth**: Massive observations accumulate in `LLMInteraction.conversation` records
3. **Multi-Stage Accumulation**: In sequential agent chains, large results compound across stages via `StageContext.final_mcp_data`

**Note**: Full MCP results are **already saved to database** immediately via the hook system (`MCPInteraction.tool_result`). Summarization addresses conversation flow efficiency, not database storage.

**Current Flow**:
```
MCP Tool Result → [Hook System: Full Result to DB] → format_observation() → f"Observation: {huge_result}" → LLM Context
```

## Solution Overview

Implement **agent-provided summarization** of large MCP results after data masking but before database storage:

1. **Dependency Inversion**: Agent passes summarizer interface to MCP Client  
2. **Security-First**: Data masking applied before summarization to protect sensitive data
3. **Pre-Storage Summarization**: MCP Client calls summarizer for large masked results before hooks save to database
4. **Context-Aware**: Summarizer has access to investigation conversation and agent's LLM client
5. **Provider-Level Token Control**: Uses LangChain's native `max_tokens` parameter for guaranteed length limits
6. **Clean Architecture**: MCP Client remains LLM-agnostic

**Target Flow**:
```
Agent → [Pass Summarizer] → MCP Client → [Tool Execution] → [Data Masking] → [Size Check] → [Agent Summarizer + max_tokens] → [Hook System: Summary to DB] → format_observation() → Condensed Observation → LLM Context
```

## Key Implementation Points

### **1. Size Detection & Token Control Strategy**
- **Token-based threshold**: Estimate tokens in MCP result using tiktoken with model-specific encoding
- **Provider-level enforcement**: Use LangChain's native `max_tokens` parameter for guaranteed length control
- **Context window awareness**: Trigger based on actual LLM context consumption
- **Server-specific configuration**: Different thresholds per MCP server based on output characteristics

### **2. Backward Compatibility**
- **Transparent Change**: No impact on existing ReAct flow or database schemas
- **Observation Format**: Maintain `f"{server}.{tool}: {result}"` structure
- **Optional Feature**: Agents without summarizer work unchanged

### **3. Summarization LLM Interaction Storage**
- **Use LLMClient**: Summarizer must use `LLMClient.generate_response()` for proper hook integration
- **Session Context**: Summarization interactions linked to same `session_id` and `stage_execution_id` as the MCP interaction
- **Interaction Type**: Add metadata to distinguish summarization interactions from regular agent reasoning
- **Complete Audit Trail**: Full conversation history includes both MCP tool calls and their summarization interactions
- **Timeline Visibility**: Dashboard will show both MCP interaction and subsequent summarization LLM interaction in stage timeline

### **4. Error Handling**
- **Graceful Degradation**: If summarization fails, store the error as the result
- **Logging**: Track summarization attempts and failures for monitoring

### **5. Configuration Design**

```yaml
# In agent configuration - per MCP server settings
mcp_servers:
  kubectl:
    # ... existing server config ...
    summarization:
      enabled: true                    # true by default
      size_threshold_tokens: 2000      # 2K by default  
      summary_max_token_limit: 1000    # 1K by default
  
  postgres:
    # ... existing server config ...
    summarization:
      enabled: true
      size_threshold_tokens: 3000      # Database output can be large
      summary_max_token_limit: 800
      
  filesystem:
    # ... existing server config ...
    summarization:
      enabled: false                   # Disable for file operations
```

## Detailed Implementation

### **1. MCP Result Summarizer**

**Location**: `backend/tarsy/integrations/mcp/summarizer.py` (new file)

```python
import json
from typing import Dict, Any, Optional, TYPE_CHECKING
from tarsy.integrations.llm.client import LLMClient
from tarsy.models.unified_interactions import LLMConversation, MessageRole
from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.models.processing_context import StageContext

logger = get_module_logger(__name__)

class MCPResultSummarizer:
    """Agent-provided MCP result summarizer using LLM client with stage context awareness."""
    
    def __init__(self, llm_client: LLMClient, prompt_builder: PromptBuilder):
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    async def summarize_result(
        self,
        server_name: str,
        tool_name: str,
        result: Dict[str, Any],
        investigation_conversation: LLMConversation,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_summary_tokens: int = 1000
    ) -> Dict[str, Any]:
        """
        Summarize a large MCP tool result using LLM with investigation conversation context.
        
        Uses LangChain's max_tokens parameter to enforce token limits at the provider level,
        ensuring reliable summarization length control beyond prompt suggestions.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool that produced the result
            result: The original tool result dictionary
            investigation_conversation: The ongoing ReAct conversation for context
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID
            max_summary_tokens: Maximum tokens enforced at LLM provider level via max_tokens
            
        Returns:
            Summarized result dictionary with same structure as original
        """
        try:
            # Extract the actual result content
            result_content = result.get("result", str(result))
            if isinstance(result_content, dict):
                result_text = json.dumps(result_content, indent=2, default=str)
            else:
                result_text = str(result_content)
            
            # Use prompt builder to create summarization prompts
            system_prompt = self.prompt_builder.build_mcp_summarization_system_prompt(
                server_name, tool_name, max_summary_tokens
            )
            system_message = LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)
            
            # Serialize conversation context and build user prompt
            conversation_context = self._serialize_conversation_context(investigation_conversation)
            user_prompt = self.prompt_builder.build_mcp_summarization_user_prompt(
                conversation_context, server_name, tool_name, result_text
            )
            user_message = LLMMessage(role=MessageRole.USER, content=user_prompt)
            
            # Create conversation with both messages (required to start with system message)
            summarization_conversation = LLMConversation(messages=[system_message, user_message])
            
            # Generate summary using LLM client with max_tokens limit (ensures proper hook integration)
            llm_config = {"max_tokens": max_summary_tokens}
            response_conversation = await self.llm_client.generate_response(
                summarization_conversation, session_id, stage_execution_id, llm_config
            )
            
            # Extract summary from response
            assistant_message = response_conversation.get_latest_assistant_message()
            if not assistant_message:
                raise Exception("No response from LLM for summarization")
            
            summary_text = assistant_message.content.strip()
            
            # Return summarized result in same structure as original
            summarized_result = result.copy()
            summarized_result["result"] = summary_text
            
            logger.debug(f"Successfully summarized {server_name}.{tool_name} result with investigation context")
            return summarized_result
            
        except Exception as e:
            logger.error(f"Failed to summarize {server_name}.{tool_name} result: {e}")
            raise
    
    # Helper methods for conversation processing

    def _serialize_conversation_context(self, conversation: LLMConversation) -> str:
        """Serialize LLMConversation into readable context for summarization."""
        context_lines = []
        
        for message in conversation.messages:
            role = message.role.value.upper()
            content = message.content
            
            # Special handling for system messages - extract valuable domain knowledge
            if message.role == MessageRole.SYSTEM:
                content = self._extract_domain_knowledge_from_system_message(content)
            
            # Truncate very long messages to keep context manageable
            if len(content) > 10000:
                content = content[:10000] + "... [truncated]"
            
            context_lines.append(f"{role}: {content}")
        
        return "\n\n".join(context_lines)
    
    def _extract_domain_knowledge_from_system_message(self, system_content: str) -> str:
        """Extract valuable domain knowledge from ReAct system message, filtering out procedural noise."""
        # Import the constant to filter out ReAct formatting instructions
        from tarsy.agents.prompts.templates import REACT_FORMATTING_INSTRUCTIONS
        
        # Remove the ReAct formatting instructions to keep only domain knowledge
        if REACT_FORMATTING_INSTRUCTIONS in system_content:
            domain_content = system_content.split(REACT_FORMATTING_INSTRUCTIONS)[0].strip()
        else:
            # Fallback: take first reasonable chunk if pattern not found
            domain_content = system_content[:1000] + "... [domain knowledge extracted]"
        
        return domain_content
```

### **2. Prompt Template Updates**

**Location**: `backend/tarsy/agents/prompts/templates.py`

**Split REACT_SYSTEM_TEMPLATE for clean domain knowledge extraction**:
```python
# ReAct formatting instructions constant
REACT_FORMATTING_INSTRUCTIONS = """
🚨 WARNING: NEVER GENERATE FAKE OBSERVATIONS! 🚨
After writing "Action Input:", you MUST stop immediately. The system will provide the "Observation:" for you.
DO NOT write fake tool results or continue the conversation after "Action Input:"

🔥 CRITICAL COLON FORMATTING RULE 🔥
EVERY ReAct section header MUST END WITH A COLON (:)

✅ CORRECT: "Thought:" (with colon)
❌ INCORRECT: "Thought" (missing colon)

You MUST write:
- "Thought:" (NOT "Thought")  
- "Action:" (NOT "Action")
- "Action Input:" (NOT "Action Input")

CRITICAL REACT FORMATTING RULES:
Follow the ReAct pattern exactly. You must use this structure:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take (choose from available tools)
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now have sufficient information to provide my analysis
Final Answer: [Complete SRE analysis in structured format - see below]

RESPONSE OPTIONS:
At each step, you have exactly TWO options:

1. Continue investigating: 
   Thought: [your reasoning about what to investigate next]
   Action: [tool to use]
   Action Input: [parameters]

2. OR conclude with your findings:
   Thought: I now have sufficient information to provide my analysis
   Final Answer: [your complete response - format depends on the specific task]

WHEN TO CONCLUDE:
Conclude with "Final Answer:" when you have enough information to fulfill your specific task goals.
You do NOT need perfect information - focus on actionable insights from the data you've collected.

CRITICAL FORMATTING REQUIREMENTS:
1. ALWAYS include colons after section headers: "Thought:", "Action:", "Action Input:"
2. Each section must start on a NEW LINE - never continue on the same line
3. Always add a blank line after "Action Input:" before stopping
4. For Action Input, provide ONLY parameter values (no YAML, no code blocks, no triple backticks)

⚠️ ABSOLUTELY CRITICAL: STOP AFTER "Action Input:" ⚠️
5. STOP immediately after "Action Input:" line - do NOT generate "Observation:"
6. NEVER write fake observations or continue the conversation
7. The system will provide the real "Observation:" - you must NOT generate it yourself
8. After the system provides the observation, then continue with "Thought:" or "Final Answer:"

VIOLATION EXAMPLES (DO NOT DO THIS):
❌ Action Input: apiVersion=v1, kind=Secret, name=my-secret
❌ Observation: kubernetes-server.resources_get: {{"result": "..."}} 
❌ Thought: I have retrieved the data...

CORRECT BEHAVIOR:
✅ Action Input: apiVersion=v1, kind=Secret, name=my-secret
✅ [STOP HERE - SYSTEM WILL PROVIDE OBSERVATION]

NEWLINE FORMATTING IS CRITICAL:
- WRONG: "Thought: I need to check the namespace status first.Action: kubernetes-server.resources_get"
- CORRECT: 
Thought: I need to check the namespace status first.

Action: kubernetes-server.resources_get
Action Input: apiVersion=v1, kind=Namespace, name=superman-dev

EXAMPLE OF CORRECT INVESTIGATION:
Thought: I need to check the namespace status first. This will give me details about why the namespace is stuck in terminating state.

Action: kubernetes-server.resources_get
Action Input: apiVersion=v1, kind=Namespace, name=superman-dev

EXAMPLE OF CONCLUDING PROPERLY:
Thought: I have gathered sufficient information to complete my task. Based on my investigation, I can now provide the requested analysis.

Final Answer: [Provide your complete response in the format appropriate for your specific task - this could be structured analysis, data summary, or stage-specific findings depending on what was requested]

CRITICAL VIOLATIONS TO AVOID:
❌ GENERATING FAKE OBSERVATIONS: Never write "Observation:" yourself - the system provides it
❌ CONTINUING AFTER ACTION INPUT: Stop immediately after "Action Input:" - don't add more content
❌ HALLUCINATING TOOL RESULTS: Don't make up API responses or tool outputs
🚨 ❌ MISSING COLONS: Writing "Thought" instead of "Thought:" - THIS IS THE #1 FORMATTING ERROR
❌ Action Input with ```yaml or code blocks  
❌ Running sections together on the same line without proper newlines
❌ Providing analysis in non-ReAct format (you MUST use "Final Answer:" to conclude)
❌ Abandoning ReAct format and providing direct structured responses

🔥 COLON EXAMPLES - MEMORIZE THESE:
❌ WRONG: "Thought\nThe user wants me to investigate..."
❌ WRONG: "Action\nkubernetes-server.resources_get"
✅ CORRECT: "Thought:\nThe user wants me to investigate..."
✅ CORRECT: "Action:\nkubernetes-server.resources_get"

THE #1 MISTAKE: Writing fake observations and continuing the conversation after Action Input"""

# Updated ReAct System Message Template  
REACT_SYSTEM_TEMPLATE = PromptTemplate.from_template("""{composed_instructions}

{react_formatting_instructions}

Focus on {task_focus} for human operators to execute.""")
```

**Add new summarization templates to templates.py**:
```python
# MCP Result Summarization Templates
MCP_SUMMARIZATION_SYSTEM_TEMPLATE = PromptTemplate.from_template("""You are an expert at summarizing technical output from system administration and monitoring tools for ongoing incident investigation.

Your specific task is to summarize output from **{server_name}.{tool_name}** in a way that:

1. **Preserves Critical Information**: Keep all details essential for troubleshooting and investigation
2. **Maintains Investigation Context**: Focus on information relevant to what the investigator was looking for
3. **Reduces Verbosity**: Remove redundant details while preserving technical accuracy  
4. **Highlights Key Findings**: Emphasize errors, warnings, unusual patterns, and actionable insights
5. **Stays Concise**: Keep summary under {max_summary_tokens} tokens while preserving meaning

## Summarization Guidelines:

- **Always Preserve**: Error messages, warnings, status indicators, resource metrics, timestamps
- **Intelligently Summarize**: Large lists by showing patterns, counts, and notable exceptions
- **Focus On**: Non-default configurations, problematic settings, resource utilization issues
- **Maintain**: Technical accuracy and context about what the data represents
- **Format**: Clean, structured text suitable for continued technical investigation

Your summary will be inserted as an observation in the ongoing investigation conversation.""")

MCP_SUMMARIZATION_USER_TEMPLATE = PromptTemplate.from_template("""Below is the ongoing investigation conversation that provides context for what the investigator has been looking for and thinking about:

## Investigation Context:
=== CONVERSATION START ===
{conversation_context}
=== CONVERSATION END ===

## Tool Result to Summarize:
The investigator just executed `{server_name}.{tool_name}` and got the following output:

=== TOOL OUTPUT START ===
{result_text}
=== TOOL OUTPUT END ===

## Your Task:
Based on the investigation context above, provide a concise summary of the tool result that:
- Preserves information most relevant to what the investigator was looking for
- Removes verbose or redundant details that don't impact the investigation
- Maintains technical accuracy and actionable insights
- Fits naturally as the next "Observation:" in the investigation conversation

The summary will be used as an observation in the ongoing ReAct investigation process.""")
```

**Update PromptBuilder with summarization methods** (`backend/tarsy/agents/prompts/builders.py`):
```python
def get_enhanced_react_system_message(self, composed_instructions: str, task_focus: str = "investigation and providing recommendations") -> str:
    """Get enhanced ReAct system message using template. Used by ReAct iteration controllers."""
    return REACT_SYSTEM_TEMPLATE.format(
        composed_instructions=composed_instructions,
        react_formatting_instructions=REACT_FORMATTING_INSTRUCTIONS,  # Use the constant
        task_focus=task_focus
    )

def build_mcp_summarization_system_prompt(self, server_name: str, tool_name: str, max_summary_tokens: int) -> str:
    """Build system prompt for MCP result summarization."""
    return MCP_SUMMARIZATION_SYSTEM_TEMPLATE.format(
        server_name=server_name,
        tool_name=tool_name,
        max_summary_tokens=max_summary_tokens
    )

def build_mcp_summarization_user_prompt(self, conversation_context: str, server_name: str, 
                                       tool_name: str, result_text: str) -> str:
    """Build user prompt for MCP result summarization with investigation context."""
    return MCP_SUMMARIZATION_USER_TEMPLATE.format(
        conversation_context=conversation_context,
        server_name=server_name,
        tool_name=tool_name,
        result_text=result_text
    )
```

### **3. Enhanced LLM Client for max_tokens Support**

**Location**: `backend/tarsy/integrations/llm/client.py` (enhanced existing file)

**Key Enhancement**: Added optional `max_tokens` parameter to enable provider-level token control:

```python
async def generate_response(
    self, 
    conversation: LLMConversation, 
    session_id: str, 
    stage_execution_id: Optional[str] = None,
    max_tokens: Optional[int] = None  # NEW: Optional max tokens configuration
) -> LLMConversation:
    """Enhanced with optional max_tokens configuration for provider-level token control."""
    
    # Enhanced _execute_with_retry method:
    # Build config with callbacks
    config = {"callbacks": [callback]}
    
    # Pass max_tokens as direct kwarg if provided
    if max_tokens is not None:
        response = await self.llm_client.ainvoke(
            langchain_messages,
            config=config,
            max_tokens=max_tokens  # Provider-level enforcement
        )
    else:
        response = await self.llm_client.ainvoke(
            langchain_messages,
            config=config
        )
```

**Benefits:**
- **Guaranteed Token Limits**: Provider enforces max_tokens, not just prompt suggestions
- **Universal Support**: Works with OpenAI, Anthropic, XAI, Google providers via LangChain
- **Cost Control**: Prevents excessive token generation and associated costs
- **Backward Compatibility**: Existing code unaffected (optional parameter)

### **4. Token Counting Utility**

**Location**: `backend/tarsy/utils/token_counter.py` (new file)

**Dependency**: Added `tiktoken>=0.7.0` to `backend/pyproject.toml` dependencies

```python
import tiktoken
from typing import Any, Dict
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

class TokenCounter:
    """Utility for estimating token counts in text data."""
    
    def __init__(self, model: str = "gpt-4o"):
        """Initialize with tiktoken encoding for the specified model."""
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to o200k_base encoding for unknown models
            self.encoding = tiktoken.get_encoding("o200k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text string."""
        return len(self.encoding.encode(text))
    
    def estimate_observation_tokens(self, server_name: str, tool_name: str, result: Dict[str, Any]) -> int:
        """Estimate tokens that would be used in ReAct observation."""
        # Simulate the format_observation output format
        if isinstance(result, dict) and 'result' in result:
            formatted_result = json.dumps(result['result'], indent=2) if isinstance(result['result'], dict) else str(result['result'])
        else:
            formatted_result = json.dumps(result, indent=2)
        
        observation_text = f"{server_name}.{tool_name}: {formatted_result}"
        return self.count_tokens(observation_text)
```

### **3. MCPClient Enhancement**

**Location**: `backend/tarsy/integrations/mcp/client.py`

**Add import at top of file**:
```python
from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
from tarsy.utils.token_counter import TokenCounter
from tarsy.agents.prompts.templates import MCP_SUMMARIZATION_SYSTEM_TEMPLATE, MCP_SUMMARIZATION_USER_TEMPLATE
from tarsy.utils.timestamp import now_us
```

**Changes to `__init__` method**:
```python
def __init__(self, settings: Settings, mcp_registry: Optional[MCPServerRegistry] = None, summarizer: Optional[MCPResultSummarizer] = None):
    # ... existing initialization ...
    self.summarizer = summarizer  # Optional agent-provided summarizer
    self.token_counter = TokenCounter()  # For size threshold detection
```

**New method for summarization logic**:
```python
async def _maybe_summarize_result(
    self, 
    server_name: str, 
    tool_name: str, 
    result: Dict[str, Any], 
    investigation_conversation: LLMConversation,
    session_id: str,
    stage_execution_id: Optional[str] = None
) -> Dict[str, Any]:
    """Apply summarization if result exceeds size threshold."""
    
    if not self.summarizer:
        return result
    
    # Get server-specific configuration
    server_config = self.mcp_registry.get_server_config_safe(server_name)
    if not server_config or not hasattr(server_config, 'summarization'):
        return result
    
    summarization_config = getattr(server_config, 'summarization', None)
    if not summarization_config or not getattr(summarization_config, 'enabled', True):
        return result
    
    # Check size threshold
    size_threshold = getattr(summarization_config, 'size_threshold_tokens', 2000)
    estimated_tokens = self.token_counter.estimate_observation_tokens(server_name, tool_name, result)
    
    if estimated_tokens <= size_threshold:
        return result
    
    try:
        # Get max summary tokens from server configuration
        max_summary_tokens = getattr(summarization_config, 'summary_max_token_limit', 1000)
        
        logger.info(f"Summarizing large MCP result: {server_name}.{tool_name} ({estimated_tokens} tokens)")
        summarized = await self.summarizer.summarize_result(
            server_name, tool_name, result, investigation_conversation, 
            session_id, stage_execution_id, max_summary_tokens
        )
        
        return summarized
        
    except Exception as e:
        logger.error(f"Failed to summarize MCP result {server_name}.{tool_name}: {e}")
        # Return error message as result for graceful degradation
        return {
            "result": f"Error: Failed to summarize large result ({estimated_tokens} tokens). Summarization error: {str(e)}"
        }
```

**Updated `call_tool` method signature** (needs investigation conversation):
```python
async def call_tool(self, server_name: str, tool_name: str, parameters: Dict[str, Any], 
                   session_id: str, stage_execution_id: Optional[str] = None,
                   investigation_conversation: Optional[LLMConversation] = None) -> Dict[str, Any]:
    """Call a specific tool on an MCP server with optional investigation context for summarization."""
    # ... existing validation logic ...
    
    # Use typed hook context for clean data flow
    async with mcp_interaction_context(session_id, server_name, tool_name, 
                                     parameters, stage_execution_id) as ctx:
        # ... existing tool call logic ...
        
        # Apply data masking FIRST - never send sensitive data to LLM
        # ... existing data masking logic ...
        
        # Apply summarization AFTER data masking (if investigation context available)
        if investigation_conversation:
            response_dict = await self._maybe_summarize_result(
                server_name, tool_name, response_dict, investigation_conversation, 
                session_id, stage_execution_id
            )
        
        # ... existing logging ...
```

### **4. Configuration Model Extensions**

**Location**: `backend/tarsy/models/agent_config.py`

**New summarization configuration model**:
```python
class SummarizationConfig(BaseModel):
    """Configuration for MCP result summarization."""
    
    enabled: bool = Field(
        default=True,
        description="Whether summarization is enabled for this server"
    )
    size_threshold_tokens: int = Field(
        default=2000,
        description="Token threshold above which results will be summarized",
        ge=100
    )
    summary_max_token_limit: int = Field(
        default=1000,
        description="Maximum tokens allowed in summary",
        ge=50
    )
```

**Update to `MCPServerConfigModel`**:
```python
class MCPServerConfigModel(BaseModel):
    # ... existing fields ...
    
    summarization: Optional[SummarizationConfig] = Field(
        default_factory=lambda: SummarizationConfig(),
        description="Summarization configuration for large results"
    )
```

### **5. BaseAgent Integration**

**Location**: `backend/tarsy/agents/base_agent.py`

**Add summarizer to agent initialization**:
```python
async def _configure_mcp_client(self):
    """Configure MCP client with agent-specific server subset and summarizer."""
    # ... existing server configuration logic ...
    
    # Create and inject summarizer if LLM client is available
    if hasattr(self, 'llm_client') and self.llm_client:
        summarizer = MCPResultSummarizer(self.llm_client, self._prompt_builder)
        # Update MCP client with summarizer
        self.mcp_client.summarizer = summarizer
    
    logger.info(f"Configured agent {self.__class__.__name__} with MCP servers: {mcp_server_ids}")
```

**Update `execute_mcp_tools` method to pass investigation context**:
```python
async def execute_mcp_tools(self, tools_to_call: List[Dict], session_id: str, 
                          investigation_conversation: Optional[LLMConversation] = None) -> Dict[str, List[Dict]]:
    """Execute MCP tools with optional investigation context for summarization."""
    results = {}
    
    for tool_call in tools_to_call:
        try:
            server_name = tool_call.get("server")
            tool_name = tool_call.get("tool")
            tool_params = tool_call.get("parameters", {})
            
            # Verify this server is allowed for this agent
            if self._configured_servers and server_name not in self._configured_servers:
                raise ValueError(f"Tool '{tool_name}' from server '{server_name}' not allowed for agent {self.__class__.__name__}")
            
            # Pass investigation conversation for context-aware summarization
            result = await self.mcp_client.call_tool(
                server_name, tool_name, tool_params, session_id, 
                self._current_stage_execution_id, investigation_conversation
            )
            
            # Organize results by server
            if server_name not in results:
                results[server_name] = []
            
            results[server_name].append({
                "tool": tool_name,
                "parameters": tool_params,
                "result": result,
                "timestamp": now_us()
            })
            
        except Exception as e:
            # ... existing error handling ...
```

### **6. AgentFactory Enhancement**

**Location**: `backend/tarsy/services/agent_factory.py`

**Update agent creation to pass summarizer**:
```python
def create_agent(self, agent_type: str, **kwargs) -> BaseAgent:
    # ... existing agent creation logic ...
    
    # All agents get the same LLM client, MCP client will get summarizer in _configure_mcp_client
    agent_instance = agent_class(
        llm_client=self.llm_client,
        mcp_client=self.mcp_client,  # MCP client will receive summarizer from agent
        mcp_registry=self.mcp_registry,
        **creation_kwargs
    )
```

### **7. Iteration Controller Updates**

**Location**: Update iteration controllers to pass StageContext to execute_mcp_tools

**Example update to ReactController** (`backend/tarsy/agents/iteration_controllers/base_controller.py`):
```python
# In execute_analysis_loop method, when executing tools:
# OLD: mcp_data = await agent.execute_mcp_tools([parsed_response.tool_call.model_dump()], context.session_id)
# NEW: mcp_data = await agent.execute_mcp_tools([parsed_response.tool_call.model_dump()], context.session_id, conversation)

# Where 'conversation' is the current LLMConversation being built in the ReAct loop
```

### **8. Error Handling Integration**

**Location**: Error handling is integrated throughout:

1. **Size Detection Errors**: If token counting fails, continue without summarization
2. **Summarization Failures**: Store error message as result and log the failure  
3. **Configuration Errors**: Fall back to no summarization if configuration is invalid
4. **LLM Unavailability**: Skip summarization if LLM client is unavailable
5. **Data Masking Failures**: If masking fails, continue without summarization for security
6. **Investigation Context Missing**: If conversation context is unavailable, fall back to basic summarization

### **9. Testing Structure**

**New test files needed**:
- `backend/tests/unit/utils/test_token_counter.py` - Test token counting accuracy and edge cases
- `backend/tests/unit/integrations/mcp/test_summarizer.py` - Test MCPResultSummarizer with mocked LLM and stage context
- `backend/tests/integration/test_mcp_summarization.py` - End-to-end summarization flow testing
- Update existing `test_mcp_client.py` with summarization scenarios and configuration tests

## Implementation Phases

### **Phase 1: Prompt System Integration**

**Deliverables:**
- Updated prompt templates
- Enhanced prompt builder methods
- Template structure reorganization

**Tasks:**
1. **Split ReAct System Template** (`backend/tarsy/agents/prompts/templates.py`)
   - Extract `REACT_FORMATTING_INSTRUCTIONS` constant
   - Refactor `REACT_SYSTEM_TEMPLATE` to use constant
   - Ensure clean domain knowledge separation

2. **Add Summarization Templates**
   - Implement `MCP_SUMMARIZATION_SYSTEM_TEMPLATE`
   - Implement `MCP_SUMMARIZATION_USER_TEMPLATE`
   - Focus on investigation context awareness

3. **Enhance PromptBuilder** (`backend/tarsy/agents/prompts/builders.py`)
   - Add `build_mcp_summarization_system_prompt()` method
   - Add `build_mcp_summarization_user_prompt()` method
   - Update existing ReAct system message method

**Verification:** Prompt templates render correctly with test data, prompt builder methods produce valid prompts.

### **Phase 2: Foundation Components**

**Deliverables:**
- Token counting utility with tiktoken integration
- MCP result summarizer core implementation with LLM max_tokens support
- Enhanced configuration models with validation
- Comprehensive unit tests for all components
- **ENHANCEMENT**: LLM Client max_tokens support for provider-level token control

**Tasks:**
1. **Create Token Counter Utility** (`backend/tarsy/utils/token_counter.py`)
   - Implement tiktoken integration for token estimation
   - Add observation format simulation
   - Handle encoding fallbacks for unknown models

2. **Implement MCP Result Summarizer** (`backend/tarsy/integrations/mcp/summarizer.py`)
   - Create `MCPResultSummarizer` class
   - Implement conversation context serialization
   - Add domain knowledge extraction from system messages
   - **Depends on**: Phase 1 prompt templates and builder methods

3. **Extend Configuration Models** (`backend/tarsy/models/agent_config.py`)
   - Add `SummarizationConfig` model
   - Update `MCPServerConfigModel` to include summarization settings
   - Validate configuration constraints

4. **Unit Testing**
   - Test token counting accuracy and edge cases
   - Mock LLM client for summarizer testing
   - Configuration validation tests

5. **Enhanced LLM Client Integration** (`backend/tarsy/integrations/llm/client.py`)
   - Add optional `llm_config` parameter to `generate_response()` method
   - Implement provider-level `max_tokens` enforcement via LangChain config
   - Maintain backward compatibility with existing method signatures
   - **Depends on**: Existing LLM client infrastructure

**Verification:** All new components have isolated unit tests and can be imported without errors. Enhanced LLM client provides provider-level token control for reliable summarization.

### **Phase 3: MCP Client Integration**

**Deliverables:**
- Enhanced MCP client with summarization capabilities
- Size threshold detection
- Error handling and graceful degradation

**Tasks:**
1. **Update MCPClient Constructor** (`backend/tarsy/integrations/mcp/client.py`)
   - Add optional summarizer parameter
   - Initialize token counter
   - Import required summarization components

2. **Implement Summarization Logic**
   - Create `_maybe_summarize_result()` method
   - Add server-specific configuration reading
   - Implement size threshold checking

3. **Update `call_tool` Method**
   - Add optional `investigation_conversation` parameter
   - Integrate summarization after data masking
   - Maintain backward compatibility

4. **Error Handling**
   - Handle summarization failures gracefully
   - Add metadata about summarization process
   - Ensure full error logging

**Verification:** MCP client can handle large results with and without summarization, maintains backward compatibility.

### **Phase 4: Agent Integration**

**Deliverables:**
- BaseAgent summarizer injection
- Updated tool execution flow
- Agent factory enhancements

**Tasks:**
1. **Update BaseAgent** (`backend/tarsy/agents/base_agent.py`)
   - Modify `_configure_mcp_client()` to inject summarizer
   - Update `execute_mcp_tools()` to pass investigation conversation
   - Handle agent-specific summarization policies

2. **Enhance AgentFactory** (`backend/tarsy/services/agent_factory.py`)
   - Ensure agents receive MCP client with summarization capability
   - Maintain dependency injection patterns

3. **Update Iteration Controllers**
   - Modify ReAct controller to pass conversation context to MCP calls
   - Update other controllers as needed
   - Ensure conversation context flows properly

**Verification:** Agents can successfully use summarization, all existing agent functionality remains intact.

### **Phase 5: Configuration and Testing**

**Deliverables:**
- Configuration file examples
- Integration tests
- End-to-end testing
- Documentation updates

**Tasks:**
1. **Configuration Examples**
   - Update `config/agents.yaml.example` with summarization settings
   - Add server-specific configuration examples
   - Document configuration options

2. **Integration Testing** (`backend/tests/integration/test_mcp_summarization.py`)
   - Test full summarization flow
   - Test configuration loading
   - Test error scenarios

3. **E2E Testing** (`backend/tests/e2e/test_api_e2e.py`)
   - Extend existing test_api_e2e.py tests cover summarization
   - Test dashboard visibility of summarization interactions

4. **Existing Test Updates**
   - Update `test_mcp_client.py` with summarization scenarios
   - Update agent tests to handle new summarization flow
   - Update mock configurations

**Verification:** Full test suite passes, performance improvements are measurable, configuration examples work.

### **Phase 6: Dashboard Integration**

**Dashboard Integration**
 - Ensure summarization interactions appear in timeline

## Success Criteria

1. **Storage Efficiency**: Significant reduction in database storage and token usage for large MCP results
2. **Information Preservation**: Summarized results retain investigation-relevant details
3. **Performance Improvement**: Faster conversation processing and database operations
4. **Clean Architecture**: MCP Client remains LLM-agnostic, agents control summarization policy
5. **Complete Audit Trail**: All summarization LLM interactions properly stored and linked to their MCP interactions
6. **Transparent Operation**: No breaking changes to existing functionality
7. **🚀 ENHANCED: Provider-Level Token Control**: Guaranteed token limits via LangChain's native `max_tokens` parameter for precise cost and length control