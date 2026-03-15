import React, { useEffect, useState, useRef } from 'react';
import { Activity, Clock, Percent, TrendingUp, TrendingDown, Target, AlertTriangle, Info, Zap, X } from 'lucide-react';

const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
const formatNumber = (val, decimals = 2) => Number(val).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const formatPercent = (val) => Number(val).toLocaleString('en-US', { style: 'percent', minimumFractionDigits: 0 });

const StatCard = ({ title, value, colorClass = "text-white", icon: Icon, subValue, subColorClass = "text-gray-400" }) => (
  <div className="bg-[#1a1d24] rounded-xl p-4 border border-gray-800 shadow-lg flex flex-col justify-between">
    <div className="flex justify-between items-start mb-2">
      <span className="text-sm font-medium text-gray-400">{title}</span>
      {Icon && <Icon className="w-4 h-4 text-gray-500" />}
    </div>
    <div className="flex items-baseline gap-2">
      <span className={`text-2xl font-bold tracking-tight ${colorClass}`}>{value}</span>
      {subValue && <span className={`text-xs font-medium ${subColorClass}`}>{subValue}</span>}
    </div>
  </div>
);

const HelpModal = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl max-w-lg w-full max-h-[80vh] overflow-y-auto shadow-2xl">
        <div className="sticky top-0 bg-[#1a1d24]/90 backdrop-blur border-b border-gray-800 p-4 flex justify-between items-center z-10">
          <h2 className="text-lg font-bold text-white flex items-center gap-2"><Info className="w-5 h-5 text-blue-400"/> What Each Metric Means</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-colors"><X className="w-5 h-5"/></button>
        </div>
        <div className="p-6 space-y-6">
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">15m ATR</h3>
            <p className="text-sm text-gray-300">Average True Range over 15 one-minute candles. Measures how much BTC is moving per candle. High ATR = volatile market. Low ATR = quiet market. Use it to gauge risk.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">VC Z-Score</h3>
            <p className="text-sm text-gray-300">Volatility Compression Z-Score. Normalizes price deviation by ATR and amplifies during volatility squeezes. &gt; +2.0 → BTC unusually HIGH. &lt; -2.0 → BTC unusually LOW. Threshold: ±2.0 required for Prime Setup.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">RSI</h3>
            <p className="text-sm text-gray-300">Relative Strength Index (14-period). &gt; 70 → Overbought (red), &lt; 30 → Oversold (green). 30–70 is Neutral.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">MACD Hist</h3>
            <p className="text-sm text-gray-300">Difference between the MACD line and signal line. Positive (green) → upward momentum building. Negative (red) → downward momentum building.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">EV (Expected Value)</h3>
            <p className="text-sm text-gray-300">Your model's edge vs the Kalshi market price. Positive = model beats market odds. Must be &gt; 0 for Prime Setup.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">YES Prob</h3>
            <p className="text-sm text-gray-300">Market-implied probability that BTC closes ABOVE the strike at expiry. Derived from the Kalshi orderbook (1 - best NO ask price).</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">Direction</h3>
            <p className="text-sm text-gray-300">2-of-3 consensus vote between RSI, MACD, and Z-Score. UP = bet YES. DOWN = bet NO. NEUTRAL = no trade.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">Prob Trend</h3>
            <p className="text-sm text-gray-300">Direction the Kalshi YES implied prob has moved over the last 5 updates. ▲ Rising = bullish. ▼ Falling = bearish.</p>
          </div>
          <div>
            <h3 className="text-sm font-bold text-emerald-400 mb-1">ATR Dist</h3>
            <p className="text-sm text-gray-300">How many ATRs the current BTC price is away from the Kalshi strike price. Positive (green) = Above strike. Negative (red) = Below strike.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default function Dashboard() {
  const [state, setState] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  useEffect(() => {
    const connect = () => {
      const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => {
        setIsConnected(false);
        setTimeout(connect, 2000); // Reconnect loop
      };
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'state') {
          setState({ price: data.current_price, signals: data.signals });
        } else if (data.type === 'info' || data.type === 'error') {
          setLogs(prev => [...prev.slice(-49), data]);
        }
      };
      
      wsRef.current = ws;
    };
    
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (!state) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0f1115]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="text-gray-400 font-medium">Connecting to Kalshi Bot Backend...</p>
        </div>
      </div>
    );
  }

  const { price, signals } = state;
  const { 
    atr, z_score, rsi, ev, macd, signal_direction, prob_trend, 
    p_win_estimate, time_left, strike_price, atr_distance, is_good_setup,
    supports = [], resistances = [] 
  } = signals;

  const mins = Math.floor(time_left / 60);
  const secs = time_left % 60;
  const isExpiring = time_left < 60;

  const zColor = Math.abs(z_score) >= 2.0 ? "text-red-400" : "text-white";
  const rsiColor = rsi > 70 ? "text-red-400" : (rsi < 30 ? "text-emerald-400" : "text-white");
  const dirColor = signal_direction === "UP" ? "text-emerald-400" : (signal_direction === "DOWN" ? "text-red-400" : "text-gray-400");
  const hist = macd?.histogram || 0;
  const histColor = hist > 0 ? "text-emerald-400" : "text-red-400";
  const trendColor = prob_trend === "▲" ? "text-emerald-400" : (prob_trend === "▼" ? "text-red-400" : "text-gray-400");
  const distColor = atr_distance > 1.0 ? "text-emerald-400" : (atr_distance < 0 ? "text-red-400" : "text-white");

  // Format walls
  const maxWallVol = Math.max(
    ...supports.slice(0, 5).map(w => w[1]), 
    ...resistances.slice(0, 5).map(w => w[1]), 
    1
  );

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <HelpModal isOpen={isHelpOpen} onClose={() => setIsHelpOpen(false)} />
      
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[#1a1d24] p-5 rounded-2xl border border-gray-800 shadow-md">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">Kalshi Quant Assisant</h1>
            <div className={`px-2 py-0.5 rounded-full text-xs font-bold border ${isConnected ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
              {isConnected ? 'LIVE' : 'OFFLINE'}
            </div>
          </div>
          <p className="text-gray-400 text-sm font-medium">BTC-USD | KXBTC15M</p>
        </div>
        
        <div className="flex items-center gap-8">
          <div className="text-right">
            <div className="text-sm text-gray-500 font-medium mb-1">Current BTC Price</div>
            <div className="text-3xl font-bold tracking-tight text-white font-mono">{formatCurrency(price)}</div>
          </div>
          
          <div className={`flex flex-col items-center justify-center p-3 rounded-xl border ${isExpiring ? 'bg-red-500/10 border-red-500/30' : 'bg-[#222630] border-gray-800'}`}>
            <div className="flex items-center gap-1.5 text-xs font-bold text-gray-400 mb-1 uppercase tracking-wider">
              <Clock className="w-3.5 h-3.5" /> Market Closes In
            </div>
            <div className={`text-2xl font-bold font-mono ${isExpiring ? 'text-red-400 animate-pulse' : 'text-gray-300'}`}>
              {mins.toString().padStart(2, '0')}:{secs.toString().padStart(2, '0')}
            </div>
          </div>
        </div>
      </header>

      {/* Prime Setup Banner */}
      {is_good_setup ? (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-5 shadow-lg shadow-emerald-500/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-10">
            <Zap size={120} className="text-emerald-500" />
          </div>
          <div className="relative z-10">
            <h2 className="text-lg font-bold text-emerald-400 flex items-center gap-2 mb-2">
              <Zap className="w-5 h-5 fill-emerald-400" /> PRIME SETUP DETECTED — ACT NOW
            </h2>
            <p className="text-emerald-100/80 mb-4 max-w-2xl text-sm leading-relaxed">
              BTC momentum ({signal_direction}) diverges from Kalshi market price.
              Edge: <strong className="text-white bg-emerald-500/20 px-1.5 py-0.5 rounded">EV {ev > 0 ? '+' : ''}{formatNumber(ev, 3)}</strong> per $1 risked.
            </p>
            <div className="bg-[#1a1d24]/60 backdrop-blur rounded-xl p-4 border border-emerald-500/20 inline-block">
              <p className="font-medium text-white text-sm">
                ACTION: Open the current KXBTC15M market on Kalshi and place a <strong className="text-emerald-400">{(signal_direction === 'UP' ? 'YES' : 'NO')}</strong> contract. 
                Size $5–$20. Edge closes quickly!
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl p-5 shadow-md flex items-start gap-4">
          <div className="p-2 bg-gray-800/50 rounded-lg shrink-0">
            <Activity className="w-5 h-5 text-gray-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-gray-300 mb-1">Monitoring... Wait for edge.</h2>
              Waiting for statistical edge. Prime Setup requires: Z-Score ≥ ±2.0, EV &gt; 0, and a 2-of-3 directional vote (RSI+MACD+Z).
          </div>
        </div>
      )}

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Col: Metrics */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-200">Signal Metrics</h3>
            <button onClick={() => setIsHelpOpen(true)} className="flex items-center gap-1.5 text-xs font-semibold bg-[#222630] hover:bg-[#2a2f3a] text-blue-400 transition-colors px-3 py-1.5 rounded-full border border-gray-800">
              <Info className="w-3.5 h-3.5" /> What do these mean?
            </button>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard title="15m ATR" value={formatCurrency(atr)} icon={Activity} />
            <StatCard title="VC Z-Score" value={formatNumber(z_score)} colorClass={zColor} icon={Target} />
            <StatCard title="RSI (14)" value={formatNumber(rsi, 1)} colorClass={rsiColor} icon={Activity} />
            <StatCard title="MACD Hist" value={(hist > 0 ? '+' : '') + formatNumber(hist, 4)} colorClass={histColor} icon={TrendingUp} />
            
            <StatCard title="Expected Value" value={(ev > 0 ? '+' : '') + formatNumber(ev, 4)} colorClass={ev > 0 ? "text-emerald-400" : "text-white"} icon={Activity} />
            <StatCard title="YES Prob" value={formatPercent(p_win_estimate)} subValue={`${prob_trend} Trend`} subColorClass={trendColor} icon={Percent} />
            <StatCard title="Direction" value={signal_direction} colorClass={dirColor} icon={signal_direction === 'UP' ? TrendingUp : (signal_direction === 'DOWN' ? TrendingDown : Activity)} />
            
            <StatCard 
              title="Strike Dist" 
              value={(atr_distance > 0 ? '+' : '') + formatNumber(atr_distance)} 
              subValue="ATR"
              colorClass={distColor} 
              icon={Target} 
            />
          </div>
          
          {/* Target Strike Info Banner */}
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4 flex justify-between items-center">
             <div className="flex items-center gap-3">
               <Target className="w-5 h-5 text-blue-400" />
               <span className="text-sm font-medium text-blue-100">Kalshi Contract Target Strike</span>
             </div>
             <div className="text-xl font-mono font-bold text-white">{formatCurrency(strike_price)}</div>
          </div>
        </div>

        {/* Right Col: Orderbook & Logs */}
        <div className="space-y-6">
          <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl p-5 shadow-md flex flex-col h-72">
            <h3 className="text-sm font-bold text-gray-300 mb-4 flex items-center gap-2"><Activity className="w-4 h-4"/> Orderbook Walls</h3>
            <div className="flex-1 overflow-auto space-y-1 font-mono text-xs">
              {resistances.slice(0, 5).reverse().map((w, i) => (
                <div key={`res-${i}`} className="flex items-center gap-2">
                  <span className="text-red-400 w-16">${formatNumber(w[0], 2)}</span>
                  <div className="flex-1 bg-gray-800 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-red-500/70 h-full rounded-full" style={{ width: `${(w[1] / maxWallVol) * 100}%` }}></div>
                  </div>
                  <span className="text-gray-400 w-16 text-right">${formatNumber(Math.round(w[1]), 0)}</span>
                </div>
              ))}
              
              <div className="my-3 border-t border-gray-800/80 border-dashed relative">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#1a1d24] px-2 text-[10px] text-gray-500 tracking-wider">SPREAD</div>
              </div>
              
              {supports.slice(0, 5).map((w, i) => (
                <div key={`sup-${i}`} className="flex items-center gap-2">
                  <span className="text-emerald-400 w-16">${formatNumber(w[0], 2)}</span>
                  <div className="flex-1 bg-gray-800 h-1.5 rounded-full overflow-hidden">
                    <div className="bg-emerald-500/70 h-full rounded-full" style={{ width: `${(w[1] / maxWallVol) * 100}%` }}></div>
                  </div>
                  <span className="text-gray-400 w-16 text-right">${formatNumber(Math.round(w[1]), 0)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl p-4 shadow-md flex flex-col h-48">
             <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">System Logs</h3>
             <div className="flex-1 overflow-y-auto space-y-1 font-mono text-[10px] bg-[#0c0d12] rounded-lg p-3 border border-gray-800/50">
               {logs.length === 0 ? (
                 <span className="text-gray-600 italic">Waiting for connection...</span>
               ) : (
                 logs.map((log, i) => (
                   <div key={i} className={`${log.type === 'error' ? 'text-red-400' : 'text-gray-400'}`}>
                     <span className="opacity-50 font-bold mr-1">[{log.type === 'error' ? 'ERR' : 'INFO'}]</span>
                     {log.message}
                   </div>
                 ))
               )}
               <div ref={logsEndRef} />
             </div>
          </div>
        </div>

      </div>
    </div>
  );
}
