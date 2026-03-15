import React, { useState } from 'react'
import Dashboard from './Dashboard'
import WhitelistAccess from './WhitelistAccess'
import './index.css'

function App() {
  const [accessGranted, setAccessGranted] = useState(false);

  return (
    <div className="min-h-screen bg-[#0f1115] text-slate-200">
      {accessGranted ? 
        <Dashboard /> : 
        <WhitelistAccess onAccessGranted={() => setAccessGranted(true)} />
      }
    </div>
  )
}

export default App
