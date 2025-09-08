import { useState } from 'react';
import {
  Box,
  Avatar,
  IconButton,
  Menu,
  MenuItem,
  Typography,
  ListItemIcon,
  Divider,
  Tooltip,
} from '@mui/material';
import { AccountCircle, Logout, Person } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

/**
 * User profile component with avatar and logout functionality
 * 
 * EP-0017 Implementation:
 * - Shows user info from JWT token claims
 * - Provides logout functionality that clears HTTP-only cookies
 * - Displays GitHub avatar and username
 */
export default function UserProfile() {
  const { user, logout } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    handleClose();
    await logout();
  };

  if (!user) {
    return null;
  }

  return (
    <Box>
      <Tooltip title={`${user.username} (${user.email})`}>
        <IconButton
          onClick={handleClick}
          size="small"
          sx={{ ml: 2 }}
          aria-controls={open ? 'user-menu' : undefined}
          aria-haspopup="true"
          aria-expanded={open ? 'true' : undefined}
        >
          <Avatar
            src={user.avatar_url}
            alt={user.username}
            sx={{ width: 32, height: 32 }}
          >
            <AccountCircle />
          </Avatar>
        </IconButton>
      </Tooltip>

      <Menu
        id="user-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        onClick={handleClose}
        PaperProps={{
          elevation: 3,
          sx: {
            overflow: 'visible',
            filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.32))',
            mt: 1.5,
            minWidth: 200,
            '&:before': {
              content: '""',
              display: 'block',
              position: 'absolute',
              top: 0,
              right: 14,
              width: 10,
              height: 10,
              bgcolor: 'background.paper',
              transform: 'translateY(-50%) rotate(45deg)',
              zIndex: 0,
            },
          },
        }}
        transformOrigin={{ horizontal: 'right', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
      >
        <Box sx={{ px: 2, py: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Avatar src={user.avatar_url} alt={user.username} sx={{ width: 40, height: 40 }}>
            <AccountCircle />
          </Avatar>
          <Box>
            <Typography variant="subtitle2" fontWeight="bold">
              {user.username}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {user.email}
            </Typography>
          </Box>
        </Box>

        <Divider />

        <MenuItem onClick={() => window.open(`https://github.com/${user.username}`, '_blank')}>
          <ListItemIcon>
            <Person fontSize="small" />
          </ListItemIcon>
          View GitHub Profile
        </MenuItem>

        <MenuItem onClick={handleLogout}>
          <ListItemIcon>
            <Logout fontSize="small" />
          </ListItemIcon>
          Logout
        </MenuItem>
      </Menu>
    </Box>
  );
}
