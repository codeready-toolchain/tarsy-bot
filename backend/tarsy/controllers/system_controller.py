"""System-level API endpoints."""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Request

from tarsy.models.system_models import SystemWarning
from tarsy.models.mcp_api_models import MCPServersResponse, MCPServerInfo, MCPToolInfo
from tarsy.services.system_warnings_service import get_warnings_service
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/warnings", response_model=List[SystemWarning])
async def get_system_warnings() -> List[SystemWarning]:
    """
    Get active system warnings.

    Returns warnings about non-fatal system errors that operators
    should be aware of (e.g., failed MCP servers, missing configuration).

    Returns:
        List of active system warnings
    """
    warnings_service = get_warnings_service()
    return warnings_service.get_warnings()  # Pydantic handles serialization


@router.get("/mcp-servers", response_model=MCPServersResponse)
async def get_mcp_servers(request: Request) -> MCPServersResponse:
    """
    Get available MCP servers and their tools.
    
    This endpoint creates a dedicated MCP client instance to discover all
    available servers and list their tools. Useful for building UI for
    MCP server/tool selection.
    
    Returns:
        MCPServersResponse with list of servers and their tools
        
    Raises:
        503: Service not initialized or MCP client unavailable
    """
    try:
        # Get alert_service from app state
        from tarsy.main import alert_service
        
        if alert_service is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        # Create dedicated MCP client for this request
        # Use MCPClientFactory to avoid async context issues
        mcp_client = None
        try:
            logger.info("Creating dedicated MCP client for server discovery")
            mcp_client = await alert_service.mcp_client_factory.create_client()
            
            # Get all server IDs from registry
            server_ids = alert_service.mcp_server_registry.get_all_server_ids()
            logger.info(f"Found {len(server_ids)} configured MCP servers")
            
            # Generate temporary session ID for tool listing (not tied to alert)
            temp_session_id = f"mcp-discovery-{uuid.uuid4().hex[:8]}"
            
            servers_info = []
            total_tools = 0
            
            # Query each server for its tools
            for server_id in server_ids:
                try:
                    # Get server configuration
                    server_config = alert_service.mcp_server_registry.get_server_config(server_id)
                    
                    # List tools from this server
                    server_tools_dict = await mcp_client.list_tools(
                        session_id=temp_session_id,
                        server_name=server_id
                    )
                    
                    # Extract tools for this server
                    tools = []
                    if server_id in server_tools_dict:
                        for tool in server_tools_dict[server_id]:
                            tools.append(MCPToolInfo(
                                name=tool.name,
                                description=tool.description or "",
                                input_schema=tool.inputSchema or {}
                            ))
                    
                    total_tools += len(tools)
                    
                    servers_info.append(MCPServerInfo(
                        server_id=server_config.server_id,
                        server_type=server_config.server_type,
                        enabled=server_config.enabled,
                        tools=tools
                    ))
                    
                    logger.info(f"Server '{server_id}' has {len(tools)} tools")
                    
                except Exception as e:
                    # Log error but continue with other servers
                    logger.error(f"Failed to query server '{server_id}': {e}")
                    # Include server in response but with no tools
                    try:
                        server_config = alert_service.mcp_server_registry.get_server_config(server_id)
                        servers_info.append(MCPServerInfo(
                            server_id=server_config.server_id,
                            server_type=server_config.server_type,
                            enabled=server_config.enabled,
                            tools=[]
                        ))
                    except Exception:
                        # Skip this server entirely if we can't even get config
                        pass
            
            return MCPServersResponse(
                servers=servers_info,
                total_servers=len(servers_info),
                total_tools=total_tools
            )
            
        finally:
            # Clean up MCP client
            if mcp_client:
                logger.info("Cleaning up dedicated MCP client")
                await mcp_client.cleanup()
                
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to list MCP servers: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to retrieve MCP servers: {str(e)}"
        )
