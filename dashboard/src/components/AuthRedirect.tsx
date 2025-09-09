import { useEffect } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

/**
 * Component that handles OAuth redirect by navigating to a protected endpoint
 * and letting the OAuth2 proxy handle the redirect naturally
 */
export default function AuthRedirect() {
  useEffect(() => {
    // Instead of redirecting to OAuth login directly, navigate to a protected endpoint
    // and let the OAuth2 proxy handle the redirect naturally
    const currentPath = window.location.pathname + window.location.search;
    const protectedUrl = `/api/v1/history/active-sessions?redirect_after_auth=${encodeURIComponent(currentPath)}`;
    
    console.log('Navigating to protected endpoint to trigger OAuth flow:', protectedUrl);
    window.location.href = protectedUrl;
  }, []);

  return (
    <Box 
      display="flex" 
      flexDirection="column" 
      alignItems="center" 
      justifyContent="center" 
      minHeight="100vh"
      gap={2}
    >
      <CircularProgress size={48} />
      <Typography variant="h6" color="text.secondary">
        Redirecting to login...
      </Typography>
    </Box>
  );
}
