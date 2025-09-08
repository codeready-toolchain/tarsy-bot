import { ReactNode } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useAuth } from '../../contexts/AuthContext';
import LoginPage from './LoginPage';

interface AuthGuardProps {
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Authentication guard component that protects routes
 * 
 * EP-0017 Implementation:
 * - Shows loading while checking authentication
 * - Redirects to login if not authenticated
 * - Renders protected content if authenticated
 */
export default function AuthGuard({ children, fallback }: AuthGuardProps) {
  const { user, loading } = useAuth();

  // Show loading state while checking authentication
  if (loading) {
    return fallback || (
      <Box
        display="flex"
        flexDirection="column"
        alignItems="center"
        justifyContent="center"
        minHeight="100vh"
        gap={2}
      >
        <CircularProgress size={48} />
        <Typography variant="body1" color="textSecondary">
          Loading...
        </Typography>
      </Box>
    );
  }

  // Show login page if not authenticated
  if (!user) {
    return <LoginPage />;
  }

  // Render protected content if authenticated
  return <>{children}</>;
}
