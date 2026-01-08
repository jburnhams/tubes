import React from 'react';
import { Toolbar } from './components/Toolbar';
import { ChannelGrid } from './components/ChannelGrid';
import { useAuth } from './context/AuthContext';

function App() {
  const { loading } = useAuth();

  // If loading, we show a loading indicator.
  // Note: If authentication fails, AuthContext will handle the redirect.
  // We keep the app in a loading state or show a loader until then.
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Toolbar />
      <div className="app">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center mb-10">
            <h1 className="text-4xl font-extrabold text-gray-900 sm:text-5xl sm:tracking-tight lg:text-6xl">
              Tubes
            </h1>
            <p className="mt-5 max-w-xl mx-auto text-xl text-gray-500">
              Discover your favorite YouTube channels.
            </p>
          </div>

          <ChannelGrid />
        </div>
      </div>
    </div>
  );
}

export default App;
