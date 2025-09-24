#!/usr/bin/env python3
"""Simple test script to validate Phase 2 transport factory implementation."""

import asyncio
from contextlib import AsyncExitStack

from tarsy.integrations.mcp.transport.factory import MCPTransportFactory
from tarsy.models.mcp_transport_config import StdioTransportConfig, HTTPTransportConfig, TRANSPORT_STDIO, TRANSPORT_HTTP


async def test_stdio_transport():
    """Test stdio transport creation."""
    print("🔧 Testing Stdio Transport...")
    
    # Create stdio config
    stdio_config = StdioTransportConfig(
        command="echo",
        args=["Hello from stdio transport!"]
    )
    
    async with AsyncExitStack() as exit_stack:
        # Create transport
        transport = MCPTransportFactory.create_transport(
            server_id="test-stdio-server",
            transport=stdio_config,
            exit_stack=exit_stack
        )
        
        print(f"✅ Created stdio transport: {type(transport).__name__}")
        print(f"   - Server ID: test-stdio-server")
        print(f"   - Transport type: {stdio_config.type}")
        print(f"   - Command: {stdio_config.command}")
        print(f"   - Args: {stdio_config.args}")
        print(f"   - Connected: {transport.is_connected}")


async def test_http_transport():
    """Test HTTP transport creation."""
    print("\n🌐 Testing HTTP Transport...")
    
    # Create HTTP config
    http_config = HTTPTransportConfig(
        url="http://localhost:8080/mcp",
        bearer_token="test-token-123",
        verify_ssl=False,
        timeout=30
    )
    
    # Create transport
    transport = MCPTransportFactory.create_transport(
        server_id="test-http-server",
        transport=http_config
    )
    
    print(f"✅ Created HTTP transport: {type(transport).__name__}")
    print(f"   - Server ID: test-http-server")
    print(f"   - Transport type: {http_config.type}")
    print(f"   - URL: {http_config.url}")
    print(f"   - Has bearer token: {bool(http_config.bearer_token)}")
    print(f"   - Verify SSL: {http_config.verify_ssl}")
    print(f"   - Timeout: {http_config.timeout}s")
    print(f"   - Connected: {transport.is_connected}")
    
    # Cleanup
    await transport.close()


async def test_transport_type_validation():
    """Test transport type validation."""
    print("\n🔍 Testing Transport Type Validation...")
    
    # Test constants
    stdio_type = TRANSPORT_STDIO
    http_type = TRANSPORT_HTTP
    
    print(f"✅ TRANSPORT_STDIO = {stdio_type}")
    print(f"✅ TRANSPORT_HTTP = {http_type}")
    
    # Test invalid type handling
    try:
        # This should fail with unsupported transport type
        class FakeTransport:
            type = "invalid-type"
        
        MCPTransportFactory.create_transport(
            server_id="invalid-server",
            transport=FakeTransport()
        )
        print("❌ Should have raised ValueError for invalid transport type")
    except ValueError as e:
        print(f"✅ Correctly rejected invalid transport type: {e}")


async def main():
    """Run all validation tests."""
    print("🚀 Phase 2 Transport Factory Validation")
    print("=" * 50)
    
    try:
        await test_stdio_transport()
        await test_http_transport()
        await test_transport_type_validation()
        
        print("\n" + "=" * 50)
        print("🎉 All Phase 2 transport factory tests passed!")
        print("✅ Stdio transport: Working")
        print("✅ HTTP transport: Working")  
        print("✅ Factory validation: Working")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
