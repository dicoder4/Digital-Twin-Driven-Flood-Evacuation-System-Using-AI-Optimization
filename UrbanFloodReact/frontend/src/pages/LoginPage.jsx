import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Droplets, ShieldAlert, Navigation, Activity, Users, Map, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const LoginPage = () => {
  const [isRegistering, setIsRegistering] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    name: '',
    email: '',
    phone: '',
    address: '',
    role: 'authority',
  });
  
  // Backwards compatibility with existing logic
  const username = formData.username;
  const password = formData.password;
  
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isFirstVisit, setIsFirstVisit] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const visited = localStorage.getItem('hasVisitedBefore');
    if (!visited) {
      setIsFirstVisit(true);
      localStorage.setItem('hasVisitedBefore', 'true');
    }
  }, []);

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleAuth = async (e) => {
    e.preventDefault();
    setError(null);

    // Frontend validation for strong password
    if (isRegistering) {
      if (formData.password !== formData.confirmPassword) {
        setError("Passwords do not match.");
        return;
      }

      const pwd = formData.password;
      if (pwd.length < 8 || !/[A-Z]/.test(pwd) || !/\d/.test(pwd) || !/[!@#$%^&*(),.?":{}|<>]/.test(pwd)) {
        setError("Password must be at least 8 characters, with 1 uppercase, 1 number, and 1 special character.");
        return;
      }
    }

    setLoading(true);

    const endpoint = isRegistering ? 'register' : 'login';
    const payload = isRegistering 
      ? formData 
      : { username: formData.username, password: formData.password };

    try {
      const response = await fetch(`http://localhost:8000/auth/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `${isRegistering ? 'Registration' : 'Login'} failed`);
      }

      const responseData = await response.json();
      login(responseData.user);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = async (role) => {
    setError(null);
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8000/auth/demo-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      
      if (!response.ok) {
        throw new Error('Demo login failed');
      }

      const responseData = await response.json();
      login(responseData.user);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-slate-50 font-sans">
      {/* Left Side - Branding/Hero */}
      <div className="hidden lg:flex lg:w-1/2 bg-blue-600 relative overflow-hidden items-center justify-center p-12">
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-blue-700 to-blue-900 opacity-90"></div>
        <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-blue-500 opacity-20 blur-3xl"></div>
        <div className="absolute top-20 right-20 w-72 h-72 rounded-full bg-blue-400 opacity-20 blur-3xl"></div>
        
        <div className="relative z-10 text-white w-full max-w-lg">
          <div className="flex items-center gap-3 mb-10">
            <div className="bg-white p-3 rounded-2xl shadow-xl">
              <Droplets size={36} className="text-blue-600" />
            </div>
            <h1 className="text-5xl font-extrabold tracking-tight">Flood Evac AI</h1>
          </div>
          <h2 className="text-3xl font-semibold mb-6 text-blue-50 leading-snug">Digital Twin–Driven Evacuation System</h2>
          <p className="text-blue-200 text-xl mb-12 leading-relaxed">
            A dynamic simulation platform for urban planners and disaster authorities. Integrating real-time environmental data, physics-based flood modeling, and advanced AI optimization to generate dynamic, life-saving evacuation strategies.
          </p>
          <div className="space-y-6">
            <div className="flex items-start gap-4">
              <div className="bg-blue-800/40 p-3 rounded-xl border border-blue-400/20"><Map size={24} className="text-blue-300" /></div>
              <div>
                <h3 className="font-semibold text-lg text-blue-50">High-Fidelity Digital Twin</h3>
                <p className="text-blue-200/90 mt-1">Automatic generation of urban road networks and elevation models via OSM and SRTM data, rendered interactively with MapLibre.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="bg-blue-800/40 p-3 rounded-xl border border-blue-400/20"><Activity size={24} className="text-blue-300" /></div>
              <div>
                <h3 className="font-semibold text-lg text-blue-50">Physics-Based Flood Simulation</h3>
                <p className="text-blue-200/90 mt-1">Dynamic SWM-style modeling of flood propagation driven by historic or manual variable rainfall intensity and terrain topology.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="bg-blue-800/40 p-3 rounded-xl border border-blue-400/20"><Navigation size={24} className="text-blue-300" /></div>
              <div>
                <h3 className="font-semibold text-lg text-blue-50">Metaheuristic AI Routing</h3>
                <p className="text-blue-200/90 mt-1">Deploying Genetic Algorithms (GA), Ant Colony Optimization (ACO), and PSO synchronized with live TomTom traffic feeds.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="bg-blue-800/40 p-3 rounded-xl border border-blue-400/20"><Users size={24} className="text-blue-300" /></div>
              <div>
                <h3 className="font-semibold text-lg text-blue-50">Agentic GenAI Co-Pilot</h3>
                <p className="text-blue-200/90 mt-1">Dual FastMCP architecture powering an autonomous Expert Panel to synthesize the physics simulation into actionable NDRF directives.</p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="bg-blue-800/40 p-3 rounded-xl border border-blue-400/20"><ShieldAlert size={24} className="text-blue-300" /></div>
              <div>
                <h3 className="font-semibold text-lg text-blue-50">Multimodal Resource Management</h3>
                <p className="text-blue-200/90 mt-1">Real-time monitoring of safe shelters, city bus fleet manifests, IDRN tactical supplies, and Metro mass-transit integrity.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center items-center p-6 sm:p-12 xl:p-24 relative">
        <div className="max-w-lg xl:max-w-2xl w-full">
          {/* Mobile Header */}
          <div className="lg:hidden flex items-center justify-center gap-3 mb-10">
            <div className="bg-blue-600 p-2.5 rounded-xl shadow-lg">
               <Droplets size={28} className="text-white" />
            </div>
            <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">Flood Evac AI</h1>
          </div>

          <div className="mb-12 text-center lg:text-left">
            <h2 className="text-4xl xl:text-5xl font-bold text-slate-800 mb-4 tracking-tight">
              {isRegistering ? 'Create Account' : (isFirstVisit ? 'Welcome' : 'Welcome Back')}
            </h2>
            <p className="text-slate-500 text-xl xl:text-2xl">
              {isRegistering ? 'Register to access the simulation platform.' : 'Sign in to access the command center.'}
            </p>
          </div>

          {error && (
            <div className="mb-8 bg-red-50 border border-red-200 p-4 rounded-xl flex items-center gap-3">
              <ShieldAlert size={20} className="text-red-500 flex-shrink-0" />
              <p className="text-sm text-red-700 font-medium">{error}</p>
            </div>
          )}

          <form onSubmit={handleAuth} className="space-y-6">
            {isRegistering && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Account Type</label>
                    <select
                      name="role"
                      value={formData.role}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 transition duration-200 outline-none hover:border-slate-300 bg-white"
                    >
                      <option value="authority">🏢 Disaster Response Authority</option>
                      <option value="researcher">🔬 Researcher</option>
                    </select>
                  </div>
                  
                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Choose Username</label>
                    <input
                      type="text"
                      name="username"
                      required
                      value={formData.username}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="Enter desired username"
                    />
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Full Name</label>
                    <input
                      type="text"
                      name="name"
                      required
                      value={formData.name}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="Enter your full name"
                    />
                  </div>

                  <div>
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Email Address</label>
                    <input
                      type="email"
                      name="email"
                      required
                      value={formData.email}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="Enter your email address"
                    />
                  </div>

                  <div>
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Phone Number</label>
                    <input
                      type="tel"
                      name="phone"
                      required
                      value={formData.phone}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="Enter your ph. number (e.g., +911234567890)"
                    />
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Address</label>
                    <input
                      type="text"
                      name="address"
                      required
                      value={formData.address}
                      onChange={handleInputChange}
                      className="w-full px-5 py-3 xl:py-4 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="Enter your address (e.g., 123 Main St, City, State)"
                    />
                  </div>
                  
                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Password</label>
                    <div className="relative">
                      <input
                        type={showPassword ? "text" : "password"}
                        name="password"
                        required
                        value={formData.password}
                        onChange={handleInputChange}
                        className="w-full px-5 py-3 xl:py-4 pr-12 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                        placeholder="Enter password"
                      />
                      <button 
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors"
                      >
                        {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                      </button>
                    </div>
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-sm xl:text-base font-semibold text-slate-700 mb-2">Confirm Password</label>
                    <div className="relative">
                      <input
                        type={showPassword ? "text" : "password"}
                        name="confirmPassword"
                        required
                        value={formData.confirmPassword}
                        onChange={handleInputChange}
                        className="w-full px-5 py-3 xl:py-4 pr-12 text-base border-2 border-slate-200 rounded-xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                        placeholder="Confirm password"
                      />
                      <button 
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors"
                      >
                        {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}

            {!isRegistering && (
              <>
                <div>
                  <label className="block text-base xl:text-lg font-semibold text-slate-700 mb-3">Username</label>
                  <input
                    type="text"
                    name="username"
                    required
                    value={formData.username}
                    onChange={handleInputChange}
                    className="w-full px-6 py-4 xl:py-5 text-lg border-2 border-slate-200 rounded-2xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                    placeholder="Enter your username"
                  />
                </div>

                <div>
                  <label className="block text-base xl:text-lg font-semibold text-slate-700 mb-3">Password</label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      name="password"
                      required
                      value={formData.password}
                      onChange={handleInputChange}
                      className="w-full px-6 py-4 xl:py-5 pr-14 text-lg border-2 border-slate-200 rounded-2xl focus:ring-0 focus:border-blue-500 text-slate-800 placeholder-slate-400 transition duration-200 outline-none hover:border-slate-300"
                      placeholder="••••••••"
                    />
                    <button 
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-4 flex items-center text-slate-400 hover:text-slate-600 transition-colors"
                    >
                      {showPassword ? <EyeOff size={24} /> : <Eye size={24} />}
                    </button>
                  </div>
                </div>
              </>
            )}

            <div className="pt-4">
              <button
                type="submit"
                disabled={loading}
                className={"w-full bg-blue-600 hover:bg-blue-700 active:scale-[0.99] text-white font-bold py-5 xl:py-6 text-lg xl:text-xl rounded-2xl shadow-lg shadow-blue-600/30 transition-all duration-200 flex justify-center items-center " + (loading ? 'opacity-70 cursor-not-allowed' : '')}
              >
                {loading ? 'Processing...' : (isRegistering ? 'Register & Login' : 'Sign In')}
              </button>
            </div>
            
            <div className="text-center mt-6">
              <p className="text-slate-600 text-lg">
                {isRegistering ? "Already have an account?" : "Don't have an account?"}
                <button 
                  type="button" 
                  onClick={() => {
                    setIsRegistering(!isRegistering);
                    setError(null);
                  }}
                  className="ml-2 font-bold text-blue-600 hover:text-blue-800 transition-colors"
                >
                  {isRegistering ? "Sign In" : "Register"}
                </button>
              </p>
            </div>
          </form>

          <div className="mt-10">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-4 bg-slate-50 text-slate-400 font-semibold tracking-wide uppercase text-xs">Sandbox Access</span>
              </div>
            </div>

            <div className="mt-8 grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => handleDemoLogin('authority')}
                disabled={loading}
                className="flex flex-col items-center justify-center px-4 py-4 border-2 border-orange-100 bg-white hover:bg-orange-50 hover:border-orange-200 rounded-xl text-orange-600 transition-all duration-200 group active:scale-95 shadow-sm"
              >
                <div className="bg-orange-50 p-2 rounded-full mb-2 group-hover:bg-orange-100 transition-colors">
                  <ShieldAlert size={20} className="text-orange-500" />
                </div>
                <span className="text-sm font-bold">Authority Role</span>
              </button>
              <button
                type="button"
                onClick={() => handleDemoLogin('researcher')}
                disabled={loading}
                className="flex flex-col items-center justify-center px-4 py-4 border-2 border-purple-100 bg-white hover:bg-purple-50 hover:border-purple-200 rounded-xl text-purple-600 transition-all duration-200 group active:scale-95 shadow-sm"
              >
                <div className="bg-purple-50 p-2 rounded-full mb-2 group-hover:bg-purple-100 transition-colors">
                  <Navigation size={20} className="text-purple-500" />
                </div>
                <span className="text-sm font-bold">Researcher Role</span>
              </button>
            </div>
          </div>
          
          <p className="mt-12 text-center text-sm text-slate-400 font-medium">
            &copy; 2026 Digital Twin Flood Evacuation
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;