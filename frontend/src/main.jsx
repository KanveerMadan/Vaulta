import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
// Fonts are bundled with the app (no third-party font requests)
import '@fontsource-variable/bricolage-grotesque/opsz.css'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './index.css'
import { keepFocusedFieldVisible } from './lib/keyboard'

keepFocusedFieldVisible()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)