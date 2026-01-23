import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from './Button';

export const Toolbar: React.FC = () => {
  const { user, login, logout } = useAuth();
  const navigate = useNavigate();
  const [imageError, setImageError] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  const handleImageError = () => {
    setImageError(true);
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    };

    if (isMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isMenuOpen]);

  const handleSearch = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const handleSearchKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  // Fallback image
  const fallbackImage = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(user?.name || 'User');
  const profileImage = !imageError && user?.profile_picture ? user.profile_picture : fallbackImage;

  return (
    <header className="fixed top-0 left-0 right-0 h-14 bg-white flex justify-between items-center px-4 md:px-6 z-[300] border-b border-gray-200 font-roboto">
      <div className="flex items-center">
        <div className="hover:bg-gray-100 p-2 rounded-full cursor-pointer mr-1 md:mr-4 hidden md:block">
          <img className="h-6" src="/icons/hamburger-menu.svg" alt="Menu" />
        </div>
        <a href="/" className="flex items-center" title="YouTube Home">
          <img className="h-5 md:h-6 cursor-pointer" src="/icons/youtube-logo.svg" alt="YouTube Logo" />
        </a>
      </div>

      <div className="flex-1 max-w-[600px] ml-10 md:ml-16 mr-4 md:mr-9 hidden sm:flex items-center">
        <input
          className="flex-1 h-9 md:h-10 px-3 text-base border border-gray-300 rounded-l-[2px] shadow-inner focus:outline-none focus:border-blue-500 placeholder-gray-500"
          type="text"
          placeholder="Search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyPress={handleSearchKeyPress}
        />
        <button
          onClick={handleSearch}
          className="h-9 md:h-10 w-16 bg-gray-50 border border-l-0 border-gray-300 rounded-r-[2px] cursor-pointer hover:bg-gray-100 flex justify-center items-center relative group"
        >
          <img className="h-6 mt-1" src="/icons/search.svg" alt="Search" />
          <div className="absolute bg-gray-600 text-white text-xs py-1 px-2 rounded bottom-[-35px] opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none whitespace-nowrap z-[400]">
            Search
          </div>
        </button>
        <button
          className="h-10 w-10 ml-2 rounded-full bg-gray-50 cursor-pointer hover:bg-gray-200 flex justify-center items-center relative group border-none"
        >
          <img className="h-6" src="/icons/voice-search-icon.svg" alt="Voice Search" />
          <div className="absolute bg-gray-600 text-white text-xs py-1 px-2 rounded bottom-[-35px] opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none whitespace-nowrap z-[400]">
            Search with your voice
          </div>
        </button>
      </div>

      <div className="flex items-center shrink-0 w-[180px] justify-between">
        <Link to="/channels" className="relative group cursor-pointer hidden sm:block">
          <img className="h-6" src="/icons/upload.svg" alt="Create" />
          <div className="absolute bg-gray-600 text-white text-xs py-1 px-2 rounded bottom-[-35px] left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none whitespace-nowrap z-[400]">
            Create
          </div>
        </Link>
        <Link to="/channels" className="relative group cursor-pointer hidden sm:block">
          <img className="h-6" src="/icons/youtube-apps.svg" alt="Apps" />
          <div className="absolute bg-gray-600 text-white text-xs py-1 px-2 rounded bottom-[-35px] left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none whitespace-nowrap z-[400]">
            YouTube apps
          </div>
        </Link>
        <div className="relative group cursor-pointer hidden sm:block">
          <div className="relative">
            <img className="h-6" src="/icons/notifications.svg" alt="Notifications" />
            <div className="absolute -top-1 -right-1 bg-red-600 text-white text-[10px] px-1 rounded-full border-2 border-white">3</div>
          </div>
          <div className="absolute bg-gray-600 text-white text-xs py-1 px-2 rounded bottom-[-35px] left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none whitespace-nowrap z-[400]">
            Notifications
          </div>
        </div>

        <div className="ml-2 relative" ref={menuRef}>
          {user ? (
            <>
              <button onClick={toggleMenu} className="focus:outline-none">
                <img
                  src={profileImage}
                  alt={user.name}
                  onError={handleImageError}
                  className="h-8 w-8 rounded-full object-cover cursor-pointer"
                  title={`Logged in as ${user.name}`}
                />
              </button>
              {isMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-white border border-gray-200 shadow-xl rounded-lg overflow-hidden z-[500]">
                  <div className="p-4 flex items-start border-b border-gray-200 bg-gray-50">
                    <img
                      src={profileImage}
                      alt={user.name}
                      className="h-10 w-10 rounded-full object-cover mr-3 flex-shrink-0"
                    />
                    <div className="overflow-hidden">
                      <p className="font-medium text-gray-900 truncate" title={user.name}>{user.name}</p>
                      <p className="text-sm text-gray-600 truncate" title={user.email}>{user.email}</p>
                      {user.is_admin && (
                        <span className="inline-block mt-1 px-2 py-0.5 text-xs text-blue-700 bg-blue-100 rounded-full">
                          Admin
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="py-2">
                    <div className="px-4 py-2 text-xs text-gray-500">
                      Last login: {new Date(user.last_login_at).toLocaleDateString()}
                    </div>
                    <div className="border-t border-gray-100 my-1"></div>
                    <button
                      onClick={() => {
                        setIsMenuOpen(false);
                        logout();
                      }}
                      className="w-full text-left px-4 py-3 text-sm text-gray-700 hover:bg-gray-100 flex items-center"
                    >
                      <span className="mr-2">🚪</span> Sign out
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div onClick={login} className="text-blue-600 border border-blue-600 px-3 py-1 uppercase text-sm font-medium rounded-sm cursor-pointer hover:bg-blue-50">
              Sign in
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
