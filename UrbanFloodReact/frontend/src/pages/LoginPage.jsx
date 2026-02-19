import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import { Droplets, LogIn, UserPlus, Gamepad2, FlaskConical, Building2, User } from 'lucide-react';

export default function LoginPage() {
  const [tab, setTab] = useState('login');
  const [form, setForm] = useState({ username: '', password: '', name: '', email: '', phone: '', role: 'researcher' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/login', { username: form.username, password: form.password });
      login(res.data.user);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 6) { setError('Password must be at least 6 characters'); return; }
    setLoading(true);
    try {
      const res = await api.post('/auth/register', form);
      login(res.data.user);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = async (role) => {
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/demo-login', { role });
      login(res.data.user);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Demo login failed');
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'login', label: 'Login', icon: LogIn },
    { id: 'register', label: 'Register', icon: UserPlus },
    { id: 'demo', label: 'Demo Access', icon: Gamepad2 },
  ];

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-900 via-blue-800 to-indigo-900">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="flex justify-center mb-3">
            <div className="bg-blue-100 p-3 rounded-full">
              <Droplets className="w-8 h-8 text-blue-600" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-gray-800">🌊 Emergency Flood Evacuation System</h1>
          <p className="text-sm text-gray-500 mt-1">Secure Access Portal</p>
        </div>

        {/* Tabs */}
        <div className="flex mb-6 bg-gray-100 rounded-lg p-1">
          {tabs.map(t => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => { setTab(t.id); setError(''); }}
                className={`flex-1 py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all
                  ${tab === t.id ? 'bg-white shadow text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}>
                <Icon size={14} /> {t.label}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">{error}</div>
        )}

        {/* ---- LOGIN TAB ---- */}
        {tab === 'login' && (
          <form onSubmit={handleLogin} className="space-y-4">
            <input name="username" value={form.username} onChange={handleChange} placeholder="Username"
              className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none" />
            <input name="password" type="password" value={form.password} onChange={handleChange} placeholder="Password"
              className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none" />
            <div className="flex gap-3">
              <button disabled={loading} type="submit"
                className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg transition-all disabled:opacity-50">
                {loading ? 'Signing in...' : '🔓 Login'}
              </button>
              <button disabled={loading} type="button" onClick={() => handleDemoLogin('guest')}
                className="flex-1 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-lg transition-all disabled:opacity-50">
                👤 Guest Access
              </button>
            </div>
          </form>
        )}

        {/* ---- REGISTER TAB ---- */}
        {tab === 'register' && (
          <form onSubmit={handleRegister} className="space-y-3">
            <input name="username" value={form.username} onChange={handleChange} placeholder="Choose Username"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none" />
            <input name="name" value={form.name} onChange={handleChange} placeholder="Full Name"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none" />
            <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="Email Address"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none" />
            <input name="phone" value={form.phone} onChange={handleChange} placeholder="Phone (+91XXXXXXXXXX)"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none" />
            <input name="password" type="password" value={form.password} onChange={handleChange} placeholder="Password (min 6 chars)"
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none" />
            <select name="role" value={form.role} onChange={handleChange}
              className="w-full px-4 py-2.5 rounded-lg border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none">
              <option value="researcher">🔬 Researcher (Full Access)</option>
              <option value="authority">🏢 Disaster Response Authority</option>
            </select>
            <button disabled={loading} type="submit"
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg transition-all disabled:opacity-50">
              {loading ? 'Creating account...' : '📝 Create Account'}
            </button>
          </form>
        )}

        {/* ---- DEMO ACCESS TAB ---- */}
        {tab === 'demo' && (
          <div className="space-y-4">
            <p className="text-sm text-blue-600 bg-blue-50 p-3 rounded-lg">
              ℹ️ Use these demo accounts to explore the system without credentials:
            </p>

            <div className="grid grid-cols-2 gap-3">
              {/* Researcher Demo */}
              <div className="border border-gray-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <FlaskConical size={16} className="text-purple-600" />
                  <span className="font-bold text-sm text-gray-800">Researcher</span>
                </div>
                <p className="text-xs text-gray-500">Full system access</p>
                <p className="text-[10px] text-gray-400">researcher / research123</p>
                <button onClick={() => handleDemoLogin('researcher')} disabled={loading}
                  className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-bold rounded-lg transition-all disabled:opacity-50">
                  🔬 Login as Researcher
                </button>
              </div>

              {/* Authority Demo */}
              <div className="border border-gray-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Building2 size={16} className="text-orange-600" />
                  <span className="font-bold text-sm text-gray-800">Authority</span>
                </div>
                <p className="text-xs text-gray-500">Disaster response</p>
                <p className="text-[10px] text-gray-400">authority / authority123</p>
                <button onClick={() => handleDemoLogin('authority')} disabled={loading}
                  className="w-full py-2 bg-orange-600 hover:bg-orange-700 text-white text-sm font-bold rounded-lg transition-all disabled:opacity-50">
                  🏢 Login as Authority
                </button>
              </div>
            </div>

            {/* Guest */}
            <button onClick={() => handleDemoLogin('guest')} disabled={loading}
              className="w-full py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
              <User size={16} /> 👤 Guest Access (Citizen)
            </button>
          </div>
        )}

        <p className="text-[10px] text-gray-400 text-center mt-6">
          🚨 Emergency Contact: 112 | 🚓 Police: 100 | 🚑 Medical: 108
        </p>
      </div>
    </div>
  );
}
