# TARSy Dashboard

The TARSy Dashboard is a React + TypeScript + Vite frontend that provides a real-time interface for monitoring alert processing, viewing historical analysis, and managing SRE operations.

## 🚀 Features

- **📊 Real-time Dashboard**: Live updates of alert processing status via WebSocket connections
- **📝 Manual Alert Submission**: Submit alerts for testing and development
- **📈 Processing Timeline**: Detailed chronological view of agent chain execution
- **🔍 Historical Analysis**: Browse and filter past alert processing sessions  
- **🔐 OAuth Integration**: GitHub OAuth authentication in production containers
- **📱 Responsive Design**: Mobile-friendly interface with modern UI components

## 🛠️ Technology Stack

- **React 18** - Modern React with hooks and functional components
- **TypeScript** - Full type safety across the application
- **Vite** - Fast build tool with Hot Module Replacement (HMR)
- **Tailwind CSS** - Utility-first CSS framework for styling
- **WebSocket** - Real-time communication for live updates
- **Axios** - HTTP client for API communication

## 🏗️ Development

The dashboard is designed to work in two modes:

### Development Mode (Direct Backend)
- Connects directly to backend on `localhost:8000`
- Uses Vite's built-in proxy for API calls
- No authentication required
- Fast development with HMR

### Container Mode (Production-like)
- Served as static files via Nginx
- All requests routed through OAuth2-proxy
- GitHub OAuth authentication required
- Production-optimized build

## 📁 Project Structure

```
dashboard/
├── src/
│   ├── components/         # React components
│   │   ├── DashboardView.tsx    # Main dashboard interface
│   │   ├── AlertSubmission.tsx  # Manual alert form
│   │   └── ProcessingTimeline.tsx  # Chain execution timeline
│   ├── services/          # API and service layer
│   │   ├── api.ts         # HTTP client and API calls
│   │   ├── auth.ts        # Authentication service
│   │   └── websocket.ts   # WebSocket connection management
│   ├── contexts/          # React Context providers
│   │   └── AuthContext.tsx     # Authentication state management
│   ├── types/             # TypeScript type definitions
│   └── main.tsx           # Application entry point
├── public/                # Static assets
├── nginx.conf             # Production Nginx configuration
├── Dockerfile             # Multi-stage production container
├── vite.config.ts         # Vite configuration with proxy setup
└── package.json           # Dependencies and scripts
```

## 🔧 Configuration

### Environment Variables

The dashboard uses different configuration based on the deployment mode:

**Development Mode:**
- Uses relative URLs (handled by Vite proxy)
- Configuration in `.env.development`

**Container Mode:**
- Uses absolute URLs (baked into production build)
- Configured via Docker build arguments

### Vite Proxy Configuration

The `vite.config.ts` includes intelligent proxy configuration that:
- Routes API calls to backend in development
- Handles WebSocket connections
- Manages CORS automatically
- Switches behavior based on container vs development mode

## 📊 API Integration

The dashboard communicates with the TARSy backend via:

- **REST API**: Alert submission, status checks, historical data
- **WebSocket**: Real-time processing updates and notifications
- **OAuth2-Proxy**: Authentication in production containers

Key API endpoints:
- `POST /api/v1/alerts` - Submit new alerts
- `GET /api/v1/alert-types` - Get supported alert types  
- `GET /api/v1/history/sessions` - List processing sessions
- `WebSocket /ws/{alert_id}` - Real-time updates

## 🔐 Authentication

In container mode, the dashboard integrates with GitHub OAuth via oauth2-proxy:
- All routes protected behind authentication
- Session management handled by oauth2-proxy
- Logout functionality with proper redirect handling
- User info display from OAuth provider

## 🎨 UI Components

The dashboard uses a custom component library built with Tailwind CSS:
- Consistent design system
- Responsive layouts
- Loading states and error handling
- Real-time data visualization
- Interactive processing timelines

## 📦 Build Process

### Development Build
```bash
npm run dev    # Start Vite dev server with HMR
```

### Production Build
```bash
npm run build  # Create optimized production build
npm run preview # Preview production build locally
```

### Container Build
The multi-stage Dockerfile:
1. **Builder stage**: Install dependencies and create production build
2. **Runtime stage**: Serve via Nginx with custom configuration

## 🔄 Real-time Features

The dashboard provides real-time updates through:
- **WebSocket connections** for live alert processing status
- **Automatic reconnection** with exponential backoff
- **Connection health monitoring** with status indicators
- **Error handling** with user-friendly notifications

## 🧪 Testing

The dashboard includes comprehensive testing setup:
- Unit tests for components and services
- Integration tests for API communication
- End-to-end tests for user workflows

Run tests:
```bash
npm run test
```

## 🚀 Deployment

The dashboard is deployed as part of the TARSy container stack:
- Built into optimized static files
- Served via Nginx reverse proxy
- Integrated with OAuth2-proxy for authentication
- Configured for production performance

See the main [README.md](../README.md) for complete deployment instructions.