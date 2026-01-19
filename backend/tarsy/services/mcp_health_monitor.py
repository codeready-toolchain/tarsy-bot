"""
MCP Health Monitor Service.

Independent background service for periodic MCP server health monitoring.
"""

import asyncio
from typing import TYPE_CHECKING, Dict, List, Optional

from mcp.types import Tool

from tarsy.models.system_models import WarningCategory
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.integrations.mcp.client import MCPClient
    from tarsy.services.system_warnings_service import SystemWarningsService

logger = get_module_logger(__name__)


def _mcp_warning_message(server_id: str) -> str:
    """Generate standard warning message for MCP server failure."""
    return f"MCP Server '{server_id}' is currently unreachable"


class MCPHealthMonitor:
    """
    Independent background service for MCP server health monitoring.
    
    Responsibilities:
    - Periodically ping all configured MCP servers
    - Add warnings for unhealthy servers
    - Clear warnings for healthy servers
    - Attempt recovery of startup-failed servers
    
    Does NOT:
    - Manipulate session state directly
    - Reach into MCPClient internals
    - Manually recover sessions (client auto-recovers on use)
    """
    
    def __init__(
        self,
        mcp_client: "MCPClient",
        warnings_service: "SystemWarningsService",
        check_interval: float = 15.0
    ):
        """
        Initialize MCP health monitor.
        
        Args:
            mcp_client: MCP client instance to monitor
            warnings_service: System warnings service for managing warnings
            check_interval: Seconds between health checks (default: 15s)
        """
        self._mcp_client = mcp_client
        self._warnings_service = warnings_service
        self._check_interval = check_interval
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Tool cache: server_id -> list of tools from last successful check
        # Retains last successful tool list even if server becomes unhealthy
        self._tool_cache: Dict[str, List[Tool]] = {}
    
    async def start(self) -> None:
        """Start health monitoring background task."""
        if self._running:
            logger.warning("MCP health monitor already running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"MCP health monitor started (interval: {self._check_interval}s)")
    
    async def stop(self) -> None:
        """Stop health monitoring gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("MCP health monitor stopped")
    
    def get_cached_tools(self) -> Dict[str, List[Tool]]:
        """
        Get cached tool lists from last successful health checks.
        
        Returns a defensive copy of the cache to prevent external modifications.
        Both the dict and the lists inside are copied to prevent callers from
        mutating the internal cache.
        Cache retains last successful tool list even if server is currently unhealthy.
        
        Returns:
            Dictionary mapping server IDs to their tool lists
        """
        return {k: v.copy() for k, v in self._tool_cache.items()}
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop - checks all servers periodically."""
        logger.info("Health monitor loop started")
        
        try:
            while self._running:
                # Sleep FIRST - ensures app is fully started before first check
                # and matches the pattern of other background services
                await asyncio.sleep(self._check_interval)
                
                # Then check servers (app is definitely ready by now)
                try:
                    await self._check_all_servers()
                except asyncio.CancelledError:
                    # Re-raise cancellation to stop cleanly
                    raise
                except Exception as e:
                    logger.error(f"Error in health monitor loop: {e}", exc_info=True)
                
        except asyncio.CancelledError:
            logger.info("Health monitor loop cancelled")
        finally:
            logger.info("Health monitor loop stopped")
    
    async def _check_all_servers(self) -> None:
        """Check health of all configured MCP servers concurrently."""
        # Get all configured server IDs
        all_server_ids = self._mcp_client.mcp_registry.get_all_server_ids()
        
        # Check all servers concurrently (don't let slow servers block others)
        tasks = [
            self._check_and_update_warnings(server_id)
            for server_id in all_server_ids
        ]
        
        # Wait for all checks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_and_update_warnings(self, server_id: str) -> None:
        """Check a single server and update its warning status."""
        try:
            is_healthy = await self._check_server(server_id)
            
            if is_healthy:
                # Clear any existing warning
                self._clear_warning(server_id)
            else:
                # Ensure warning exists
                self._ensure_warning(server_id)
                
        except Exception as e:
            logger.error(f"Error checking server {server_id}: {e}", exc_info=True)
            # On error, ensure warning exists
            self._ensure_warning(server_id)
    
    async def _ping_and_cache_tools(self, server_id: str) -> bool:
        """
        Ping server by loading its tools and cache them if successful.
        
        This combines health check and tool caching into a single operation,
        avoiding duplicate list_tools() calls. Uses 5-second timeout for
        fast failure detection.
        
        Args:
            server_id: ID of the server to check and cache
            
        Returns:
            True if server is healthy and tools were cached, False otherwise
        """
        try:
            session = self._mcp_client.sessions.get(server_id)
            if not session:
                logger.debug(f"Cannot ping {server_id}: no session")
                return False
            
            # Ping by loading tools with timeout (5s for fast failure detection)
            tools_result = await asyncio.wait_for(
                session.list_tools(),
                timeout=5.0
            )
            
            # Update cache with new tool list
            self._tool_cache[server_id] = tools_result.tools
            logger.debug(f"Pinged and cached {len(tools_result.tools)} tools for {server_id}")
            return True
            
        except asyncio.TimeoutError:
            logger.debug(f"Ping timeout for {server_id} (5s)")
            return False
        except Exception as e:
            logger.debug(f"Ping failed for {server_id}: {e}")
            return False
    
    async def _check_server(self, server_id: str) -> bool:
        """
        Check if a single server is healthy and cache its tools.
        
        Handles two cases:
        1. Server has session: ping it - if fails, try to recover with new session
        2. Server has no session: try to initialize it (startup failure recovery)
        
        On successful health check, loads and caches the server's tool list.
        
        Args:
            server_id: ID of the server to check
            
        Returns:
            True if healthy, False otherwise
        """
        # Early check: Skip missing servers
        server_config = self._mcp_client.mcp_registry.get_server_config_safe(server_id)
        if server_config is None:
            # Server config is missing - clear any stale warnings and skip health checks
            logger.debug(f"Skipping health check for {server_id}: config missing")
            self._clear_warning(server_id)
            return False
        
        # Case 1: Server has a session - ping it (and cache tools if successful)
        has_session = server_id in self._mcp_client.sessions
        if has_session:
            # Ping and cache tools in single operation (avoids duplicate list_tools calls)
            is_healthy = await self._ping_and_cache_tools(server_id)
            if is_healthy:
                logger.debug(f"✓ Server {server_id}: healthy")
                return True
            else:
                # Ping failed - session is dead, try to recover with new session
                # try_initialize_server() will replace the dead session
                logger.warning(f"✗ Server {server_id}: ping failed, attempting recovery")
                # Fall through to recovery attempt
        
        # Case 2: Server has no session OR ping failed (need recovery)
        # try_initialize_server() creates new session (replaces dead one if exists)
        if not has_session:
            logger.debug(f"Server {server_id} has no session, attempting initialization...")
        
        success = await self._mcp_client.try_initialize_server(server_id)
        
        if success:
            # Session created/replaced successfully - verify it works and cache tools
            logger.debug(f"Session created for {server_id}, verifying with ping...")
            # Ping and cache tools in single operation
            is_healthy = await self._ping_and_cache_tools(server_id)
            if is_healthy:
                logger.info(f"✓ Successfully recovered {server_id}")
                return True
            else:
                logger.debug(f"Session created for {server_id} but ping failed")
                return False
        else:
            logger.debug(f"Failed to initialize {server_id}")
            return False
    
    def _ensure_warning(self, server_id: str) -> None:
        """
        Ensure a warning exists for unhealthy MCP server.
        Idempotent - only adds if no warning currently exists.
        """
        from datetime import datetime, timezone

        from tarsy.utils.timestamp import now_us
        
        # Check if warning already exists
        existing_warnings = self._warnings_service.get_warnings()
        for warning in existing_warnings:
            if (warning.category == WarningCategory.MCP_INITIALIZATION and 
                warning.server_id == server_id):
                # Warning already exists
                return
        
        # Add new warning
        timestamp_us = now_us()
        timestamp_readable = datetime.fromtimestamp(
            timestamp_us / 1_000_000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        warning_id = self._warnings_service.add_warning(
            category=WarningCategory.MCP_INITIALIZATION,
            message=_mcp_warning_message(server_id),
            details=(
                f"Server unreachable as of {timestamp_readable}. "
                f"The server may be down, misconfigured, or experiencing network issues. "
                f"Tools from this server are temporarily unavailable. "
                f"This warning will automatically clear when the server recovers."
            ),
            server_id=server_id,
        )
        logger.info(f"Added warning {warning_id} for unhealthy server: {server_id}")
    
    def _clear_warning(self, server_id: str) -> None:
        """
        Clear any warnings for this MCP server.
        Idempotent - safe to call even if no warning exists.
        """
        self._warnings_service.clear_warning_by_server_id(
            category=WarningCategory.MCP_INITIALIZATION,
            server_id=server_id,
        )

