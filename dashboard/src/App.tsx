// Regent home: port of Docs/design/regent_home.dc.html, filled from public/data/*.json (see export_data.py)
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import GrowthBox from "./GrowthBox";
import type { Checks, RunData, RunListItem, Sleeve, State } from "./types";
import { C, MOOD_COL, SLEEVE_COL, millions, money, pctMood, pctW, posNegCol } from "./theme";

const DATA = "./data/";
const MOOD_ORDER: State[] = ["stressed-bull", "stressed-bear", "calm-bull", "calm-bear"];
const CAP_ORDER: Sleeve[] = ["reserve", "equity", "spread", "vol"];
const CUM_ORDER: Sleeve[] = ["equity", "reserve", "spread", "vol"];
const TABS = ["HOME", "REGIME", "ALLOCATION", "SLEEVES", "RISK", "PERFORMANCE", "BOOK", "SYSTEM"];

const sectionStyle: CSSProperties = { border: `1px solid ${C.line}`, background: C.panel, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8, boxSizing: "border-box", overflow: "hidden" };
const titleStyle: CSSProperties = { fontFamily: "'Cormorant SC',serif", color: C.brass, letterSpacing: 3, fontSize: 18, fontWeight: 600, lineHeight: 1.1, paddingBottom: 5, borderBottom: "1px solid rgba(201,161,90,.35)" };
const b = (color: string): CSSProperties => ({ color, fontWeight: 400 });

function Title({ children, right }: { children: ReactNode; right?: ReactNode }) {
  if (!right) return <div style={titleStyle}>{children}</div>;
  return (
    <div style={{ ...titleStyle, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span>{children}</span>
      <span style={{ fontFamily: "'Azeret Mono',monospace", fontSize: 10, letterSpacing: 1, color: C.dim, fontWeight: 400 }}>{right}</span>
    </div>
  );
}

function Legend({ items }: { items: { c: string; n: string; v: string }[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "3px 10px", fontSize: 11 }}>
      {items.map((x) => (
        <span key={x.n} style={{ display: "flex", justifyContent: "space-between", gap: 4, whiteSpace: "nowrap", color: C.dim }}>
          <span><span style={{ color: x.c }}>■</span> {x.n}</span>
          <b style={b(C.text)}>{x.v}</b>
        </span>
      ))}
    </div>
  );
}

function Header({ runs, runId, setRunId, run }: { runs: RunListItem[]; runId: string; setRunId: (r: string) => void; run: RunData }) {
  const checks = run.checks_total ? `${run.checks_passed}/${run.checks_total}` : "—";
  return (
    <header style={{ height: 72, flex: "none", boxSizing: "border-box", border: `1px solid ${C.line}`, background: C.panel, display: "flex", flexDirection: "column" }}>
      <div style={{ height: 30, display: "flex", alignItems: "center", gap: 20, padding: "0 16px", borderBottom: `1px solid ${C.line}`, fontSize: 11, color: C.dim }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>RUN
          <select aria-label="Run" value={runId} onChange={(e) => setRunId(e.target.value)}
            style={{ font: "inherit", color: C.text, background: C.bg, border: `1px solid ${C.line2}`, padding: "2px 4px" }}>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id}</option>)}
          </select>
        </label>
        <span>MODE <b style={b(C.cyan)}>{run.mode}</b></span>
        <span>BROKER <b style={b(C.green)}>● {run.broker}</b></span>
        <span>DATA TO <b style={b(C.text)}>{run.data_to}</b></span>
        <span>SLEEVES {run.sleeves_on ? <b style={b(C.green)}>ON</b> : <b style={b(C.amber)}>OFF · STAND-IN ETFS</b>}</span>
        <span style={{ marginLeft: "auto" }}>CHECKS <b style={b(C.text)}>{checks}</b> · LAST RUN {run.last_run}</span>
      </div>
      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 22, padding: "0 16px" }}>
        <span style={{ fontFamily: "'Cormorant SC',serif", fontSize: 24, fontWeight: 600, letterSpacing: 5, color: C.cream, lineHeight: 1 }}>Regent</span>
        <nav style={{ display: "flex", gap: 2 }}>
          {TABS.map((t, i) => (
            <a key={t} href="#" onClick={(e) => e.preventDefault()}
              style={i === 0
                ? { padding: "6px 9px", fontSize: 11, background: C.cyan, color: C.bg, textDecoration: "none" }
                : { padding: "6px 9px", fontSize: 11, color: C.dim, textDecoration: "none", border: `1px solid ${C.line}` }}>{t}</a>
          ))}
        </nav>
        <span style={{ marginLeft: "auto", color: C.dim }}>NAV <b style={{ color: C.text, fontSize: 16, fontWeight: 600 }}>${Math.round(run.nav).toLocaleString("en-US")}</b></span>
      </div>
    </header>
  );
}

function MarketMood({ run }: { run: RunData }) {
  const circ = 2 * Math.PI * 80;
  let off = 0;
  const segs = MOOD_ORDER.map((s) => {
    const v = run.mood[s];
    const len = Math.max(0, v * circ - (v > 0.004 ? 2 : 0));
    const o = { da: len.toFixed(1) + " " + circ.toFixed(1), dof: (-off).toFixed(1), c: MOOD_COL[s] };
    off += v * circ;
    return o;
  });
  const top = MOOD_ORDER.reduce((a, s) => (run.mood[s] > run.mood[a] ? s : a), MOOD_ORDER[0]);
  const [w1, w2] = top.toUpperCase().split("-");
  return (
    <section style={{ ...sectionStyle, height: 295, flex: "none" }}>
      <Title>Market Mood</Title>
      <div style={{ position: "relative", flex: 1, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg viewBox="0 0 200 200" style={{ height: "100%", maxHeight: 180, width: "auto" }} role="img" aria-label={`Mood ring: ${top.replace("-", " ")} ${pctMood(run.mood[top])}.`}>
          <circle cx={100} cy={100} r={80} fill="none" stroke="#0C1E24" strokeWidth={18} />
          {segs.map((o, i) => <circle key={i} cx={100} cy={100} r={80} fill="none" stroke={o.c} strokeWidth={18} strokeDasharray={o.da} strokeDashoffset={o.dof} transform="rotate(-90 100 100)" />)}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, pointerEvents: "none" }}>
          <span style={{ fontSize: 18, fontWeight: 600, letterSpacing: 2, color: MOOD_COL[top], textAlign: "center", lineHeight: 1.15 }}>{w1}<br />{w2}</span>
          <span style={{ fontSize: 15 }}>{pctMood(run.mood[top])}</span>
        </div>
      </div>
      <Legend items={MOOD_ORDER.map((s) => ({ c: MOOD_COL[s], n: s.replace("-", " "), v: pctMood(run.mood[s]) }))} />
    </section>
  );
}

function Trades({ run }: { run: RunData }) {
  const head: CSSProperties = { color: C.dim };
  return (
    <section style={{ ...sectionStyle, flex: 1 }}>
      <Title right={`${run.trade_count.toLocaleString("en-US")} SINCE ${run.start_year}`}>Trades</Title>
      <div style={{ display: "grid", gridTemplateColumns: "44px 58px 38px minmax(0,1fr) 62px", gap: "5px 6px", fontSize: 11 }}>
        <span style={head}>DATE</span><span style={head}>SLEEVE</span><span style={head}>SIDE</span><span style={head}>QTY · SYM</span><span style={{ ...head, textAlign: "right" }}>PRICE</span>
        {run.trades.map((r, i) => (
          <Row key={i}>
            <span style={{ color: C.dim }}>{r.d}</span>
            <span>{r.sleeve}</span>
            <span style={{ color: r.qty > 0 ? C.cyan : C.amber }}>{r.qty > 0 ? "BUY" : "SELL"}</span>
            <span>{Math.abs(r.qty).toLocaleString("en-US")} {r.sym}</span>
            <span style={{ textAlign: "right" }}>${r.price.toFixed(2)}</span>
          </Row>
        ))}
      </div>
    </section>
  );
}

const Row = ({ children }: { children: ReactNode }) => <>{children}</>;

function CapitalNow({ run }: { run: RunData }) {
  const L = run.capital.layers;
  const n = L.reserve.length;
  const X = (i: number) => ((i * 300) / Math.max(1, n - 1)).toFixed(1);
  let base = new Array(n).fill(0) as number[];
  const layers = CAP_ORDER.map((s) => {
    const top = base.map((v, i) => v + L[s][i]);
    const up = top.map((v, i) => X(i) + "," + (160 - v * 160).toFixed(1));
    const lo = base.map((v, i) => X(i) + "," + (160 - v * 160).toFixed(1)).reverse();
    base = top;
    return { p: up.concat(lo).join(" "), c: SLEEVE_COL[s] };
  });
  const now = run.capital.now;
  return (
    <section style={{ ...sectionStyle, height: 300, flex: "none" }}>
      <Title>Capital Now</Title>
      <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
        <svg viewBox="0 0 300 160" preserveAspectRatio="none" style={{ width: "100%", height: "100%", display: "block" }} role="img"
          aria-label={`100 percent chart of capital per sleeve since ${run.capital.from}, reserve now ${pctW(now.reserve)}.`}>
          {layers.map((a, i) => <polygon key={i} points={a.p} fill={a.c} />)}
        </svg>
        <span style={{ position: "absolute", right: 2, top: 2, fontSize: 10, color: C.bg, background: "rgba(214,232,236,.85)", padding: "1px 4px" }}>NOW · {pctW(now.reserve)} RESERVE</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.dim }}><span>{run.capital.from}</span><span>{run.capital.to}</span></div>
      <Legend items={CAP_ORDER.map((s) => ({ c: SLEEVE_COL[s], n: s, v: pctW(now[s]) }))} />
    </section>
  );
}

function SleevePL({ run }: { run: RunData }) {
  const cum = run.pnl.cum;
  const all = CUM_ORDER.flatMap((s) => cum[s]);
  const hi = Math.max(0.5e6, Math.ceil(Math.max(...all) / 0.5e6) * 0.5e6);
  const lo = Math.min(0, Math.floor(Math.min(...all) / 0.1e6) * 0.1e6);
  const Y = (v: number) => (100 - ((v - lo) / (hi - lo)) * 100).toFixed(1);
  const lines = CUM_ORDER.map((s) => ({ c: SLEEVE_COL[s], p: cum[s].map((v, i) => ((i * 280) / Math.max(1, cum[s].length - 1)).toFixed(1) + "," + Y(v)).join(" ") }));
  const last = (s: Sleeve) => cum[s][cum[s].length - 1];
  const small: CSSProperties = { color: C.dim, fontSize: 10 };
  return (
    <section style={{ ...sectionStyle, flex: 1 }}>
      <Title>Sleeve P&amp;L</Title>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 80px 90px", gap: "6px 8px", fontSize: 12 }}>
        <span style={small}>SLEEVE</span><span style={{ ...small, textAlign: "right" }}>TODAY</span><span style={{ ...small, textAlign: "right" }}>{run.pnl.month} MTD</span>
        {run.pnl.rows.map((r) => (
          <Row key={r.n}>
            <span style={{ color: r.n === "total" ? C.text : C.dim }}>{r.n}</span>
            <span style={{ textAlign: "right", color: posNegCol(r.today) }}>{money(r.today)}</span>
            <span style={{ textAlign: "right", color: posNegCol(r.mtd) }}>{money(r.mtd)}</span>
          </Row>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.dim, borderTop: `1px solid ${C.line}`, paddingTop: 6 }}>
        <span>CUMULATIVE P&amp;L BY SLEEVE</span><span>{run.start_year} TO {run.end_year}</span>
      </div>
      <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
        <svg viewBox="0 0 280 100" preserveAspectRatio="none" style={{ width: "100%", height: "100%", display: "block" }} role="img"
          aria-label={`Cumulative profit by sleeve since ${run.start_year}: ` + CUM_ORDER.map((s) => `${s} ${millions(last(s))}`).join(", ") + "."}>
          <line x1={0} y1={Y(0)} x2={280} y2={Y(0)} stroke={C.line2} strokeDasharray="3 3" />
          {lines.map((l, i) => <polyline key={i} points={l.p} fill="none" stroke={l.c} strokeWidth={1.8} vectorEffect="non-scaling-stroke" />)}
        </svg>
        <div style={{ position: "absolute", left: 0, top: 0, fontSize: 9, color: C.dim }}>{millions(hi)}</div>
        <div style={{ position: "absolute", left: 0, bottom: 0, fontSize: 9, color: C.dim }}>{millions(lo)}</div>
      </div>
      <div style={{ display: "flex", gap: 10, fontSize: 10, color: C.dim }}>
        {CUM_ORDER.map((s) => <span key={s}><span style={{ color: SLEEVE_COL[s] }}>━</span> {s}</span>)}
      </div>
    </section>
  );
}

function Events({ run }: { run: RunData }) {
  const br = run.breaker;
  const col = br.active ? C.red : C.green;
  return (
    <section style={{ ...sectionStyle, flex: 1.5 }}>
      <Title>Events</Title>
      <div style={{ display: "flex", alignItems: "center", gap: 10, border: `1px solid ${br.active ? "rgba(255,92,77,.5)" : "rgba(61,220,151,.5)"}`, background: br.active ? "rgba(255,92,77,.07)" : "rgba(61,220,151,.07)", padding: "5px 8px", fontSize: 11 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: col, flex: "none" }} />
        <span style={{ color: br.active ? "#FF8F84" : C.green, letterSpacing: 1, whiteSpace: "nowrap" }}>VIX BREAKER · {br.active ? "CUT" : "OFF"}</span>
        <span style={{ color: C.dim }}>{br.text}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "44px 62px minmax(0,1fr)", gap: "4px 8px", fontSize: 11 }}>
        {run.events.map((e, i) => (
          <Row key={i}>
            <span style={{ color: C.dim }}>{e.d}</span>
            <span style={{ color: e.kind === "MOOD" && e.state ? MOOD_COL[e.state] : C.cyan }}>{e.kind}</span>
            <span>{e.msg}</span>
          </Row>
        ))}
      </div>
    </section>
  );
}

function Health({ run, checks }: { run: RunData; checks: Checks | null }) {
  const allOk = !!checks && checks.checks.every((k) => k.ok);
  const dur = run.duration_s == null ? "—" : `${Math.floor(run.duration_s / 60)}m ${run.duration_s % 60}s`;
  const items = [
    { n: "checks", v: checks ? `${run.checks_passed}/${run.checks_total}` : "—", c: checks ? (allOk ? C.green : C.red) : C.dim },
    { n: "data to", v: run.data_to, c: C.green },
    { n: "backtest", v: dur, c: run.duration_s == null ? C.amber : C.green },
    { n: "regime run", v: run.regime_run_id ? run.regime_run_id.split("_").pop()! : "—", c: run.regime_run_id ? C.green : C.amber },
    { n: "sleeves", v: run.sleeves_on ? "ON" : "OFF", c: run.sleeves_on ? C.green : C.amber },
    { n: "broker", v: run.broker, c: C.green },
  ];
  const nOk = checks ? checks.checks.filter((k) => k.ok).length : 0;
  return (
    <section style={{ ...sectionStyle, flex: 1.5, gap: 6 }}>
      <Title>System Health</Title>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "4px 12px", fontSize: 11 }}>
        {items.map((h) => (
          <span key={h.n} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: h.c }} />
            <span style={{ color: C.dim }}>{h.n}</span>
            <b style={{ marginLeft: "auto", fontWeight: 400 }}>{h.v}</b>
          </span>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.dim, borderTop: `1px solid ${C.line}`, paddingTop: 5 }}>
        <span>{checks ? `SYSTEM CHECKS · ${nOk}/${checks.checks.length} ${allOk ? "PASS" : "· FAILING"} · ${checks.ran_at.slice(5)}` : "SYSTEM CHECKS · NOT RUN"}</span>
        <span>tests/system_check.py</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "3px 12px", fontSize: 10 }}>
        {(checks?.checks ?? []).map((k) => (
          <span key={k.name} title={k.error || undefined} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ color: k.ok ? C.green : C.red }}>{k.ok ? "OK" : "FAIL"}</span>
            <span style={{ color: C.text }}>{k.name}</span>
          </span>
        ))}
      </div>
    </section>
  );
}

export default function App() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<RunData | null>(null);
  const [checks, setChecks] = useState<Checks | null>(null);
  const [error, setError] = useState("");
  const scale = useFitScale(1440, 900);

  useEffect(() => {
    fetch(DATA + "runs.json").then((r) => r.json()).then((list: RunListItem[]) => {
      setRuns(list);
      if (list.length) setRunId(list[0].run_id);
      else setError("No finished backtest runs. Run: .venv/Scripts/python.exe dashboard/export_data.py");
    }).catch(() => setError("No data yet. Run: .venv/Scripts/python.exe dashboard/export_data.py"));
    fetch(DATA + "checks.json").then((r) => (r.ok ? r.json() : null)).then(setChecks).catch(() => setChecks(null));
  }, []);

  useEffect(() => {
    if (!runId) return;
    fetch(DATA + runId + ".json").then((r) => r.json()).then(setRun).catch(() => setError(`Could not load ${runId}.json`));
  }, [runId]);

  if (error) return <div style={{ color: C.amber, fontFamily: "'Azeret Mono',monospace", padding: 24 }}>{error}</div>;
  if (!run) return null;

  // the design is a fixed 1440x900 canvas --> zoom it to fit the window, centred
  return (
    <div style={{ position: "fixed", inset: 0, overflow: "hidden", background: C.bg }}>
      <div style={{ position: "absolute", left: "50%", top: "50%", transform: `translate(-50%,-50%) scale(${scale})` }}>
        <Home run={run} runs={runs} runId={runId} setRunId={setRunId} checks={checks} />
      </div>
    </div>
  );
}

function useFitScale(w: number, h: number) {
  const fit = () => Math.min(window.innerWidth / w, window.innerHeight / h);
  const [scale, setScale] = useState(fit);
  useEffect(() => {
    const onResize = () => setScale(fit());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return scale;
}

function Home({ run, runs, runId, setRunId, checks }: { run: RunData; runs: RunListItem[]; runId: string; setRunId: (r: string) => void; checks: Checks | null }) {
  return (
    <div style={{ width: 1440, height: 900, boxSizing: "border-box", padding: 12, background: C.bg, color: C.text, fontFamily: "'Azeret Mono',monospace", fontSize: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <Header runs={runs} runId={runId} setRunId={setRunId} run={run} />
      <div style={{ display: "flex", gap: 10, flex: "none", height: 600 }}>
        <aside style={{ width: 310, flex: "none", display: "flex", flexDirection: "column", gap: 10 }}>
          <MarketMood run={run} />
          <Trades run={run} />
        </aside>
        <div style={{ width: 760, height: 600, flex: "none" }}>
          <GrowthBox key={run.run_id} run={run} />
        </div>
        <aside style={{ width: 310, flex: "none", display: "flex", flexDirection: "column", gap: 10 }}>
          <CapitalNow run={run} />
          <SleevePL run={run} />
        </aside>
      </div>
      <div style={{ display: "flex", gap: 10, flex: 1, minHeight: 0 }}>
        <Events run={run} />
        <Health run={run} checks={checks} />
      </div>
    </div>
  );
}
