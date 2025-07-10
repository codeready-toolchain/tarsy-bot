"""
Test script to verify the LangChain refactor works correctly.
"""

import asyncio
import sys
from app.config.settings import get_settings
from app.models.alert import Alert
from app.services.langchain_alert_service import LangChainAlertService
from app.utils.logger import setup_logging, get_module_logger

# Setup logging
setup_logging("INFO")
logger = get_module_logger(__name__)


async def test_langchain_refactor():
    """Test the LangChain refactor functionality."""
    try:
        # Initialize settings
        settings = get_settings()
        
        # Create alert service
        alert_service = LangChainAlertService(settings)
        
        # Initialize the service
        logger.info("Initializing LangChain Alert Service...")
        await alert_service.initialize()
        
        # Create a test alert
        test_alert = Alert(
            alert="HighMemoryUsage",
            severity="high",
            environment="production",
            cluster="https://k8s.example.com",
            namespace="web-app",
            pod="web-app-pod-123",
            message="Memory usage has exceeded 85% on production servers",
            runbook="mock://runbook/high-memory.md"
        )
        
        logger.info("Processing test alert...")
        
        # Process the alert
        async def progress_callback(progress: int, step: str):
            logger.info(f"Progress: {progress}% - {step}")
        
        result = await alert_service.process_alert(test_alert, progress_callback)
        
        logger.info("Alert processing completed!")
        logger.info(f"Result: {result}")
        
        # Clean up
        await alert_service.close()
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        return False
    
    return True


async def main():
    """Main test function."""
    logger.info("Starting LangChain refactor test...")
    
    success = await test_langchain_refactor()
    
    if success:
        logger.info("✅ LangChain refactor test passed!")
        return 0
    else:
        logger.error("❌ LangChain refactor test failed!")
        return 1


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(result)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Test failed with exception: {str(e)}", exc_info=True)
        sys.exit(1) 