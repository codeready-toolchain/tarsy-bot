"""
LangChain Tools wrapper for MCP client integration.
Converts MCP tools to LangChain Tools for seamless integration with LangChain agents.
"""

import json
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool
from pydantic.v1 import BaseModel as V1BaseModel

from app.integrations.mcp.mcp_client import MCPClient
from app.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class MCPToolInput(V1BaseModel):
    """Base input model for MCP tools."""
    pass


class MCPTool(BaseTool):
    """LangChain Tool wrapper for MCP tools."""
    
    name: str
    description: str
    args_schema: Optional[Type[V1BaseModel]] = MCPToolInput
    mcp_client: MCPClient = Field(exclude=True)
    server_name: str = Field(exclude=True)
    tool_name: str = Field(exclude=True)
    
    class Config:
        """Configuration for the tool."""
        arbitrary_types_allowed = True
    
    def __init__(self, mcp_client: MCPClient, server_name: str, tool_name: str, description: str, input_schema: Dict[str, Any]):
        # Create dynamic Pydantic model for the tool's input schema
        args_schema = self._create_pydantic_model(tool_name, input_schema)
        
        super().__init__(
            name=f"{server_name}_{tool_name}",
            description=description,
            args_schema=args_schema,
            mcp_client=mcp_client,
            server_name=server_name,
            tool_name=tool_name
        )
    
    def _create_pydantic_model(self, tool_name: str, input_schema: Dict[str, Any]) -> Type[V1BaseModel]:
        """Create a Pydantic model from JSON schema."""
        try:
            # Extract properties from the schema
            properties = input_schema.get("properties", {})
            required_fields = input_schema.get("required", [])
            
            # Create field definitions for the type annotation dictionary
            annotations = {}
            field_defaults = {}
            
            for field_name, field_info in properties.items():
                field_type = str  # Default to string
                field_description = field_info.get("description", "")
                
                # Map JSON schema types to Python types
                if field_info.get("type") == "string":
                    field_type = str
                elif field_info.get("type") == "integer":
                    field_type = int
                elif field_info.get("type") == "number":
                    field_type = float
                elif field_info.get("type") == "boolean":
                    field_type = bool
                elif field_info.get("type") == "array":
                    field_type = List[str]  # Simplify to list of strings
                elif field_info.get("type") == "object":
                    field_type = Dict[str, Any]
                
                # Set type annotation and default value
                if field_name in required_fields:
                    annotations[field_name] = field_type
                else:
                    annotations[field_name] = Optional[field_type]
                    field_defaults[field_name] = None
            
            # Create dynamic model class
            model_name = f"{tool_name.title().replace('_', '')}Input"
            
            # Create the class dynamically with proper inheritance
            class DynamicModel(V1BaseModel):
                pass
            
            # Set the annotations and defaults
            DynamicModel.__annotations__ = annotations
            for field_name, default_value in field_defaults.items():
                setattr(DynamicModel, field_name, default_value)
            
            # Set the class name
            DynamicModel.__name__ = model_name
            DynamicModel.__qualname__ = model_name
            
            return DynamicModel
        
        except Exception as e:
            logger.warning(f"Failed to create Pydantic model for {tool_name}: {e}")
            # Return basic model as fallback
            return MCPToolInput
    
    async def _arun(self, **kwargs: Any) -> str:
        """Execute the MCP tool asynchronously."""
        try:
            # Filter out None values
            parameters = {k: v for k, v in kwargs.items() if v is not None}
            
            # Call the MCP tool
            result = await self.mcp_client.call_tool(
                self.server_name, 
                self.tool_name, 
                parameters
            )
            
            # Extract and return the result
            if isinstance(result, dict):
                return result.get("result", str(result))
            else:
                return str(result)
                
        except Exception as e:
            error_msg = f"Failed to execute MCP tool {self.tool_name}: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
    
    def _run(self, **kwargs: Any) -> str:
        """Synchronous run method (not implemented for MCP tools)."""
        raise NotImplementedError("MCP tools only support async execution")


class MCPToolkit:
    """Toolkit for managing MCP tools as LangChain Tools."""
    
    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        self._tools_cache: Dict[str, List[MCPTool]] = {}
    
    async def get_tools(self, server_name: Optional[str] = None) -> List[MCPTool]:
        """Get all available MCP tools as LangChain Tools."""
        # Get available tools from MCP client
        available_tools = await self.mcp_client.list_tools(server_name)
        
        all_tools = []
        
        for srv_name, tools in available_tools.items():
            if srv_name not in self._tools_cache:
                self._tools_cache[srv_name] = []
            
            # Convert each tool to LangChain Tool
            for tool_info in tools:
                tool_name = tool_info["name"]
                description = tool_info.get("description", f"MCP tool: {tool_name}")
                input_schema = tool_info.get("inputSchema", {})
                
                # Create LangChain Tool
                mcp_tool = MCPTool(
                    mcp_client=self.mcp_client,
                    server_name=srv_name,
                    tool_name=tool_name,
                    description=description,
                    input_schema=input_schema
                )
                
                self._tools_cache[srv_name].append(mcp_tool)
                all_tools.append(mcp_tool)
        
        return all_tools
    
    async def get_tool(self, server_name: str, tool_name: str) -> Optional[MCPTool]:
        """Get a specific MCP tool."""
        if server_name not in self._tools_cache:
            await self.get_tools(server_name)
        
        for tool in self._tools_cache.get(server_name, []):
            if tool.tool_name == tool_name:
                return tool
        
        return None
    
    def get_tool_names(self) -> List[str]:
        """Get names of all cached tools."""
        names = []
        for tools in self._tools_cache.values():
            names.extend([tool.name for tool in tools])
        return names 