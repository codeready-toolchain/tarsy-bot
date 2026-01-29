"""LLM and MCP interaction logging operations."""

import logging

from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra

logger = logging.getLogger(__name__)


class InteractionOperations:
    """LLM and MCP interaction logging."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def store_llm_interaction(self, interaction: LLMInteraction) -> bool:
        """Store an LLM interaction to the database."""
        if not interaction.session_id:
            return False
            
        def _store_llm_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot store LLM interaction")
                repo.create_llm_interaction(interaction)
                logger.debug(f"Stored LLM interaction for session {interaction.session_id}")
                return True

        result = self._infra._retry_database_operation("store_llm_interaction", _store_llm_operation)
        return bool(result)
    
    def store_mcp_interaction(self, interaction: MCPInteraction) -> bool:
        """Store an MCP interaction to the database.
        
        Note: May populate interaction.step_description if not set.
        """
        if not interaction.session_id:
            return False
            
        def _store_mcp_operation() -> bool:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot store MCP interaction")
                if not interaction.step_description:
                    interaction.step_description = interaction.get_step_description()
                repo.create_mcp_communication(interaction)
                logger.debug(f"Stored MCP interaction for session {interaction.session_id}")
                return True

        result = self._infra._retry_database_operation("store_mcp_interaction", _store_mcp_operation)
        return bool(result)
