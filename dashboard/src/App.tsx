import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import { theme } from './theme';
import { AuthProvider } from './contexts/AuthContext';
import { VersionProvider, useVersion } from './contexts/VersionContext';
import DashboardView from './components/DashboardView';
import SessionDetailWrapper from './components/SessionDetailWrapper';
import ManualAlertSubmission from './components/ManualAlertSubmission';
import NotFoundPage from './components/NotFoundPage';
import VersionUpdateBanner from './components/VersionUpdateBanner';

/**
 * AppContent component - Contains routes and version-aware components
 * Separated from App to allow useVersion hook inside VersionProvider
 */
function AppContent() {
  const { dashboardVersionChanged } = useVersion();
  
  return (
    <>
      <VersionUpdateBanner show={dashboardVersionChanged} />
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
            
            {/* Catch-all route shows 404 page */}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Router>
      </AuthProvider>
    </>
  );
}

/**
 * Main App component for the Tarsy Dashboard - Enhanced with Conversation View
 * Provides React Router setup with dual session detail views (conversation + technical)
 * Includes version monitoring with update banner
 */
function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <VersionProvider>
        <AppContent />
      </VersionProvider>
    </ThemeProvider>
  );
}

export default App;
