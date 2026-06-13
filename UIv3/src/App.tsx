/* ============================================================
   CLOSZR — App root
   ============================================================ */
import { useState, useEffect, useCallback } from "react";
import { Icon, Avatar } from "./components";
import { useData } from "./data/store";
import { fetchDealDetail, type DealDetail } from "./data/fetchDetail";
import DealsTable from "./DealsTable";
import PipelineView from "./PipelineView";
import DealWorkspace from "./DealWorkspace";
import ForecastView from "./ForecastView";
import OneOnOneView from "./OneOnOneView";
import TodoView from "./TodoView";

function TopBar({ view, onNav }: { view: string; onNav: (v: string) => void }) {
  const tabs = ["TO-DOs", "Deals", "Forecast", "1:1"];
  return (
    <header className="cz-topbar">
      <div className="cz-brand">
        <span className="cz-logo">Closzr</span>
        <span className="cz-logo-sub">Sales Intelligence</span>
      </div>
      <nav className="cz-topnav">
        {tabs.map(t => <button key={t} className={"cz-topnav-tab" + (t === view ? " on" : "")} onClick={() => onNav(t)}>{t}</button>)}
      </nav>
      <div style={{flex:1}}/>
      <button className="cz-team-select">All Teams <Icon name="chevDown" size={14}/></button>
      <div className="cz-user">
        <Avatar initials="XS" size={34} name="Xavi Soler"/>
        <div className="cz-user-info">
          <span className="cz-user-name">Xavi Soler</span>
          <span className="cz-user-role">Team Lead · Santander</span>
        </div>
      </div>
    </header>
  );
}

// ComingSoon removed — all tabs have content now

function DealsTab({ onOpen }: { onOpen: (row: any, tab: string) => void }) {
  const [view, setView] = useState("pipeline");
  return view === "hoy"
    ? <DealsTable onOpen={onOpen} view={view} setView={setView}/>
    : <PipelineView onOpen={onOpen} view={view} setView={setView}/>;
}

function App() {
  const D = useData();
  const [view, setView] = useState("TO-DOs");
  const [detail, setDetail] = useState<DealDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // deep-link: ?deal=<id>&tab=<hist|atlas|next>
  useEffect(() => {
    if (D.loading) return;
    const p = new URLSearchParams(location.search);
    const id = p.get("deal");
    if (!id) return;
    fetchDealDetail(id).then(setDetail);
  }, [D.loading]);

  const handleOpen = useCallback((row: any, _tab?: string) => {
    if (!row.id) return;
    setDetailLoading(true);
    fetchDealDetail(row.id).then(d => {
      setDetail(d);
      setDetailLoading(false);
    }).catch(() => setDetailLoading(false));
  }, []);

  if (D.loading) {
    return (
      <div className="cz-app">
        <TopBar view={view} onNav={setView}/>
        <main className="cz-main" style={{display:"flex",alignItems:"center",justifyContent:"center",minHeight:"60vh"}}>
          <p style={{color:"var(--ink-3)",fontSize:15}}>Cargando datos...</p>
        </main>
      </div>
    );
  }

  return (
    <div className="cz-app">
      <TopBar view={view} onNav={setView}/>
      <main className="cz-main">
        {view === "TO-DOs" && <TodoView onOpen={handleOpen}/>}
        {view === "Deals" && <DealsTab onOpen={handleOpen}/>}
        {view === "Forecast" && <ForecastView/>}
        {view === "1:1" && <OneOnOneView onOpen={handleOpen}/>}
      </main>
      {detailLoading && (
        <div className="cz-overlay" style={{background:"rgba(28,24,16,.25)"}}>
          <p style={{color:"white",fontSize:15}}>Cargando deal...</p>
        </div>
      )}
      {detail && !detailLoading && (
        <DealWorkspace detail={detail} initialTab="hist" onClose={() => setDetail(null)}/>
      )}
    </div>
  );
}

export default App;
