import React from 'react';
import { Button } from './components/Button';
import { Toolbar } from './components/Toolbar';
import { useCounter } from './hooks/useCounter';
import { useAuth } from './context/AuthContext';

function App() {
  const { count, increment, decrement, reset } = useCounter(0);
  const { loading } = useAuth();

  if (loading) {
    return <div className="app">Loading...</div>;
  }

  return (
    <>
      <Toolbar />
      <div className="app">
        <h1>Tubes</h1>

        <p>A minimal React + TypeScript app with comprehensive testing setup</p>

        <div className="counter-demo">
          <h2>Counter: {count}</h2>
          <div className="button-group">
            <Button label="Increment" onClick={increment} variant="primary" />
            <Button label="Decrement" onClick={decrement} variant="secondary" />
            <Button label="Reset" onClick={reset} variant="secondary" />
          </div>
        </div>
      </div>
    </>
  );
}

export default App;
