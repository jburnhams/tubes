// The app's entry: bundled faces, the stylesheet, then Strata's providers in the order every Strata
// app nests them. ThemeProvider owns the `.dark` class (no matchMedia listener here; index.html's
// inline script sets it before first paint), StrataQueryProvider gives every useLoad a query
// client with Strata's defaults (one retry, 30 s stale, no refetch on focus), and the router is
// built from the same route tree the tests render (routes.tsx).
import '@fontsource-variable/source-sans-3'
import '@fontsource-variable/jetbrains-mono'
import './styles/app.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { StrataQueryProvider, ThemeProvider } from 'strata-react'
import { BASE } from './api'
import { routes } from './routes'

const router = createBrowserRouter(routes, { basename: BASE || '/' })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <StrataQueryProvider>
        <RouterProvider router={router} />
      </StrataQueryProvider>
    </ThemeProvider>
  </StrictMode>,
)
