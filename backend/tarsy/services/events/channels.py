"""Event channel definitions for TARSy eventing system."""


class EventChannel:
    """Event channel definitions for TARSy eventing system."""

    SESSIONS = "sessions"
    """
    Global session lifecycle events for all sessions.

    Events: session.created, session.started, session.completed, session.failed
    Consumers: Dashboard main page, monitoring tools, CLI
    """

    @staticmethod
    def session_details(session_id: str) -> str:
        """
        Per-session detail channel for specific session operations.

        Events: llm.interaction, mcp.tool_call, stage.started, stage.completed
        Consumers: Session detail page, CLI following specific session

        Args:
            session_id: Session identifier

        Returns:
            Channel name (e.g., "session:abc-123")
        """
        return f"session:{session_id}"

