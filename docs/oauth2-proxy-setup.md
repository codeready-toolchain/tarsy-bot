# OAuth2-Proxy Setup for Tarsy-bot

This guide covers setting up [OAuth2-Proxy](https://github.com/oauth2-proxy/oauth2-proxy) for authentication testing with the Tarsy-bot dashboard.

## Table of Contents
- [Installation](#installation)
- [OAuth Provider Setup](#oauth-provider-setup)
- [Configuration](#configuration)
- [Starting the Service](#starting-the-service)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Installation

**📖 For installation instructions, see the official documentation**: [OAuth2-Proxy Installation Guide](https://oauth2-proxy.github.io/oauth2-proxy/installation)

**Verify installation**:
```bash
oauth2-proxy --version
```

## OAuth Provider Setup

You need to configure an OAuth provider (GitHub, Google, etc.). Here's how to set up GitHub:

### GitHub OAuth App

1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Click "New OAuth App"
3. Fill in the details:
   - **Application name**: `Tarsy-bot Development`
   - **Homepage URL**: `http://localhost:4180`
   - **Authorization callback URL**: `http://localhost:4180/oauth2/callback`
4. Click "Register application"
5. Save the **Client ID** and **Client Secret**

## Configuration

The OAuth2-proxy configuration is in `config/oauth2-proxy.cfg`. 

**📋 For a complete configuration template, see: [`config/oauth2-proxy.cfg.example`](../config/oauth2-proxy.cfg.example)**

## Starting the Service

### Method 1: Using Make Commands (Recommended)

```bash
# Check oauth2-proxy status
make oauth2-proxy-status

# Start oauth2-proxy
make oauth2-proxy

# Start all services with oauth2-proxy automatically
make dev-auth-full

# Start backend + dashboard (assumes oauth2-proxy already running)
make dev-auth
```

### Method 2: Manual Start

```bash
# Foreground (for debugging)
oauth2-proxy --config=config/oauth2-proxy.cfg

# Background
nohup oauth2-proxy --config=config/oauth2-proxy.cfg > logs/oauth2-proxy.log 2>&1 &
```

## Production Considerations

For production deployments:

1. **Use HTTPS**: Configure `tls_cert_file` and `tls_key_file`
2. **Secure cookies**: Set `cookie_secure = true`
3. **Restrict access**: Use provider-specific restrictions (GitHub org, Google domain)
4. **Session management**: Configure appropriate `cookie_expire` settings
5. **Reverse proxy**: Set `reverse_proxy = true` if behind nginx/apache

## Useful Commands Reference

```bash
# OAuth2-Proxy Management
make oauth2-proxy-bg        # Start in background
make oauth2-proxy-status    # Check status
make oauth2-proxy           # Start in foreground

# Development Workflows  
make dev                    # Default (no auth)
make dev-auth              # Manual oauth2-proxy setup
make dev-auth-full         # Automatic oauth2-proxy setup

# Status and URLs
make status                # Show all service status
make urls                  # Show all service URLs
make stop                  # Stop all services
```

## Additional Resources

- [OAuth2-Proxy Documentation](https://oauth2-proxy.github.io/oauth2-proxy/)
- [GitHub OAuth Apps](https://docs.github.com/en/developers/apps/building-oauth-apps/creating-an-oauth-app)
- [Google OAuth Setup](https://developers.google.com/identity/protocols/oauth2)
