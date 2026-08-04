import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import type { CSSProperties, ReactNode } from 'react'
import {
  Activity, ArrowRight, BarChart3, Building2, Check, ChevronLeft, ChevronRight, CircleDollarSign,
  Clock3, Coffee, Gauge, Layers3, MapPin, Pause, Play, Radio, RotateCcw, Search,
  Sparkles, Store, Target, TrendingUp, Users, Zap,
} from 'lucide-react'
import { changeSimulationSpeed, configureScenario, generateAIInsight, getAIStatus, openSimulationSocket, simulationCommand } from './api'
import type { AIStatus } from './api'
import type { LayerKey, ScenarioConfig, Snapshot } from './types'
import './styles.css'

const initialConfig: ScenarioConfig = {
  category: 'Premium coffee', brand_name: 'Northstar Coffee', average_ticket: 8.75, store_size: 1400,
  opening_time: 7, closing_time: 20, marketing_budget: 85000,
  positioning: 'Thoughtful energy for the city', target_demographic: 'Office workers + design-forward locals',
  locations: [{ id: 'A', enabled: true }, { id: 'B', enabled: true }, { id: 'C', enabled: true }],
  marketing_channels: ['Grand opening', 'Transit ads'],
}

const layers: { key: LayerKey; label: string; color: string }[] = [
  { key: 'footTraffic', label: 'Foot traffic', color: '#f9b44b' },
  { key: 'awareness', label: 'Brand awareness', color: '#9b8afd' },
  { key: 'sentiment', label: 'Sentiment', color: '#62d9a5' },
  { key: 'revenue', label: 'Revenue heatmap', color: '#f472b6' },
]

const locationMeta: Record<string, { address: string; note: string; x: number; y: number }> = {
  A: { address: 'Spring & Mercer', note: 'Highest impressions', x: 24, y: 31 },
  B: { address: 'Broadway Subway', note: 'Best conversion', x: 72, y: 62 },
  C: { address: 'Prince Courtyard', note: 'Weekend upside', x: 57, y: 82 },
}

function money(value: number, compact = false) {
  if (compact && value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (compact && value >= 1_000) return `$${Math.round(value / 1_000)}K`
  return `$${Math.round(value).toLocaleString()}`
}

function App() {
  const [config, setConfig] = useState<ScenarioConfig>(initialConfig)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [view, setView] = useState<'setup' | 'simulation' | 'report'>('setup')
  const [step, setStep] = useState(0)
  const [speed, setSpeed] = useState(10)
  const [activeLayer, setActiveLayer] = useState<LayerKey>('footTraffic')
  const [selectedLocation, setSelectedLocation] = useState('B')
  const [socketStatus, setSocketStatus] = useState<'connecting' | 'live' | 'offline'>('connecting')
  const [error, setError] = useState('')
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null)
  const [aiBrief, setAiBrief] = useState<{ provider: string; content: string; used_fallback: boolean } | null>(null)

  useEffect(() => {
    if (view !== 'simulation') return
    let disposed = false
    let retry: ReturnType<typeof window.setTimeout> | undefined
    let socket: WebSocket | undefined
    const connect = () => {
      if (disposed) return
      setSocketStatus('connecting')
      socket = openSimulationSocket(setSnapshot, () => {
        setSocketStatus('offline')
        if (!disposed) retry = window.setTimeout(connect, 1800)
      })
      socket.onopen = () => setSocketStatus('live')
    }
    connect()
    return () => {
      disposed = true
      if (retry) window.clearTimeout(retry)
      socket?.close()
    }
  }, [view])

  useEffect(() => {
    if (view === 'setup') return
    getAIStatus().then(setAiStatus).catch(() => setAiStatus(null))
  }, [view])

  const selectedMetric = snapshot?.locations.find((location) => location.id === selectedLocation) ?? snapshot?.locations[0]
  const bestLocation = useMemo(() => snapshot?.locations.reduce((best, current) => current.daily_revenue > best.daily_revenue ? current : best, snapshot.locations[0]), [snapshot])

  useEffect(() => {
    if (view !== 'report' || !bestLocation) return
    const prompt = `Retail expansion brief for ${config.brand_name}. Best location is ${bestLocation.id}, ${bestLocation.name}. Daily revenue ${bestLocation.daily_revenue}, conversion ${bestLocation.conversion_rate}%, repeat rate ${bestLocation.repeat_rate}, foot traffic ${bestLocation.foot_traffic}. Explain the executive recommendation in 2 concise sentences and name one risk.`
    generateAIInsight(prompt).then((result) => setAiBrief({ provider: result.provider, content: result.content, used_fallback: result.used_fallback })).catch(() => setAiBrief(null))
  }, [view, bestLocation?.id, config.brand_name])

  const beginSimulation = useCallback(async () => {
    if (config.locations.filter((location) => location.enabled).length < 2) {
      setError('Select at least two locations to compare.')
      return
    }
    try {
      const fresh = await configureScenario(config)
      setSnapshot(fresh)
      setView('simulation')
      setStep(0)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to launch the twin.')
    }
  }, [config])

  const toggleSimulation = async () => {
    try {
      const fresh = await simulationCommand(snapshot?.running ? 'stop' : 'start', speed)
      setSnapshot(fresh)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Simulation command failed.')
    }
  }

  const resetSimulation = async () => {
    try {
      setSnapshot(await simulationCommand('reset'))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to reset simulation.')
    }
  }

  const updateSpeed = async (nextSpeed: number) => {
    setSpeed(nextSpeed)
    try {
      setSnapshot(await changeSimulationSpeed(nextSpeed))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to change simulation speed.')
    }
  }

  const updateConfig = <K extends keyof ScenarioConfig>(key: K, value: ScenarioConfig[K]) => setConfig((current) => ({ ...current, [key]: value }))

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup"><div className="brand-mark"><span /><span /><span /></div><div><strong>retail<span>twin</span></strong><small>LOCATION INTELLIGENCE</small></div></div>
        {view !== 'setup' && <div className="district-context"><span className="live-dot" />SOHO, MANHATTAN <i>•</i> 30-DAY SIMULATION</div>}
        <div className="top-actions"><button className="icon-button"><Search size={17} /></button><button className="avatar">LS</button></div>
      </header>

      {view === 'setup' ? <Setup config={config} step={step} setStep={setStep} updateConfig={updateConfig} beginSimulation={beginSimulation} /> : (
        <main className="workspace">
          <aside className="sidebar">
            <div className="sidebar-label">WORKSPACE</div>
            <button className={view === 'simulation' ? 'nav-item active' : 'nav-item'} onClick={() => setView('simulation')}><Activity size={17} />Live simulation <span className="nav-live" /></button>
            <button className={view === 'report' ? 'nav-item active' : 'nav-item'} onClick={() => setView('report')}><BarChart3 size={17} />Executive report</button>
            <div className="sidebar-rule" />
            <div className="sidebar-label">SCENARIO</div>
            <div className="scenario-mini"><div className="scenario-icon"><Coffee size={17} /></div><div><b>{config.brand_name}</b><span>{config.category}</span></div><Check size={15} className="check-icon" /></div>
            <div className="sidebar-location"><MapPin size={14} /> {config.locations.filter((location) => location.enabled).length} locations selected</div>
            <div className="sidebar-rule" />
            <div className="sidebar-label">SIMULATION</div>
            <div className="day-card"><div><span>SIMULATED DAY</span><strong>DAY {snapshot?.day ?? 1}<small> / 30</small></strong></div><div className="mini-progress"><span style={{ width: `${snapshot?.progress ?? 0}%` }} /></div></div>
            <div className="sidebar-foot"><div className="system-status"><span className={`status-dot ${socketStatus}`} /> Engine {socketStatus === 'live' ? 'connected' : socketStatus}</div><span className="version">v0.1 MVP</span></div>
          </aside>
          {error && <div className="error-banner">{error}</div>}
          {view === 'simulation' ? <Simulation snapshot={snapshot} selectedMetric={selectedMetric} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} activeLayer={activeLayer} setActiveLayer={setActiveLayer} speed={speed} setSpeed={updateSpeed} toggleSimulation={toggleSimulation} resetSimulation={resetSimulation} setView={setView} aiStatus={aiStatus} /> : <Report snapshot={snapshot} bestLocation={bestLocation} brand={config.brand_name} setView={setView} aiStatus={aiStatus} aiBrief={aiBrief} />}
        </main>
      )}
    </div>
  )
}

function Setup({ config, step, setStep, updateConfig, beginSimulation }: { config: ScenarioConfig; step: number; setStep: (value: number) => void; updateConfig: <K extends keyof ScenarioConfig>(key: K, value: ScenarioConfig[K]) => void; beginSimulation: () => void }) {
  const steps = ['Your concept', 'Store strategy', 'Test locations', 'Go live']
  const channels = ['Grand opening', 'Transit ads', 'Local influencers', 'Opening discount', 'Social media']
  const canNext = step < 3
  const canLaunch = config.locations.filter((location) => location.enabled).length >= 2
  return <main className="setup-page">
    <div className="setup-hero"><div className="eyebrow"><Sparkles size={14} />DECISION INTELLIGENCE FOR PHYSICAL RETAIL</div><h1>Find the location<br /><em>that moves people.</em></h1><p>Simulate your next store across 10,000 synthetic consumers, 30 days of real behavior, and every strategic variable that matters.</p></div>
    <div className="setup-card">
      <div className="stepper">{steps.map((item, index) => <div key={item} className={`step ${index === step ? 'current' : ''} ${index < step ? 'done' : ''}`}><span>{index < step ? <Check size={13} /> : index + 1}</span>{item}</div>)}</div>
      <div className="setup-content">
        {step === 0 && <><div className="section-kicker">STEP 01 / CONCEPT</div><h2>What are you bringing to SoHo?</h2><p className="section-copy">Start with the idea you want to pressure-test. We’ll tune the neighborhood’s behavior model to your category.</p><label>RETAIL CATEGORY</label><div className="category-grid">{['Premium coffee', 'Healthy fast casual', 'Athletic apparel', 'Fitness studio', 'Beauty retail', 'Specialty grocery'].map((category) => <button key={category} className={`category-card ${config.category === category ? 'selected' : ''}`} onClick={() => updateConfig('category', category)}>{category === 'Premium coffee' ? <Coffee /> : category === 'Athletic apparel' ? <Target /> : category === 'Fitness studio' ? <Activity /> : <Store />}<span>{category}</span>{config.category === category && <Check className="category-check" size={15} />}</button>)}</div><label>BRAND NAME</label><input value={config.brand_name} onChange={(event) => updateConfig('brand_name', event.target.value)} placeholder="e.g. Northstar Coffee" /></>}
        {step === 1 && <><div className="section-kicker">STEP 02 / STRATEGY</div><h2>Give your store a point of view.</h2><p className="section-copy">A sharper strategy makes the synthetic consumers more opinionated — and the result more useful.</p><div className="form-grid"><div><label>AVERAGE TICKET</label><div className="input-prefix"><span>$</span><input type="number" value={config.average_ticket} onChange={(event) => updateConfig('average_ticket', Number(event.target.value))} /></div></div><div><label>STORE SIZE</label><div className="input-suffix"><input type="number" value={config.store_size} onChange={(event) => updateConfig('store_size', Number(event.target.value))} /><span>sq ft</span></div></div><div><label>OPENING HOUR</label><select value={config.opening_time} onChange={(event) => updateConfig('opening_time', Number(event.target.value))}>{Array.from({ length: 13 }, (_, index) => index + 5).map((hour) => <option key={hour} value={hour}>{hour}:00</option>)}</select></div><div><label>CLOSING HOUR</label><select value={config.closing_time} onChange={(event) => updateConfig('closing_time', Number(event.target.value))}>{Array.from({ length: 10 }, (_, index) => index + 15).map((hour) => <option key={hour} value={hour}>{hour}:00</option>)}</select></div></div><label>POSITIONING</label><input value={config.positioning} onChange={(event) => updateConfig('positioning', event.target.value)} /><label>TARGET DEMOGRAPHIC</label><input value={config.target_demographic} onChange={(event) => updateConfig('target_demographic', event.target.value)} /><label>MARKETING BUDGET</label><div className="input-prefix"><span>$</span><input type="number" value={config.marketing_budget} onChange={(event) => updateConfig('marketing_budget', Number(event.target.value))} /></div></>}
        {step === 2 && <><div className="section-kicker">STEP 03 / LOCATIONS + LAUNCH</div><h2>Which storefronts should we put to the test?</h2><p className="section-copy">Select two or more locations to let the twin expose the trade-offs between attention, access, and intent.</p><div className="location-select-grid">{Object.entries(locationMeta).map(([id, meta]) => { const enabled = config.locations.find((location) => location.id === id)?.enabled; return <button key={id} className={`location-select ${enabled ? 'selected' : ''}`} onClick={() => updateConfig('locations', config.locations.map((location) => location.id === id ? { ...location, enabled: !location.enabled } : location))}><div className="location-letter">{id}</div><div><b>{meta.address}</b><span>{meta.note}</span><small>{id === 'A' ? '24.5K' : id === 'B' ? '14.2K' : '11.8K'} daily passers</small></div><span className="toggle"><i /></span></button>})}</div><label>OPTIONAL MARKETING CHANNELS</label><div className="channel-list">{channels.map((channel) => <button key={channel} className={config.marketing_channels.includes(channel) ? 'channel selected' : 'channel'} onClick={() => updateConfig('marketing_channels', config.marketing_channels.includes(channel) ? config.marketing_channels.filter((item) => item !== channel) : [...config.marketing_channels, channel])}><span>{config.marketing_channels.includes(channel) ? <Check size={14} /> : '+'}</span>{channel}</button>)}</div></>}
        {step === 3 && <div className="ready-state"><div className="ready-icon"><Radio size={29} /></div><div className="section-kicker">READY TO LAUNCH</div><h2>Your neighborhood is waiting.</h2><p className="section-copy">We’ll animate 10,000 agents across SoHo for 30 simulated days — from morning commutes to late-night impulse buys.</p><div className="launch-summary"><div><span>CONCEPT</span><b>{config.brand_name}</b></div><div><span>LOCATIONS</span><b>{config.locations.filter((location) => location.enabled).map((location) => location.id).join(' · ')}</b></div><div><span>MARKETING</span><b>{config.marketing_channels.length} channels</b></div></div></div>}
      </div>
      <div className="setup-footer"><button className="back-button" disabled={step === 0} onClick={() => setStep(step - 1)}><ChevronLeft size={16} /> Back</button>{canNext ? <button className="primary-button" onClick={() => setStep(step + 1)}>Continue <ArrowRight size={16} /></button> : <button className="primary-button launch-button" disabled={!canLaunch} onClick={beginSimulation}><Play size={15} fill="currentColor" /> Press play on your twin</button>}</div>
    </div>
    <div className="setup-proof"><span><Users size={15} />10,000 synthetic consumers</span><span><Building2 size={15} />1 real neighborhood</span><span><Clock3 size={15} />30 days in 30 seconds</span></div>
  </main>
}

function Simulation({ snapshot, selectedMetric, selectedLocation, setSelectedLocation, activeLayer, setActiveLayer, speed, setSpeed, toggleSimulation, resetSimulation, setView, aiStatus }: { snapshot: Snapshot | null; selectedMetric: Snapshot['locations'][number] | undefined; selectedLocation: string; setSelectedLocation: (value: string) => void; activeLayer: LayerKey; setActiveLayer: (value: LayerKey) => void; speed: number; setSpeed: (value: number) => void; toggleSimulation: () => void; resetSimulation: () => void; setView: (value: 'setup' | 'simulation' | 'report') => void; aiStatus: AIStatus | null }) {
  return <section className="simulation-page">
    <div className="page-heading"><div><div className="eyebrow muted"><span className="live-dot" />LIVE SIMULATION</div><h1>SoHo is in motion.</h1><p>Watch behavior, not just foot traffic.</p></div><div className="simulation-actions"><button className="secondary-button" onClick={resetSimulation}><RotateCcw size={15} /> Reset</button><button className="primary-button" onClick={toggleSimulation}>{snapshot?.running ? <><Pause size={15} fill="currentColor" /> Pause twin</> : <><Play size={15} fill="currentColor" /> Start twin</>}</button></div></div>
    <div className="kpi-grid"><Kpi label="DAILY REVENUE" value={money(snapshot?.daily_revenue ?? 0, true)} delta="+18.4%" icon={<CircleDollarSign />} /><Kpi label="TRANSACTIONS" value={(snapshot?.transactions ?? 0).toLocaleString()} delta="+12.1%" icon={<Users />} /><Kpi label="REPEAT CUSTOMERS" value={(snapshot?.repeat_customers ?? 0).toLocaleString()} delta="+8.7%" icon={<RotateCcw />} /><Kpi label="AVG. TICKET" value={money(snapshot?.average_ticket ?? 0)} delta="on target" icon={<Gauge />} /><Kpi label="MARKET SHARE" value={`${snapshot?.market_share ?? 0}%`} delta="district share" icon={<TrendingUp />} />
    </div>
    <div className="main-grid"><div className="map-card"><div className="card-header"><div><span className="card-label"><span className="tiny-live" />DISTRICT TWIN</span><h3>Consumer movement <small>· simulated live</small></h3></div><div className="time-readout"><strong>DAY {snapshot?.day ?? 1}</strong><span>{String(snapshot?.hour ?? 7).padStart(2, '0')}:00</span></div></div><div className="map-toolbar"><div className="layer-switcher">{layers.map((layer) => <button className={activeLayer === layer.key ? 'active' : ''} key={layer.key} onClick={() => setActiveLayer(layer.key)}><i style={{ background: layer.color }} />{layer.label}</button>)}</div><div className="speed-control"><span>SPEED</span>{[1, 10, 100].map((item) => <button key={item} onClick={() => setSpeed(item)} className={speed === item ? 'active' : ''}>{item}×</button>)}</div></div><DistrictMap snapshot={snapshot} activeLayer={activeLayer} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} /></div><aside className="insights-column"><div className="insight-card aha"><div className="aha-icon"><Zap size={17} fill="currentColor" /></div><div><span className="card-label">THE AHA MOMENT · {aiStatus?.mode === 'ai-enabled' ? 'AI ENRICHED' : 'DETERMINISTIC'}</span><h3>High traffic is not high intent.</h3><p>Location A sees <b>73% more passersby</b>, but B converts almost 2× better — people slow down at the subway exit.</p><button onClick={() => setSelectedLocation('B')}>Inspect the difference <ArrowRight size={14} /></button></div></div><div className="insight-card"><div className="card-header compact"><div><span className="card-label">LOCATION PERFORMANCE</span><h3>{selectedMetric?.name ?? 'Compare locations'}</h3></div><button className="text-button">Compare <ChevronRight size={14} /></button></div><div className="location-tabs">{snapshot?.locations.map((location) => <button className={selectedLocation === location.id ? 'active' : ''} key={location.id} onClick={() => setSelectedLocation(location.id)}>Location {location.id}</button>)}</div>{selectedMetric && <><div className="performance-number"><strong>{money(selectedMetric.annual_revenue, true)}</strong><span>estimated annual revenue</span></div><div className="metric-list"><Metric label="Conversion rate" value={`${selectedMetric.conversion_rate}%`} bar={selectedMetric.conversion_rate * 10} /><Metric label="Repeat rate" value={`${Math.round(selectedMetric.repeat_rate * 100)}%`} bar={selectedMetric.repeat_rate * 100} /><Metric label="Payback period" value={`${selectedMetric.payback_months} mo`} bar={Math.max(20, 100 - selectedMetric.payback_months * 2)} /></div></>}</div></aside></div>
    <div className="bottom-grid"><Feed snapshot={snapshot} /><Competitors snapshot={snapshot} /></div><button className="report-banner" onClick={() => setView('report')}><div><span className="card-label">SIMULATION REPORT</span><strong>See the strategic recommendation</strong><p>Turn 30 days of behavior into your next location decision.</p></div><div className="report-arrow"><ArrowRight /></div></button>
  </section>
}

function DistrictMap({ snapshot, activeLayer, selectedLocation, setSelectedLocation }: { snapshot: Snapshot | null; activeLayer: LayerKey; selectedLocation: string; setSelectedLocation: (value: string) => void }) {
  const locations = snapshot?.locations ?? []
  return <div className="district-map"><div className="map-gridlines" />{Array.from({ length: 14 }, (_, index) => <div key={`street-${index}`} className={index % 2 ? 'street horizontal' : 'street vertical'} style={{ [index % 2 ? 'top' : 'left']: `${8 + index * 7}%` } as CSSProperties}><span>{index % 2 ? `W ${index + 17} ST` : `${index + 1} AVE`}</span></div>)}<div className="park" /><div className="subway"><span>◆</span> PRINCE ST</div><div className="map-label office-label">OFFICE DISTRICT</div><div className="map-label gallery-label">GALLERIES</div>{snapshot?.agents.map((agent) => <span key={agent.id} className={`agent ${agent.status}`} style={{ left: `${agent.x}%`, top: `${agent.y}%`, background: agent.color, boxShadow: `0 0 ${activeLayer === 'sentiment' ? 8 : 4}px ${agent.color}` }} />)}{locations.map((location) => <button key={location.id} className={`store-pin ${selectedLocation === location.id ? 'selected' : ''}`} style={{ left: `${locationMeta[location.id].x}%`, top: `${locationMeta[location.id].y}%` }} onClick={() => setSelectedLocation(location.id)}><span>{location.id}</span><b>LOCATION {location.id}</b></button>)}<div className="map-legend"><span><i className="legend-dot office" />Office worker</span><span><i className="legend-dot resident" />Resident</span><span><i className="legend-dot tourist" />Tourist</span></div><div className="map-heat" style={{ opacity: 0.08 + (snapshot?.layer_values[activeLayer] ?? 0) / 600 }} /></div>
}

function Kpi({ label, value, delta, icon }: { label: string; value: string; delta: string; icon: ReactNode }) { return <div className="kpi-card"><div className="kpi-top"><span>{label}</span><i>{icon}</i></div><strong>{value}</strong><small><TrendingUp size={12} />{delta}</small></div> }
function Metric({ label, value, bar }: { label: string; value: string; bar: number }) { return <div className="metric"><div><span>{label}</span><b>{value}</b></div><div className="metric-bar"><i style={{ width: `${Math.min(100, bar)}%` }} /></div></div> }
function Feed({ snapshot }: { snapshot: Snapshot | null }) { return <div className="feed-card"><div className="card-header compact"><div><span className="card-label">CONSUMER FEED</span><h3>What the neighborhood is saying</h3></div><span className="feed-count"><span className="tiny-live" /> LIVE</span></div><div className="feed-list">{snapshot?.feed.map((item) => <div className="feed-item" key={item.id}><div className={`feed-avatar ${item.sentiment}`}>{item.avatar}</div><div><p><b>{item.name}</b> {item.text}</p><span>{item.time} <i>·</i> <em>{item.sentiment}</em></span></div></div>)}</div></div> }
function Competitors({ snapshot }: { snapshot: Snapshot | null }) { return <div className="feed-card"><div className="card-header compact"><div><span className="card-label">COMPETITOR INTELLIGENCE</span><h3>Market reactions</h3></div><button className="icon-button small"><Layers3 size={15} /></button></div><div className="competitor-list">{snapshot?.competitor_events.map((item) => <div className="competitor-item" key={item.id}><div className="competitor-icon"><Building2 size={15} /></div><div><p><b>{item.competitor}</b> {item.text}</p><span>{item.time}</span></div><span className="event-kind">{item.kind}</span></div>)}</div></div> }

function Report({ snapshot, bestLocation, brand, setView, aiStatus, aiBrief }: { snapshot: Snapshot | null; bestLocation: Snapshot['locations'][number] | undefined; brand: string; setView: (value: 'setup' | 'simulation' | 'report') => void; aiStatus: AIStatus | null; aiBrief: { provider: string; content: string; used_fallback: boolean } | null }) { const rawTrafficLocation = snapshot?.locations.find((location) => location.id === 'A'); const winnerId = bestLocation?.id ?? 'B'; return <section className="report-page"><div className="page-heading"><div><div className="eyebrow muted"><BarChart3 size={14} />EXECUTIVE REPORT · SOHO, MANHATTAN</div><h1>The decision is clearer now.</h1><p>30 simulated days distilled into an expansion recommendation for {brand}.</p></div><button className="secondary-button" onClick={() => setView('simulation')}><ChevronLeft size={15} /> Back to twin</button></div><div className="report-hero"><div><span className="card-label">RECOMMENDED LOCATION</span><h2>Location {bestLocation?.id ?? 'B'} <em>· {bestLocation?.name ?? 'Broadway Subway'}</em></h2><p>{winnerId === 'B' ? 'The subway exit creates a natural pause point.' : 'This location combines the strongest local context with a repeatable customer routine.'} Lower raw traffic, but dramatically stronger intent and repeat behavior.</p></div><div className="recommendation-score"><strong>92</strong><span>confidence<br />score</span></div></div><div className="report-stats"><ReportStat label="EST. ANNUAL REVENUE" value={money(bestLocation?.annual_revenue ?? 0, true)} sub="vs. $3.2M at Location A" /><ReportStat label="EXPECTED DAILY CUSTOMERS" value={(bestLocation?.transactions ?? 0).toLocaleString()} sub="Steady morning + lunch demand" /><ReportStat label="PAYBACK PERIOD" value={`${bestLocation?.payback_months ?? 18} months`} sub="Including build-out + launch" /><ReportStat label="AVERAGE WAIT TIME" value="4 min" sub="Peak: 8 min at 12:15 PM" /></div><div className="report-columns"><div className="report-panel"><span className="card-label">{aiBrief?.used_fallback ? 'DETERMINISTIC BRIEF' : `${aiBrief?.provider.toUpperCase() ?? 'AI'} BRIEF`}</span><h3>Executive readout.</h3><p className="report-note ai-note">{aiBrief?.content ?? 'Generating a provider-aware strategy brief from the simulation results…'}</p><small className="ai-caption">{aiStatus?.mode === 'ai-enabled' ? 'Generated with your configured provider router.' : 'No provider key detected — using the reproducible local fallback.'}</small></div><div className="report-panel"><span className="card-label">WHY LOCATION {winnerId} WINS</span><h3>Intent beats impressions.</h3><div className="comparison"><div className="compare-row"><span>Location A · raw traffic</span><div><i style={{ width: `${Math.min(100, (rawTrafficLocation?.foot_traffic ?? 24500) / 260)}%` }} /></div><b>{((rawTrafficLocation?.foot_traffic ?? 24500) / 1000).toFixed(1)}K</b></div><div className="compare-row winner"><span>Location {winnerId} · conversion</span><div><i style={{ width: `${Math.min(100, (bestLocation?.conversion_rate ?? 6.8) * 10)}%` }} /></div><b>{bestLocation?.conversion_rate ?? 6.8}%</b></div></div><p className="report-note"><Zap size={15} /> The twin found that commuters at A move too quickly to stop. At {winnerId}, customers naturally slow down, browse, and return.</p></div><div className="report-panel"><span className="card-label">DECISION BRIEF</span><h3>Plan around the pause.</h3><div className="brief-list"><div><span className="brief-dot green" /><p><b>Opportunity</b> Nearby office workers become high-frequency regulars.</p></div><div><span className="brief-dot yellow" /><p><b>Watch</b> Lunch demand will exceed seating on Tuesdays and Thursdays.</p></div><div><span className="brief-dot red" /><p><b>Risk</b> Blank Street loyalty is strongest within a 2-block radius.</p></div></div></div></div></section> }
function ReportStat({ label, value, sub }: { label: string; value: string; sub: string }) { return <div className="report-stat"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div> }

export default App

createRoot(document.getElementById('root')!).render(<App />)
