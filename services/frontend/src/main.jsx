import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { errorTracker } from './utils/errorTracker.js';

// Runtime error tracker (global CLAUDE.md §26) — dev only
if (import.meta.env.DEV) {
  errorTracker.init();
  window.__errors = errorTracker;
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
