# OAuth2-Proxy Setup for TARSy

This guide covers setting up [OAuth2-Proxy](https://github.com/oauth2-proxy/oauth2-proxy) for authentication testing with the TARSy dashboard.

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
   - **Application name**: `TARSy Container Deployment`
   - **Homepage URL**: `http://localhost:8080`
   - **Authorization callback URL**: `http://localhost:8080/oauth2/callback`
4. Click "Register application"
5. Save the **Client ID** and **Client Secret**

> **Note**: For container deployment, OAuth2-proxy runs behind an Nginx reverse proxy on port 8080, not directly on port 4180.

## Configuration

The OAuth2-proxy configuration is in `config/oauth2-proxy.cfg`. 

**📋 For a complete configuration template, see: [`config/oauth2-proxy-container.cfg.example`](../config/oauth2-proxy-container.cfg.example)**

## Container Deployment (Recommended)

OAuth2-proxy is integrated into the containerized deployment and runs automatically:

```bash
# Deploy complete stack with OAuth2-proxy (preserves database)
make containers-deploy

# OR deploy fresh stack (clean rebuild including database)
make containers-deploy-fresh

# Check container status
make containers-status

# View OAuth2-proxy logs
make containers-logs

# Stop all containers
make containers-stop
```

The OAuth2-proxy container is configured to:
- Run behind Nginx reverse proxy on port 8080
- Automatically protect all `/api` endpoints  
- Handle authentication for the dashboard
- Use the configuration from `config/oauth2-proxy-container.cfg`

## Manual Configuration (Advanced)

If you need to run OAuth2-proxy outside of containers:

```bash
# Foreground (for debugging)
oauth2-proxy --config=config/oauth2-proxy.cfg

# Background
nohup oauth2-proxy --config=config/oauth2-proxy.cfg > logs/oauth2-proxy.log 2>&1 &
```

> **Note**: Manual OAuth2-proxy setup is primarily for advanced debugging. The recommended approach is container deployment.

## Production Considerations

For production deployments:

1. **Use HTTPS**: Configure `tls_cert_file` and `tls_key_file`
2. **Secure cookies**: Set `cookie_secure = true`
3. **Restrict access**: Use provider-specific restrictions (GitHub org, Google domain)
4. **Session management**: Configure appropriate `cookie_expire` settings
5. **Reverse proxy**: Set `reverse_proxy = true` if behind nginx/apache

## Useful Commands Reference

```bash
# Container Deployment (with OAuth2-proxy)
make containers-deploy        # Deploy stack (rebuild apps, preserve database)
make containers-deploy-fresh  # Deploy fresh stack (rebuild everything)
make containers-start         # Start all containers (with build)
make containers-start-fast    # Start containers (no build)
make containers-stop          # Stop all containers
make containers-clean         # Remove all containers and data

# Container Management
make containers-status        # Show container status
make containers-logs          # Show logs from all containers
make containers-build         # Build container images
make containers-build-app     # Build only application containers

# Development (no authentication)
make dev                      # Start development services
make status                   # Show service status
make stop                     # Stop development services
```

## Additional Resources

- [OAuth2-Proxy Documentation](https://oauth2-proxy.github.io/oauth2-proxy/)
- [GitHub OAuth Apps](https://docs.github.com/en/developers/apps/building-oauth-apps/creating-an-oauth-app)
- [Google OAuth Setup](https://developers.google.com/identity/protocols/oauth2)
