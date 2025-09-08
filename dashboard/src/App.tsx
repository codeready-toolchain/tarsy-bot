import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from './theme';
import { AuthProvider } from './contexts/AuthContext';
import AuthGuard from './components/auth/AuthGuard';
import LoginPage from './components/auth/LoginPage';
import DashboardView from './components/DashboardView';
import SessionDetailWrapper from './components/SessionDetailWrapper';
import ManualAlertSubmission from './components/ManualAlertSubmission';

/**
 * Main App component for the Tarsy Dashboard - Enhanced with EP-0017 Authentication
 * Provides React Router setup with authentication guards and dual session detail views
 */
function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public login route */}
            <Route path="/login" element={<LoginPage />} />
            
            {/* Protected routes - require authentication */}
            <Route path="/" element={<AuthGuard><DashboardView /></AuthGuard>} />
            <Route path="/dashboard" element={<AuthGuard><DashboardView /></AuthGuard>} />
            
            {/* Session detail routes - Unified wrapper prevents duplicate API calls */}
            <Route path="/sessions/:sessionId" element={<AuthGuard><SessionDetailWrapper /></AuthGuard>} />
            <Route path="/sessions/:sessionId/technical" element={<AuthGuard><SessionDetailWrapper /></AuthGuard>} />
            
            {/* Manual Alert Submission route - EP-0018 */}
            <Route path="/submit-alert" element={<AuthGuard><ManualAlertSubmission /></AuthGuard>} />
            
            {/* Catch-all route - show login for unknown paths */}
            <Route path="*" element={<LoginPage />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
