import { useState } from 'react'
import { Activity, ArrowUpRight, Blocks, ChevronDown, CircleDot, Command, Fingerprint, Gauge, Layers3, Network, Radio, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'

const sections = [
  { label: 'Overview', icon: Gauge }, { label: 'Networks', icon: Network }, { label: 'Observer', icon: Radio },
  { label: 'Detections', icon: Sparkles }, { label: 'Findings', icon: ShieldAlert },
]

function App() {
  const [active, setActive] = useState('Overview')
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#overview"><span className="brand-mark"><Command size={17}/></span><span>ORBIS<span className="brand-sub">INTELLIGENCE</span></span></a>
      <div className="workspace-label">WORKSPACE <span>01</span></div>
      <nav aria-label="Main navigation">{sections.map(({label, icon: Icon}) => <button key={label} className={`nav-item ${active === label ? 'selected' : ''}`} onClick={() => setActive(label)}><Icon size={17}/><span>{label}</span>{label === 'Findings' && <i className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="operator"><div className="avatar">OP</div><div><b>Operator</b><small>Local workspace</small></div><ChevronDown size={15}/></div><div className="version">ORBIS CONSOLE <span>v0.1.0 · FOUNDATION</span></div></div>
    </aside>
    <main className="main-panel">
      <header className="topbar"><div className="breadcrumb">INTELLIGENCE <span>/</span> <b>{active.toUpperCase()}</b></div><div className="top-actions"><span className="api-indicator"><i/> API NOT CONNECTED</span><button className="profile-select" aria-label="Select network profile">Network profile <ChevronDown size={14}/></button></div></header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line"/> OPERATOR CONSOLE <span className="eyebrow-id">/ 01</span></div><h1>{active === 'Overview' ? 'Situational overview' : active}</h1><p>Network intelligence, grounded in verified source evidence.</p></div><div className="date-chip"><CircleDot size={13}/> SYSTEM STATUS <span>UNAVAILABLE</span></div></div>
        <section className="hero-grid">
          <article className="panel identity-panel"><div className="panel-head"><div className="panel-icon teal"><Fingerprint size={17}/></div><div><h2>Network identity</h2><p>Verified chain context</p></div><span className="tag tag-muted">NOT CONNECTED</span></div><div className="identity-empty"><div className="orbit"><Network size={21}/><span/></div><b>No network identity available</b><p>Identity details appear when the backend verifies a configured network profile.</p></div><div className="panel-foot"><span>FINGERPRINT</span><span className="mono">—</span></div></article>
          <article className="panel observer-panel"><div className="panel-head"><div className="panel-icon blue"><Radio size={17}/></div><div><h2>Observer synchronization</h2><p>Canonical source ingestion</p></div><span className="tag tag-muted"><i/> IDLE</span></div><div className="observer-empty"><div className="sync-graphic"><div className="sync-grid"/><Blocks size={30}/><span className="pulse-ring"/></div><div><b>Waiting for observer data</b><p>No synchronization status has been returned by the API.</p></div></div><div className="sync-metrics"><div><small>CHECKPOINT</small><b>—</b></div><div><small>RANGE COVERAGE</small><b className="muted-value">Unavailable</b></div><div><small>LAST VERIFIED</small><b>—</b></div></div></article>
        </section>
        <section className="section-row"><div className="section-title"><div><span className="section-index">01</span><h2>Recent activity</h2></div><span className="section-caption">PERSISTED SOURCE RECORDS</span></div><article className="panel table-panel"><div className="table-head"><span>BLOCK / TRANSACTION</span><span>SUMMARY</span><span>TIME</span><span>STATUS</span></div><div className="empty-row"><div className="empty-icon"><Activity size={17}/></div><div><b>No persisted activity returned</b><p>Activity will appear here when the read-only API is available.</p></div><span className="unavailable-label">UNAVAILABLE</span></div></article></section>
        <section className="lower-grid">
          <article className="panel lower-panel"><div className="section-title"><div><span className="section-index">02</span><h2>Detection status</h2></div><ArrowUpRight size={16}/></div><div className="detection-state"><div className="state-symbol"><Layers3 size={19}/></div><div><b>No evaluations available</b><p>Rule versions and evaluation outcomes require backend data.</p></div></div><div className="lower-foot"><span>D-02 LIFECYCLE</span><b className="tag tag-muted">NOT AVAILABLE</b></div></article>
          <article className="panel lower-panel"><div className="section-title"><div><span className="section-index">03</span><h2>Findings</h2></div><ArrowUpRight size={16}/></div><div className="findings-empty"><div className="findings-icon"><ShieldCheck size={19}/></div><div><b>No findings returned</b><p>An empty response does not indicate a negative evaluation.</p></div></div><div className="lower-foot"><span>ACTIVE / HISTORICAL</span><b>—</b></div></article>
        </section>
        <footer className="footer"><span>ORBIS <i>•</i> EVIDENCE FIRST</span><span><ShieldCheck size={12}/> NO LIVE DATA CONNECTED <span className="footer-divider">|</span> READ-ONLY FOUNDATION</span></footer>
      </div>
    </main>
  </div>
}

export { App }
