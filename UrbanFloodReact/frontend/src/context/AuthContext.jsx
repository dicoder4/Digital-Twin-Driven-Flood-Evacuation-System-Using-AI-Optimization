import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('flood_user');
    return saved ? JSON.parse(saved) : null;
  });

  useEffect(() => {
    if (user) {
      localStorage.setItem('flood_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('flood_user');
    }
  }, [user]);

  const login = (userData) => setUser(userData);

  const logout = () => {
    setUser(null);
    localStorage.removeItem('flood_user');
  };

  const isAuthenticated = !!user;
  const isAuthority = user?.role === 'authority';
  const isResearcher = user?.role === 'researcher';

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated, isAuthority, isResearcher }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
