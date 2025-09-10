import { IconButton, Tooltip } from '@mui/material';
import { Login } from '@mui/icons-material';
import { authService } from '../services/auth';

interface LoginButtonProps {
  variant?: 'contained' | 'outlined' | 'text';
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export default function LoginButton({ size = 'medium', className }: LoginButtonProps) {
  const handleLogin = () => {
    console.log('Manual login button clicked');
    authService.redirectToLogin();
  };

  return (
    <Tooltip title="Login with GitHub">
      <IconButton
        size={size}
        onClick={handleLogin}
        className={className}
        sx={{ 
          color: 'white',
          '&:hover': {
            backgroundColor: 'rgba(255, 255, 255, 0.1)',
          }
        }}
      >
        <Login />
      </IconButton>
    </Tooltip>
  );
}
