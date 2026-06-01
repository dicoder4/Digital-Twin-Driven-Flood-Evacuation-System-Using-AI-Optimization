import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import LoginPage from './pages/LoginPage.jsx'
import SharedReportPage from './pages/SharedReportPage.jsx'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider } from './context/LanguageContext'
import { TutorialProvider } from './context/TutorialContext'

const PrivateRoute = ({ children }) => {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LanguageProvider>
    <AuthProvider>
    <TutorialProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/report/:reportId" element={<SharedReportPage />} />
          <Route 
            path="/*" 
            element={
              <PrivateRoute>
                <App />
              </PrivateRoute>
            } 
          />
        </Routes>
      </BrowserRouter>
    </TutorialProvider>
    </AuthProvider>
    </LanguageProvider>
  </StrictMode>,
)
