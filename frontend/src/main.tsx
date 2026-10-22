import './styles/theme.css'
import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { routerFuture } from './kit/router'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter {...routerFuture}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
