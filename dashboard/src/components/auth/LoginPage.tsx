import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Container, Paper, Typography, Button, CircularProgress } from '@mui/material';
import { GitHub } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

/**
 * Login page component that initiates GitHub OAuth authentication
 * 
 * EP-0017 Implementation:
 * - Redirects to backend OAuth endpoint with state-encoded redirect URL
 * - Handles dev mode and production authentication flows
 * - Shows loading state while checking existing authentication
 */
export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();

  // If user is already authenticated, redirect to dashboard
  useEffect(() => {
    if (!loading && user) {
      console.log('✅ User already authenticated, navigating to dashboard');
      navigate('/dashboard', { replace: true });
    }
  }, [user, loading, navigate]);

  const handleLogin = () => {
    try {
      // Use dashboard as default redirect after login
      const redirectUrl = window.location.origin + '/dashboard';
      console.log('🔑 Starting GitHub OAuth login with redirect:', redirectUrl);
      login(redirectUrl);
      console.log('🔑 Login function called successfully');
    } catch (error) {
      console.error('❌ Error in handleLogin:', error);
    }
  };

  // Show loading while checking authentication status
  if (loading) {
    return (
      <Container maxWidth="sm">
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
            Checking authentication status...
          </Typography>
        </Box>
      </Container>
    );
  }

  // Show login form if not authenticated
  return (
    <Container maxWidth="sm">
      <Box
        display="flex"
        flexDirection="column"
        alignItems="center"
        justifyContent="center"
        minHeight="100vh"
        gap={4}
      >
        <Paper
          elevation={3}
          sx={{
            padding: 4,
            width: '100%',
            textAlign: 'center',
            borderRadius: 2,
          }}
        >
          <Typography variant="h4" component="h1" gutterBottom fontWeight="bold">
            Tarsy Dashboard
          </Typography>
          
          <Typography variant="h6" color="textSecondary" gutterBottom>
            Agent-Driven Alert Response System
          </Typography>
          
          <Typography variant="body1" color="textSecondary" paragraph sx={{ mt: 3, mb: 3 }}>
            Sign in with your GitHub account to access the dashboard.
            Organization and team membership will be verified.
          </Typography>

          <Button
            variant="contained"
            size="large"
            startIcon={<GitHub />}
            onClick={(e) => {
              console.log('🔘 Button click event fired!', e);
              e.preventDefault();
              handleLogin();
            }}
            sx={{
              mt: 2,
              py: 1.5,
              px: 4,
              fontSize: '1.1rem',
              textTransform: 'none',
              borderRadius: 2,
              backgroundColor: '#24292f',
              '&:hover': {
                backgroundColor: '#1a1e22',
              },
            }}
            fullWidth
          >
            Sign in with GitHub
          </Button>

          <Typography variant="caption" color="textSecondary" display="block" sx={{ mt: 3 }}>
            Secure authentication with HTTP-only cookies • No tokens stored in browser
          </Typography>
        </Paper>
      </Box>
    </Container>
  );
}
