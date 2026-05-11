/**
 * ================================================================================
 *   frontend/src/main.jsx  —  REACT APPLICATION ENTRY POINT
 * ================================================================================
 *
 * PURPOSE:
 *   Bootstraps the React SPA. Creates the root DOM node, imports the global
 *   stylesheet (index.css), and mounts the <App /> component.
 *
 * WHY IT EXISTS:
 *   Vite (the build tool) needs a single entry file. This is it.
 *   `npm run dev` and `npm run build` both start here.
 *
 * CONNECTIONS TO OTHER FILES:
 *   • App.tsx       → the root component that decides which page to show
 *   • index.css     → global styles, CSS variables, markdown theme, animations
 *
 * STRICT MODE NOTE:
 *   <React.StrictMode> intentionally double-mounts components in development
 *   to detect side effects. This caused a real bug in DesignDocPage where
 *   the first mount's AbortController cancelled the second mount's SSE stream.
 *   The fix was using a ref (`currentEffectRef`) to track effect generations.
 *
 * PATTERN: Standard React 18 createRoot API
 * ================================================================================
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// Create a React root attached to the <div id="root"></div> in index.html
const root = ReactDOM.createRoot(document.getElementById('root'))

// Render the entire application tree inside StrictMode
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
