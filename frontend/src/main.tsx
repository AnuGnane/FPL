import './styles/theme.css'
import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { routerFuture } from './kit/router'
import App from './App'

const root = document.getElementById('root')
if (!root) throw new Error('index.html has no #root element')

createRoot(root).render(
  <React.StrictMode>
    <BrowserRouter {...routerFuture}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
