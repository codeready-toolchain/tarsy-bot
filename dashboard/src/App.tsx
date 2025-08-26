import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from './theme';
import DashboardView from './components/DashboardView';
import OptimizedSessionDetailPage from './components/OptimizedSessionDetailPage';
import ConversationSessionDetailPage from './components/ConversationSessionDetailPage';

/**
 * Main App component for the Tarsy Dashboard - Enhanced with Conversation View
 * Provides React Router setup with dual session detail views (conversation + technical)
 */
function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Routes>
          {/* Main dashboard route */}
          <Route path="/" element={<DashboardView />} />
          <Route path="/dashboard" element={<DashboardView />} />
          
          {/* Session detail routes - Dual View System */}
          {/* New default: Conversation-focused view */}
          <Route path="/sessions/:sessionId" element={<ConversationSessionDetailPage />} />
          {/* Technical detail view (existing optimized view) */}
          <Route path="/sessions/:sessionId/technical" element={<OptimizedSessionDetailPage />} />
          
          {/* Catch-all route redirects to dashboard */}
          <Route path="*" element={<DashboardView />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}

export default App;
