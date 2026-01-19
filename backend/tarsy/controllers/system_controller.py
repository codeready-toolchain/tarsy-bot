"""System-level API endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from tarsy.config.settings import get_settings
from tarsy.models.llm_models import GoogleNativeTool
from tarsy.models.mcp_api_models import MCPServerInfo, MCPServersResponse, MCPToolInfo
from tarsy.models.system_models import SystemWarning
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
async def get_mcp_servers(_request: Request) -> MCPServersResponse:
    """
    Get available MCP servers and their tools.
    
    Uses cached tool lists from the health monitor when available, falling back
    to direct MCP queries during the startup period (first ~15 seconds).
    
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
        
        # Try to use cached tools from health monitor first
        cached_tools = {}
        if alert_service.mcp_health_monitor is not None:
            cached_tools = alert_service.mcp_health_monitor.get_cached_tools()
        
        # Get all server IDs from registry
        server_ids = alert_service.mcp_server_registry.get_all_server_ids()
        logger.info(f"Found {len(server_ids)} configured MCP servers")
        
        # If cache is empty (startup period), fall back to creating dedicated client
        if not cached_tools:
            logger.info("Tool cache empty (startup period), falling back to direct MCP queries")
            return await _get_mcp_servers_direct(alert_service, server_ids)
        
        # Use cached tools - much faster!
        logger.info(f"Using cached tools for {len(cached_tools)} servers")
        servers_info = []
        total_tools = 0
        
        for server_id in server_ids:
            try:
                # Get server configuration
                server_config = alert_service.mcp_server_registry.get_server_config(server_id)
                
                # Get tools from cache (empty list if server not in cache yet)
                tools = []
                if server_id in cached_tools:
                    for tool in cached_tools[server_id]:
                        tools.append(MCPToolInfo(
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {}
                        ))
                
                total_tools += len(tools)
                
                servers_info.append(MCPServerInfo(
                    server_id=server_id,
                    tools=tools
                ))
                
                logger.debug(f"Server '{server_id}' has {len(tools)} cached tools")
                
            except Exception as e:
                # Log error but continue with other servers
                logger.error(f"Failed to process server '{server_id}': {e}")
                # Include server in response but with no tools
                try:
                    # Just verify server exists in registry
                    alert_service.mcp_server_registry.get_server_config(server_id)
                    servers_info.append(MCPServerInfo(
                        server_id=server_id,
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
                
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to list MCP servers: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to retrieve MCP servers: {str(e)}"
        ) from e


async def _get_mcp_servers_direct(alert_service, server_ids: list[str]) -> MCPServersResponse:
    """
    Fallback: Query MCP servers directly when cache is not available.
    
    Used during startup period before health monitor has populated the cache.
    """
    mcp_client = None
    try:
        logger.info("Creating dedicated MCP client for server discovery")
        mcp_client = await alert_service.mcp_client_factory.create_client()
        
        servers_info = []
        total_tools = 0
        
        # Query each server for its tools
        for server_id in server_ids:
            try:
                # Get server configuration
                server_config = alert_service.mcp_server_registry.get_server_config(server_id)
                
                # List tools from this server (simple version without database storage)
                server_tools_dict = await mcp_client.list_tools_simple(
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
                    server_id=server_id,
                    tools=tools
                ))
                
                logger.info(f"Server '{server_id}' has {len(tools)} tools")
                
            except Exception as e:
                # Log error but continue with other servers
                logger.error(f"Failed to query server '{server_id}': {e}")
                # Include server in response but with no tools
                try:
                    # Just verify server exists in registry
                    alert_service.mcp_server_registry.get_server_config(server_id)
                    servers_info.append(MCPServerInfo(
                        server_id=server_id,
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
            await mcp_client.close()


@router.get("/default-tools")
async def get_default_tools(
    _request: Request,
    alert_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get default tools configuration for a specific alert type.
    
    Returns the default MCP servers and native tools that would be used
    for the specified alert type based on its chain configuration.
    Different alert types use different chains with different agent configurations.
    
    Args:
        alert_type: Optional alert type. If not provided, uses the default alert type.
    
    Returns:
        Dict with:
        - alert_type: The alert type these defaults are for
        - mcp_servers: List of default MCP server IDs for this alert type's chain
        - native_tools: Dict of native tool names and their default states
        
    Raises:
        400: Invalid alert type
        503: Service not initialized or configuration unavailable
    """
    try:
        # Get settings to access LLM provider configuration
        settings = get_settings()
        
        # Get current provider configuration for native tools
        provider_config = settings.get_llm_config(settings.llm_provider)
        
        # Extract default native tools from provider config
        # If native_tools is None in config, default is all enabled for Google/Gemini
        native_tools_config = provider_config.native_tools
        
        if native_tools_config is None:
            # Default: Google Search and URL Context enabled, Code Execution disabled for security
            default_native_tools = {
                GoogleNativeTool.GOOGLE_SEARCH.value: True,
                GoogleNativeTool.CODE_EXECUTION.value: False,
                GoogleNativeTool.URL_CONTEXT.value: True,
            }
        else:
            # Use provider's explicit configuration
            default_native_tools = native_tools_config.copy()
        
        # Get alert service for chain and agent configuration
        from tarsy.main import alert_service
        
        if alert_service is None:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        # Determine which alert type to use
        effective_alert_type = alert_type or alert_service.chain_registry.get_default_alert_type()
        
        # Get the chain for this alert type
        try:
            chain_config = alert_service.chain_registry.get_chain_for_alert_type(effective_alert_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        
        # Collect MCP servers from all agents in the chain
        server_names = set()
        for stage in chain_config.stages:
            agent_name = stage.agent
            if not agent_name:
                continue
            
            # Look up agent's default MCP servers from configuration
            # Try configured agents first, then builtin agents
            if alert_service.agent_factory.agent_configs and agent_name in alert_service.agent_factory.agent_configs:
                agent_config = alert_service.agent_factory.agent_configs[agent_name]
                server_names.update(agent_config.mcp_servers)
            else:
                # Builtin agent - get MCP servers by calling the classmethod
                try:
                    # Get the agent class from the factory's registry
                    agent_class = alert_service.agent_factory.static_agent_classes.get(agent_name)
                    if agent_class:
                        # Call mcp_servers() as a classmethod (no instantiation needed)
                        if hasattr(agent_class, 'mcp_servers'):
                            mcp_server_list = agent_class.mcp_servers()
                            if mcp_server_list:  # Guard against None
                                server_names.update(mcp_server_list)
                                logger.debug(f"Got MCP servers from builtin agent {agent_name}: {mcp_server_list}")
                except Exception as e:
                    logger.warning(f"Failed to get MCP servers from builtin agent '{agent_name}': {e}")
        
        # Get server details for the collected server names
        mcp_servers = []
        for server_id in sorted(server_names):
            try:
                # Just verify server exists in registry
                alert_service.mcp_server_registry.get_server_config(server_id)
                mcp_servers.append({
                    "server_id": server_id,
                })
            except Exception as e:
                logger.warning(f"Failed to get config for server '{server_id}': {e}")
                continue
        
        logger.info(f"Returning defaults for alert_type='{effective_alert_type}': "
                   f"{len(mcp_servers)} MCP servers, native_tools={default_native_tools}")
        
        return {
            "alert_type": effective_alert_type,
            "mcp_servers": mcp_servers,
            "native_tools": default_native_tools
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get default tools: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to retrieve default tools configuration: {str(e)}"
        ) from e
