/**
 * ================================================================================
 *   frontend/src/main.jsx  â€”  REACT APPLICATION ENTRY POINT
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
 *   â€¢ App.tsx       â†’ the root component that decides which page to show
 *   â€¢ index.css     â†’ global styles, CSS variables, markdown theme, animations
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

// ðŸŸ¢ BEGINNER: React is the core library. ReactDOM is the package that renders React components into the browser's DOM (the actual HTML page).
import React from 'react'
import ReactDOM from 'react-dom/client'

// ðŸŸ¢ BEGINNER: Import the root component of our app. This is the top-level component that decides which page to show.
import App from './App.tsx'

// ðŸŸ¢ BEGINNER: Import global CSS styles (fonts, colors, animations) that apply to the whole app.
import '@tabler/icons-webfont/dist/tabler-icons.min.css'
import './index.css'

// ðŸŸ¢ BEGINNER: Find the <div id="root"></div> element in index.html and create a React "root" there.
// This is where our entire React application will be drawn on the screen.
const root = ReactDOM.createRoot(document.getElementById('root'))

// ðŸŸ¢ BEGINNER: Render the App component inside the root div.
// NOTE: React.StrictMode was removed because it double-mounts components in dev,
// which breaks SSE streaming (the first mount's stream gets cancelled, causing
// partial content). In production builds, StrictMode has no effect anyway.
root.render(
  <App />,
)
