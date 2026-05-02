import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Droplets, ShieldAlert, Navigation, Map, Eye, EyeOff, ExternalLink, Mail, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

const labelStyle = { display: 'block', fontSize: '0.82rem', fontWeight: 600, color: '#475569', marginBottom: '6px' };
const inputStyle = { width: '100%', padding: '11px 16px', fontSize: '0.9rem', border: '2px solid #e2e8f0', borderRadius: '10px', outline: 'none', color: '#1e293b', transition: 'border-color 0.2s', background: 'white', boxSizing: 'border-box' };
const eyeBtnStyle = { position: 'absolute', top: 0, right: '12px', bottom: 0, display: 'flex', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 0 };

function FeatureCard({ icon, title, desc }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '12px 14px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px' }}>
      <div style={{ background: 'rgba(30,58,138,0.5)', padding: '8px', borderRadius: '10px', display: 'flex', flexShrink: 0 }}>{icon}</div>
      <div>
        <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600, color: '#e0edff' }}>{title}</h3>
        <p style={{ margin: '3px 0 0', fontSize: '0.8rem', color: 'rgba(191,219,254,0.7)', lineHeight: 1.4 }}>{desc}</p>
      </div>
    </div>
  );
}

const LoginPage = () => {
  const [isRegistering, setIsRegistering] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ username: '', password: '', confirmPassword: '', name: '', email: '', phone: '', address: '', role: 'authority' });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isFirstVisit, setIsFirstVisit] = useState(false);
  const { login } = useAuth();
  const { lang, toggle: toggleLang } = useLanguage();
  const navigate = useNavigate();

  useEffect(() => { const visited = localStorage.getItem('hasVisitedBefore'); if (!visited) { setIsFirstVisit(true); localStorage.setItem('hasVisitedBefore', 'true'); } }, []);
  const handleInputChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleAuth = async (e) => {
    e.preventDefault(); setError(null);
    if (isRegistering) {
      if (formData.password !== formData.confirmPassword) { setError("Passwords do not match."); return; }
      const pwd = formData.password;
      if (pwd.length < 8 || !/[A-Z]/.test(pwd) || !/\d/.test(pwd) || !/[!@#$%^&*(),.?":{}|<>]/.test(pwd)) { setError("Password must be at least 8 characters, with 1 uppercase, 1 number, and 1 special character."); return; }
    }
    setLoading(true);
    const endpoint = isRegistering ? 'register' : 'login';
    const payload = isRegistering ? formData : { username: formData.username, password: formData.password };
    try {
      const response = await fetch(`http://localhost:8000/auth/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || `${isRegistering ? 'Registration' : 'Login'} failed`); }
      const responseData = await response.json(); login(responseData.user); navigate('/');
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  };

  const handleDemoLogin = async (role) => {
    setError(null); setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/auth/demo-login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role }) });
      if (!response.ok) throw new Error('Demo login failed');
      const responseData = await response.json(); login(responseData.user); navigate('/');
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  };

  return (
    <div style={{ height: '100vh', display: 'flex', fontFamily: "'Inter', sans-serif", background: '#f8fafc', overflow: 'hidden' }}>
      {/* Language toggle — fixed top-right */}
      <button onClick={toggleLang} style={{ position: 'fixed', top: '16px', right: '16px', zIndex: 9999, fontSize: '12px', fontWeight: 700, padding: '5px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', background: 'white', color: '#334155', cursor: 'pointer', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
        {t('lang_toggle', lang)}
      </button>
      {/* Left Hero */}
      <div style={{ display: 'none', width: '50%', background: 'linear-gradient(145deg, #1e3a8a 0%, #1d4ed8 50%, #2563eb 100%)', position: 'relative', overflow: 'hidden' }} className="login-hero-panel">
        <div style={{ position: 'absolute', bottom: '-80px', left: '-60px', width: '320px', height: '320px', borderRadius: '50%', background: 'rgba(59,130,246,0.15)', filter: 'blur(60px)' }} />
        <div style={{ position: 'absolute', top: '60px', right: '-40px', width: '240px', height: '240px', borderRadius: '50%', background: 'rgba(96,165,250,0.12)', filter: 'blur(50px)' }} />
        <div style={{ position: 'relative', zIndex: 10, color: 'white', display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%', padding: '3rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '1.5rem' }}>
            <div style={{ background: 'white', padding: '10px', borderRadius: '16px', boxShadow: '0 4px 20px rgba(0,0,0,0.15)', display: 'flex' }}>
              <Droplets size={32} color="#2563eb" />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: '2.2rem', fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.1 }}>{t('login_title', lang)}</h1>
              <div style={{ fontSize: '0.85rem', color: 'rgba(191,219,254,0.9)', fontWeight: 500, marginTop: '2px' }}>{t('login_subtitle', lang)}</div>
            </div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '10px', padding: '12px 16px', marginBottom: '1.5rem' }}>
            <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#e0edff' }}>{t('login_city', lang)}</div>
            <div style={{ fontSize: '0.82rem', color: 'rgba(191,219,254,0.75)', marginTop: '3px' }}>ಬೆಂಗಳೂರು ನಗರ ಪ್ರವಾಹ ಸ್ಥಳಾಂತರ ವ್ಯವಸ್ಥೆ</div>
          </div>
          <p style={{ color: 'rgba(191,219,254,0.85)', fontSize: '1rem', lineHeight: 1.65, marginBottom: '2rem', maxWidth: '480px' }}>
            A simulation platform for urban planners and disaster authorities — integrating environmental data, physics-based flood modeling, and advanced AI optimization for life-saving evacuation strategies.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '2rem' }}>
            <FeatureCard icon={<Map size={20} color="#93c5fd" />} title={t('feature_hifi', lang)} desc={t('feature_hifi_desc', lang)} />
            <FeatureCard icon={<Navigation size={20} color="#93c5fd" />} title={t('feature_ai', lang)} desc={t('feature_ai_desc', lang)} />
            <FeatureCard icon={<ShieldAlert size={20} color="#93c5fd" />} title={t('feature_resource', lang)} desc={t('feature_resource_desc', lang)} />
          </div>
          <div style={{ marginTop: 'auto', paddingTop: '1.5rem', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <a href="https://github.com/dicoder4/Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#93c5fd', fontSize: '0.85rem', fontWeight: 600, textDecoration: 'none' }}><ExternalLink size={14} /> {t('learn_more', lang)}</a>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'rgba(191,219,254,0.6)', fontSize: '0.8rem' }}>
              <Mail size={13} /><a href="mailto:cryptkeep7@gmail.com" style={{ color: 'rgba(191,219,254,0.7)', textDecoration: 'none' }}>cryptkeep7@gmail.com</a>
            </div>
          </div>
        </div>
      </div>

      {/* Right Form */}
      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '2rem', overflowY: 'auto' }} className="login-form-panel">
        <div style={{ maxWidth: '520px', width: '100%', margin: 'auto 0' }}>
          <div className="login-mobile-header" style={{ display: 'none', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '2rem' }}>
            <div style={{ background: '#2563eb', padding: '8px', borderRadius: '12px', display: 'flex' }}><Droplets size={24} color="white" /></div>
            <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800, color: '#1e293b' }}>{t('login_title', lang)}</h1>
          </div>
          <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
            <h2 style={{ fontSize: '2rem', fontWeight: 800, color: '#1e293b', marginBottom: '0.5rem', letterSpacing: '-0.02em' }}>{isRegistering ? t('create_account', lang) : (isFirstVisit ? t('welcome', lang) : t('welcome_back', lang))}</h2>
            <p style={{ color: '#64748b', fontSize: '1rem' }}>{isRegistering ? t('register_subtitle', lang) : t('signin_subtitle', lang)}</p>
          </div>
          {error && (<div style={{ marginBottom: '1.5rem', background: '#fef2f2', border: '1px solid #fecaca', padding: '12px 16px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}><ShieldAlert size={18} color="#ef4444" style={{ flexShrink: 0 }} /><p style={{ margin: 0, fontSize: '0.85rem', color: '#b91c1c', fontWeight: 500 }}>{error}</p></div>)}

          <form onSubmit={handleAuth} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {isRegistering && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('account_type', lang)}</label><select name="role" value={formData.role} onChange={handleInputChange} style={inputStyle}><option value="authority">{t('dra_option', lang)}</option><option value="researcher">{t('researcher_option', lang)}</option></select></div>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('choose_username', lang)}</label><input type="text" name="username" required value={formData.username} onChange={handleInputChange} style={inputStyle} placeholder={t('enter_username', lang)} /></div>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('full_name', lang)}</label><input type="text" name="name" required value={formData.name} onChange={handleInputChange} style={inputStyle} placeholder={t('enter_full_name', lang)} /></div>
                <div><label style={labelStyle}>{t('email', lang)}</label><input type="email" name="email" required value={formData.email} onChange={handleInputChange} style={inputStyle} placeholder={t('enter_email', lang)} /></div>
                <div><label style={labelStyle}>{t('phone', lang)}</label><input type="tel" name="phone" required value={formData.phone} onChange={handleInputChange} style={inputStyle} placeholder="+91..." /></div>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('address', lang)}</label><input type="text" name="address" required value={formData.address} onChange={handleInputChange} style={inputStyle} placeholder={t('enter_address', lang)} /></div>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('password', lang)}</label><div style={{ position: 'relative' }}><input type={showPassword ? "text" : "password"} name="password" required value={formData.password} onChange={handleInputChange} style={{ ...inputStyle, paddingRight: '44px' }} placeholder={t('enter_password', lang)} /><button type="button" onClick={() => setShowPassword(!showPassword)} style={eyeBtnStyle}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
                <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>{t('confirm_password', lang)}</label><div style={{ position: 'relative' }}><input type={showPassword ? "text" : "password"} name="confirmPassword" required value={formData.confirmPassword} onChange={handleInputChange} style={{ ...inputStyle, paddingRight: '44px' }} placeholder={t('confirm_password_ph', lang)} /><button type="button" onClick={() => setShowPassword(!showPassword)} style={eyeBtnStyle}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
              </div>
            )}
            {!isRegistering && (<>
              <div><label style={{ ...labelStyle, fontSize: '0.95rem' }}>{t('username', lang)}</label><input type="text" name="username" required value={formData.username} onChange={handleInputChange} style={{ ...inputStyle, padding: '14px 18px', fontSize: '1rem', borderRadius: '14px' }} placeholder={t('enter_your_username', lang)} /></div>
              <div><label style={{ ...labelStyle, fontSize: '0.95rem' }}>{t('password', lang)}</label><div style={{ position: 'relative' }}><input type={showPassword ? "text" : "password"} name="password" required value={formData.password} onChange={handleInputChange} style={{ ...inputStyle, padding: '14px 18px', paddingRight: '48px', fontSize: '1rem', borderRadius: '14px' }} placeholder="••••••••" /><button type="button" onClick={() => setShowPassword(!showPassword)} style={eyeBtnStyle}>{showPassword ? <EyeOff size={20} /> : <Eye size={20} />}</button></div></div>
            </>)}
            <div style={{ paddingTop: '0.5rem' }}>
              <button type="submit" disabled={loading} style={{ width: '100%', background: loading ? '#93c5fd' : 'linear-gradient(135deg, #2563eb, #1d4ed8)', color: 'white', fontWeight: 700, padding: '14px', fontSize: '1rem', borderRadius: '14px', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', boxShadow: '0 4px 14px rgba(37,99,235,0.3)', transition: 'all 0.2s', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                {loading ? t('processing_btn', lang) : (isRegistering ? t('register_btn', lang) : t('sign_in', lang))}{!loading && <ArrowRight size={18} />}
              </button>
            </div>
            <div style={{ textAlign: 'center' }}>
              <p style={{ color: '#64748b', fontSize: '0.9rem', margin: 0 }}>{isRegistering ? t('already_account', lang) : t('no_account', lang)}<button type="button" onClick={() => { setIsRegistering(!isRegistering); setError(null); }} style={{ marginLeft: '6px', fontWeight: 700, color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.9rem', padding: 0 }}>{isRegistering ? t('sign_in', lang) : t('register_link', lang)}</button></p>
            </div>
          </form>

          <div style={{ marginTop: '2rem' }}>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }} /><span style={{ padding: '0 14px', color: '#94a3b8', fontWeight: 600, fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{t('sandbox_access', lang)}</span><div style={{ flex: 1, height: '1px', background: '#e2e8f0' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <button type="button" onClick={() => handleDemoLogin('authority')} disabled={loading} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 12px', border: '2px solid #fed7aa', background: 'white', borderRadius: '12px', cursor: 'pointer', transition: 'all 0.2s' }}>
                <div style={{ background: '#fff7ed', padding: '8px', borderRadius: '50%', display: 'flex', marginBottom: '6px' }}><ShieldAlert size={18} color="#f97316" /></div>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#9a3412' }}>{t('authority_role', lang)}</span>
                <span style={{ fontSize: '0.7rem', color: '#c2410c', marginTop: '2px' }}>{t('dra_command', lang)}</span>
              </button>
              <button type="button" onClick={() => handleDemoLogin('researcher')} disabled={loading} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 12px', border: '2px solid #ddd6fe', background: 'white', borderRadius: '12px', cursor: 'pointer', transition: 'all 0.2s' }}>
                <div style={{ background: '#f5f3ff', padding: '8px', borderRadius: '50%', display: 'flex', marginBottom: '6px' }}><Navigation size={18} color="#7c3aed" /></div>
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#5b21b6' }}>{t('researcher_role', lang)}</span>
                <span style={{ fontSize: '0.7rem', color: '#6d28d9', marginTop: '2px' }}>{t('full_sim_lab', lang)}</span>
              </button>
            </div>
          </div>
          <p style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>{t('footer_copy', lang)}</p>
        </div>
      </div>

      <style>{`
        @media (min-width: 1024px) { .login-hero-panel { display: flex !important; } .login-form-panel { width: 50% !important; } .login-mobile-header { display: none !important; } }
        @media (max-width: 1023px) { .login-mobile-header { display: flex !important; } }
      `}</style>
    </div>
  );
};

export default LoginPage;