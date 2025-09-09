import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from './theme';
import { AuthProvider } from './contexts/AuthContext';
import DashboardView from './components/DashboardView';
import SessionDetailWrapper from './components/SessionDetailWrapper';
import ManualAlertSubmission from './components/ManualAlertSubmission';

/**
 * Main App component for the Tarsy Dashboard - Enhanced with Conversation View
 * Provides React Router setup with dual session detail views (conversation + technical)
 */
function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <Router>
          <Routes>
            {/* Main dashboard route */}
            <Route path="/" element={<DashboardView />} />
            <Route path="/dashboard" element={<DashboardView />} />
            
            {/* Session detail routes - Unified wrapper prevents duplicate API calls */}
            <Route path="/sessions/:sessionId" element={<SessionDetailWrapper />} />
            <Route path="/sessions/:sessionId/technical" element={<SessionDetailWrapper />} />
            
            {/* Manual Alert Submission route - EP-0018 */}
            <Route path="/submit-alert" element={<ManualAlertSubmission />} />
            
            {/* Catch-all route redirects to dashboard */}
            <Route path="*" element={<DashboardView />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
