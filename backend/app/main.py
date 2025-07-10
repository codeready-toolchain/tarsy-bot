"""
SRE AI Agent - FastAPI Application
Main entry point for the SRE AI Agent backend service.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.models.alert import Alert, AlertResponse, ProcessingStatus
from app.services.langchain_alert_service import LangChainAlertService
from app.services.websocket_manager import WebSocketManager
from app.utils.logger import setup_logging, get_module_logger

# Setup logger for this module
logger = get_module_logger(__name__)

# Global state for processing status tracking
processing_status: Dict[str, ProcessingStatus] = {}
alert_service: LangChainAlertService = None
websocket_manager: WebSocketManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global alert_service, websocket_manager
    
    # Initialize services
    settings = get_settings()
    
    # Setup logging
    setup_logging(settings.log_level)
    
    alert_service = LangChainAlertService(settings)
    websocket_manager = WebSocketManager()
    
    # Startup
    await alert_service.initialize()
    logger.info("SRE AI Agent started successfully!")
    
    yield
    
    # Shutdown
    logger.info("SRE AI Agent shutting down...")


# Create FastAPI application
app = FastAPI(
    title="SRE AI Agent",
    description="Automated incident response agent using AI and MCP servers",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "SRE AI Agent is running", "status": "healthy"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sre-ai-agent"}


@app.get("/alert-types", response_model=List[str])
async def get_alert_types():
    """Get supported alert types."""
    return get_settings().supported_alerts


@app.post("/alerts", response_model=AlertResponse)
async def submit_alert(alert: Alert):
    """Submit a new alert for processing."""
    # Generate unique alert ID
    alert_id = str(uuid.uuid4())
    
    # Initialize processing status
    processing_status[alert_id] = ProcessingStatus(
        alert_id=alert_id,
        status="queued",
        progress=0,
        current_step="Alert received",
        result=None,
        error=None
    )
    
    # Start background processing
    asyncio.create_task(process_alert_background(alert_id, alert))
    
    return AlertResponse(
        alert_id=alert_id,
        status="queued",
        message="Alert submitted for processing"
    )


@app.get("/processing-status/{alert_id}", response_model=ProcessingStatus)
async def get_processing_status(alert_id: str):
    """Get processing status for an alert."""
    if alert_id not in processing_status:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return processing_status[alert_id]


@app.websocket("/ws/{alert_id}")
async def websocket_endpoint(websocket: WebSocket, alert_id: str):
    """WebSocket endpoint for real-time progress updates."""
    try:
        await websocket_manager.connect(websocket, alert_id)
        
        # Send initial status if available
        if alert_id in processing_status:
            await websocket_manager.send_status_update(
                alert_id, processing_status[alert_id]
            )
        
        # Keep connection alive - just wait for disconnect
        try:
            while True:
                # Wait for any message or disconnect
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected for alert {alert_id}")
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for alert {alert_id}")
    except Exception as e:
        logger.error(f"WebSocket endpoint error for alert {alert_id}: {str(e)}")
    finally:
        websocket_manager.disconnect(websocket, alert_id)


async def process_alert_background(alert_id: str, alert: Alert):
    """Background task to process an alert."""
    try:
        # Update status: processing started
        await update_processing_status(
            alert_id, "processing", 10, "Starting alert processing"
        )
        
        # Process the alert using AlertService
        result = await alert_service.process_alert(
            alert, 
            progress_callback=lambda progress, step: asyncio.create_task(
                update_processing_status(alert_id, "processing", progress, step)
            )
        )
        
        # Update status: completed
        await update_processing_status(
            alert_id, "completed", 100, "Processing completed", result
        )
        
    except Exception as e:
        # Update status: error
        await update_processing_status(
            alert_id, "error", 0, "Processing failed", None, str(e)
        )


async def update_processing_status(
    alert_id: str, 
    status: str, 
    progress: int, 
    current_step: str,
    result: str = None,
    error: str = None
):
    """Update processing status and notify WebSocket clients."""
    processing_status[alert_id] = ProcessingStatus(
        alert_id=alert_id,
        status=status,
        progress=progress,
        current_step=current_step,
        result=result,
        error=error
    )
    
    # Send update via WebSocket
    if websocket_manager:
        await websocket_manager.send_status_update(
            alert_id, processing_status[alert_id]
        )


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 