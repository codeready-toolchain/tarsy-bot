import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Container, 
  Box, 
  Typography, 
  Button, 
  Paper,
  AppBar,
  Toolbar,
} from '@mui/material';
import { Home as HomeIcon, ErrorOutline as ErrorIcon } from '@mui/icons-material';

/**
 * 404 Not Found page component
 * Maintains consistent styling with the main dashboard while providing clear navigation back
 */
function NotFoundPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const handleGoToDashboard = () => {
    navigate('/');
  };

  return (
    <Container maxWidth={false} sx={{ px: 2 }}>
      {/* AppBar matching dashboard style */}
      <AppBar 
        position="static" 
        elevation={0} 
        sx={{ 
          borderRadius: 1,
          background: 'linear-gradient(135deg, #1976d2 0%, #1565c0 100%)',
          boxShadow: '0 4px 16px rgba(25, 118, 210, 0.3)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          mb: 4
        }}
      >
        <Toolbar>
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            width: 40,
            height: 40,
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.15)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            mr: 2,
            boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.3)'
          }}>
            <ErrorIcon sx={{ 
              fontSize: 20, 
              color: '#ffffff',
              filter: 'drop-shadow(0 1px 2px rgba(0, 0, 0, 0.3))'
            }} />
          </Box>
          
          <Typography 
            variant="h6" 
            component="h1" 
            sx={{ 
              flexGrow: 1,
              color: '#ffffff',
              fontWeight: 600,
              letterSpacing: '0.5px',
              textShadow: '0 1px 2px rgba(0, 0, 0, 0.3)',
            }}
          >
            Page Not Found
          </Typography>
        </Toolbar>
      </AppBar>

      {/* Main content */}
      <Box 
        display="flex" 
        flexDirection="column" 
        alignItems="center" 
        justifyContent="center" 
        minHeight="50vh"
      >
        <Paper 
          elevation={0}
          sx={{ 
            p: 6, 
            textAlign: 'center',
            maxWidth: 500,
            width: '100%',
            background: 'rgba(255, 255, 255, 0.9)',
            backdropFilter: 'blur(10px)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            borderRadius: 2,
          }}
        >
          {/* Large 404 */}
          <Typography 
            variant="h1" 
            component="h2" 
            sx={{ 
              fontSize: '6rem',
              fontWeight: 700,
              color: 'primary.main',
              opacity: 0.1,
              mb: -2,
              userSelect: 'none'
            }}
          >
            404
          </Typography>
          
          {/* Main message */}
          <Typography 
            variant="h4" 
            component="h2" 
            gutterBottom
            sx={{ 
              color: 'text.primary',
              fontWeight: 500,
              mb: 2
            }}
          >
            Oops! Page not found
          </Typography>
          
          {/* URL info */}
          <Typography 
            variant="body1" 
            color="text.secondary" 
            sx={{ mb: 4 }}
          >
            The page <code style={{ 
              background: '#f5f5f5', 
              padding: '2px 6px', 
              borderRadius: '4px',
              fontFamily: 'monospace'
            }}>{location.pathname}</code> doesn't exist.
          </Typography>
          
          {/* Action button */}
          <Button
            variant="contained"
            size="large"
            startIcon={<HomeIcon />}
            onClick={handleGoToDashboard}
            sx={{ 
              px: 4,
              py: 1.5,
              background: 'linear-gradient(135deg, #1976d2 0%, #1565c0 100%)',
              boxShadow: '0 4px 16px rgba(25, 118, 210, 0.3)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              transition: 'all 0.2s ease',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: '0 6px 20px rgba(25, 118, 210, 0.4)',
              }
            }}
          >
            Go to Dashboard
          </Button>
        </Paper>
      </Box>
    </Container>
  );
}

export default NotFoundPage;
