import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Toolbar } from './components/Toolbar';
import { VideoGrid } from './components/VideoGrid';
import { Sidebar } from './components/Sidebar';
import { VideoPage } from './pages/VideoPage';
import { ChannelPage } from './pages/ChannelPage';
import { useAuth } from './context/AuthContext';

function App() {
  const { loading } = useAuth();

  // If loading, we show a loading indicator.
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 font-roboto pt-14 pl-[72px] md:pl-52">
      <Toolbar />
      <Sidebar />
      <main className="p-6 bg-gray-50 min-h-[calc(100vh-56px)]">
        <Routes>
          <Route path="/" element={<VideoGrid />} />
          <Route path="/video/:id" element={<VideoPage />} />
          <Route path="/channel/:id" element={<ChannelPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
