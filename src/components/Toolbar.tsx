import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from './Button';

export const Toolbar: React.FC = () => {
  const { user, login, logout } = useAuth();
  const [imageError, setImageError] = useState(false);

  const handleImageError = () => {
    setImageError(true);
  };

  // Fallback image (using a generic placeholder or initial)
  const fallbackImage = 'https://ui-avatars.com/api/?name=' + (user?.name || 'User');

  return (
    <div className="toolbar" style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '1rem',
      backgroundColor: '#f8f9fa',
      borderBottom: '1px solid #dee2e6',
      marginBottom: '2rem'
    }}>
      <div className="logo" style={{ fontWeight: 'bold', fontSize: '1.2rem' }}>
        Tubes
      </div>

      <div className="auth-section" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {user ? (
          <>
            <div className="user-info" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <img
                src={!imageError && user.picture ? user.picture : fallbackImage}
                alt={user.name}
                onError={handleImageError}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  objectFit: 'cover'
                }}
              />
              <span>{user.name}</span>
            </div>
            <Button label="Logout" onClick={logout} variant="secondary" />
          </>
        ) : (
          <Button label="Login" onClick={login} variant="primary" />
        )}
      </div>
    </div>
  );
};
