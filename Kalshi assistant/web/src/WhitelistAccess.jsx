import React, { useState } from 'react';
import { Lock } from 'lucide-react';

export default function WhitelistAccess({ onAccessGranted }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    // The correct password should be set in Vercel environment variables,
    // but we fall back to a default for local testing if not set.
    const correctPassword = import.meta.env.VITE_ACCESS_KEY || 'kalshi2026';
    
    if (password === correctPassword) {
      setError(false);
      onAccessGranted();
    } else {
      setError(true);
      setPassword('');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f1115] p-4 text-slate-200">
      <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl p-8 max-w-sm w-full shadow-2xl flex flex-col items-center">
        <div className="w-16 h-16 bg-blue-500/10 rounded-full flex items-center justify-center mb-6 border border-blue-500/20">
          <Lock className="w-8 h-8 text-blue-400" />
        </div>
        
        <h1 className="text-xl font-bold mb-2 text-white">Kalshi Quant Assisant</h1>
        <p className="text-gray-400 text-sm text-center mb-8">
          Enter your access key to view live market data.
        </p>

        <form onSubmit={handleSubmit} className="w-full">
          <div className="mb-4">
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(false);
              }}
              placeholder="Access Key"
              className={`w-full bg-[#0c0d12] border ${error ? 'border-red-500/50 focus:border-red-500' : 'border-gray-800 focus:border-blue-500'} rounded-lg px-4 py-3 text-white placeholder-gray-600 outline-none transition-colors`}
              autoFocus
            />
            {error && <p className="text-red-400 text-xs mt-2 font-medium">Incorrect access key. Please try again.</p>}
          </div>
          
          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg transition-colors focus:ring-4 focus:ring-blue-500/20 outline-none"
          >
            Access Dashboard
          </button>
        </form>
      </div>
    </div>
  );
}
