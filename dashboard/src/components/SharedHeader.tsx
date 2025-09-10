import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  Box,
} from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import LoginButton from './LoginButton';
import UserMenu from './UserMenu';
import { useAuth } from '../contexts/AuthContext';

interface SharedHeaderProps {
  title: string;
  showBackButton?: boolean;
  backUrl?: string;
  children?: ReactNode; // For additional controls like toggles, status indicators, etc.
}

export default function SharedHeader({ 
  title, 
  showBackButton = false, 
  backUrl = '/', 
  children 
}: SharedHeaderProps) {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const handleBackClick = () => {
    navigate(backUrl);
  };

  return (
    <AppBar 
      position="static" 
      elevation={0} 
      sx={{ 
        borderRadius: 1,
        background: 'linear-gradient(135deg, #1976d2 0%, #1565c0 100%)',
        boxShadow: '0 4px 16px rgba(25, 118, 210, 0.3)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        mb: 2,
      }}
    >
      <Toolbar>
        {/* Back Button */}
        {showBackButton && (
          <IconButton
            edge="start"
            color="inherit"
            aria-label="back"
            onClick={handleBackClick}
            sx={{ 
              mr: 2,
              background: 'rgba(255, 255, 255, 0.1)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: 2,
              transition: 'all 0.2s ease',
              '&:hover': {
                background: 'rgba(255, 255, 255, 0.2)',
                transform: 'translateY(-1px)',
                boxShadow: '0 4px 12px rgba(255, 255, 255, 0.2)',
              }
            }}
          >
            <ArrowBack />
          </IconButton>
        )}
        
        {/* Logo and Title */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexGrow: 1 }}>
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            width: 40,
            height: 40,
            borderRadius: 2,
            background: 'rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(10px)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15), 0 0 20px rgba(255, 255, 255, 0.1)',
            transition: 'all 0.3s ease',
            position: 'relative',
            overflow: 'hidden',
            '&:before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: '-100%',
              width: '100%',
              height: '100%',
              background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent)',
              animation: 'shimmer 2s infinite',
            },
            '&:hover': {
              background: 'rgba(255, 255, 255, 0.15)',
              transform: 'translateY(-2px) scale(1.05)',
              boxShadow: '0 8px 25px rgba(0, 0, 0, 0.2), 0 0 30px rgba(255, 255, 255, 0.2)',
              '&:before': {
                left: '100%',
              }
            },
            '@keyframes shimmer': {
              '0%': { left: '-100%' },
              '100%': { left: '100%' },
            }
          }}>
            <img 
              src="/tarsy-logo.png" 
              alt="Tarsy Logo" 
              style={{ 
                height: '28px', 
                width: 'auto', 
                borderRadius: '3px',
                filter: 'drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1))'
              }} 
            />
          </Box>
          <Typography 
            variant="h5" 
            component="div"
            sx={{
              fontWeight: 600,
              letterSpacing: '-0.5px',
              textShadow: '0 1px 2px rgba(0, 0, 0, 0.1)',
              background: 'linear-gradient(45deg, #ffffff 0%, rgba(255, 255, 255, 0.9) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              // Fallback for browsers that don't support background-clip: text
              color: 'white',
            }}
          >
            {title}
          </Typography>
        </Box>
        
        {/* Additional Controls (passed as children) */}
        {children}
        
        {/* Authentication Elements */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 2 }}>
          {!isAuthenticated && !authLoading && (
            <LoginButton size="medium" />
          )}
          
          {isAuthenticated && !authLoading && (
            <UserMenu />
          )}
        </Box>
      </Toolbar>
    </AppBar>
  );
}
