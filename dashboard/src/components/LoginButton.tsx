import { Button } from '@mui/material';
import { authService } from '../services/auth';

interface LoginButtonProps {
  variant?: 'contained' | 'outlined' | 'text';
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export default function LoginButton({ variant = 'contained', size = 'medium', className }: LoginButtonProps) {
  const handleLogin = () => {
    console.log('Manual login button clicked');
    authService.redirectToLogin();
  };

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleLogin}
      className={className}
      sx={{ 
        minWidth: 'auto', // Prevent button from being too wide
        whiteSpace: 'nowrap' // Keep text on one line
      }}
    >
      Login with GitHub
    </Button>
  );
}
