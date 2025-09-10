import { useEffect } from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

/**
 * Component that handles OAuth redirect by navigating directly to the OAuth2 proxy sign-in endpoint
 * to initiate the authentication flow and return to the original route after successful authentication
 */
export default function AuthRedirect() {
  useEffect(() => {
    // Navigate directly to oauth2-proxy sign-in endpoint to initiate OAuth flow
    // This avoids 401 responses from API routes configured with oauth2-proxy api_routes
    const currentPath = window.location.pathname + window.location.search;
    const signInUrl = `/oauth2/sign_in?rd=${encodeURIComponent(currentPath)}`;
    
    console.log('Navigating to OAuth2 proxy sign-in endpoint:', signInUrl);
    window.location.href = signInUrl;
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
