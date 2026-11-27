// 3D growth box: Regent vs S&P 500, stressed periods on the floor, drawdown curtain below.
// Port of the "both_room" view in Docs/design/regent_growth_box.dc.html. Labels are HTML spans over the SVG.
import { useEffect, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import type { RunData } from "./types";
import { C, dollarsShort } from "./theme";

type P3 = [number, number, number];
interface Line { p: string; c: string; w: number; o: string; d: string }
interface Poly { p: string; f: string; s: string }
interface Tag { x: number; y: number; t: string; c: string; a: "start" | "middle" | "end"; s: number }

const CY = C.cyan, GR = C.line2, DK = C.line, BR = C.brass, DIM = C.dim, AM = C.amber, TX = C.text;
const VIEWS = [
  { n: "FRONT", rot: 0, ph: 0.06 },
  { n: "ANGLE", rot: -0.45, ph: 0.3 },
  { n: "SIDE", rot: -1.15, ph: 0.22 },
  { n: "TOP", rot: 0, ph: 1.15 },
];

const fx = (n: number) => n.toFixed(1);

function scene(run: RunData, th: number, ph: number) {
  const EQ = run.growth.eq, SPY = run.growth.spy, ST = run.growth.st, MONTHS = run.growth.months;
  const N = EQ.length;
  const F = 560, Dz = 3.9, cx = 380, cy = 268;

  const P = (x: number, y: number, z: number): P3 => {
    const x1 = x * Math.cos(th) + z * Math.sin(th), z1 = -x * Math.sin(th) + z * Math.cos(th);
    const y2 = y * Math.cos(ph) + z1 * Math.sin(ph), z2 = -y * Math.sin(ph) + z1 * Math.cos(ph);
    const s = F / (z2 + Dz);
    return [cx + x1 * s, cy - y2 * s, z2];
  };
  const pt = (a: P3) => fx(a[0]) + "," + fx(a[1]);
  const lines: Line[] = [], bg: Poly[] = [], tags: Tag[] = [];
  const fog = (pts: P3[]) => {
    const z = pts.reduce((a, q) => a + q[2], 0) / pts.length;
    return Math.max(0.25, Math.min(1, 1.05 - 0.32 * z));
  };
  const L = (pts: P3[], c: string, w = 1, o = 1, d = "none") =>
    lines.push({ p: pts.map(pt).join(" "), c, w, o: (o * fog(pts)).toFixed(2), d });
  const tag = (p: P3, t: string, c = DIM, a: Tag["a"] = "middle", s = 10, dy = 0) => tags.push({ x: p[0], y: p[1] + dy, t, c, a, s });

  // scales: y follows the run (design: 0.5x..7.4x --> -0.4..0.7)
  const maxV = Math.max(...EQ, ...SPY), minV = Math.min(...EQ, ...SPY);
  const lo = Math.min(0.5, minV * 0.98), hi = maxV * 1.002;
  const X = (i: number) => -1.6 + (3.2 * i) / Math.max(1, N - 1);
  const Y = (x: number) => -0.4 + (1.1 * (x - lo)) / (hi - lo);
  const B = -0.4, KD = 2.2;
  const dd: number[] = [];
  { let m = -1e9; for (const v of EQ) { m = Math.max(m, v); dd.push(v / m - 1); } }

  const FY = -0.78, x0 = -1.75, x1 = 1.75, z0 = -0.5, z1 = 0.5;
  const farZ = P(0, 0, z1)[2] > P(0, 0, z0)[2] ? z1 : z0, nearZ = farZ === z1 ? z0 : z1, wz = farZ * 0.98;

  // floor + grid
  bg.push({ p: [P(x0, FY, z0), P(x1, FY, z0), P(x1, FY, z1), P(x0, FY, z1)].map(pt).join(" "), f: "rgba(8,26,32,.7)", s: "rgba(31,88,102,.9)" });
  for (let k = 0; k <= 14; k++) { const x = x0 + ((x1 - x0) * k) / 14; L([P(x, FY, z0), P(x, FY, z1)], GR, 1, 0.7); }
  for (let k = 0; k <= 4; k++) { const z = z0 + ((z1 - z0) * k) / 4; L([P(x0, FY, z), P(x1, FY, z)], GR, 1, 0.7); }

  // the two far walls with grids
  {
    const TY = 0.85;
    const farX = P(x1, 0, 0)[2] > P(x0, 0, 0)[2] ? x1 : x0, nearX = farX === x1 ? x0 : x1;
    bg.push({ p: [P(x0, FY, farZ), P(x1, FY, farZ), P(x1, TY, farZ), P(x0, TY, farZ)].map(pt).join(" "), f: "rgba(14,42,52,.55)", s: "rgba(31,88,102,.9)" });
    bg.push({ p: [P(farX, FY, z0), P(farX, FY, z1), P(farX, TY, z1), P(farX, TY, z0)].map(pt).join(" "), f: "rgba(10,32,40,.6)", s: "rgba(31,88,102,.9)" });
    L([P(x0, TY, farZ), P(x1, TY, farZ)], GR, 1, 0.7); L([P(farX, TY, z0), P(farX, TY, z1)], GR, 1, 0.7);
    L([P(farX, FY, farZ), P(farX, TY, farZ)], GR, 1, 0.8); L([P(nearX, FY, farZ), P(nearX, TY, farZ)], GR, 1, 0.6); L([P(farX, FY, nearZ), P(farX, TY, nearZ)], GR, 1, 0.6);
    for (let k = 1; k < 6; k++) { const y = FY + ((TY - FY) * k) / 6; L([P(x0, y, farZ), P(x1, y, farZ)], DK, 1, 1); L([P(farX, y, z0), P(farX, y, z1)], DK, 1, 1); }
    for (let k = 1; k < 14; k++) { const x = x0 + ((x1 - x0) * k) / 14; L([P(x, FY, farZ), P(x, TY, farZ)], DK, 1, 0.8); }
    for (let k = 1; k < 4; k++) { const z = z0 + ((z1 - z0) * k) / 4; L([P(farX, FY, z), P(farX, TY, z)], DK, 1, 0.8); }
  }

  // shadow of the line on the floor + drop lines
  L(EQ.map((x, i) => P(X(i), FY, 0)), CY, 2, 0.22);
  for (let i = 0; i < N; i += 12) L([P(X(i), FY, 0), P(X(i), Y(EQ[i]), 0)], CY, 1, 0.14);

  // stressed periods painted on the floor
  {
    let i = 0;
    while (i < N) {
      if (ST[i] > 0.5) {
        let j = i;
        while (j + 1 < N && ST[j + 1] > 0.5) j++;
        const a = X(i) - 0.008, b = X(j) + 0.008;
        bg.push({ p: [P(a, FY, z0), P(b, FY, z0), P(b, FY, z1), P(a, FY, z1)].map(pt).join(" "), f: "rgba(255,174,66,.30)", s: "none" });
        L([P(a, FY, z0), P(a, FY, z1)], AM, 1.5, 0.95); L([P(b, FY, z0), P(b, FY, z1)], AM, 1.5, 0.95);
        i = j + 1;
      } else i++;
    }
  }

  // S&P 500 on the back wall
  {
    const sp = SPY.map((x, i) => P(X(i), Y(x), wz));
    bg.push({ p: sp.concat([P(X(N - 1), FY, wz), P(X(0), FY, wz)]).map(pt).join(" "), f: "rgba(157,180,188,.10)", s: "none" });
    L(sp, "#B8CCD3", 1.8, 0.95);
    const li = Math.min(30, N - 1);
    const lp = P(X(li), Y(SPY[li]) + 0.12, wz);
    tags.push({ x: lp[0], y: lp[1], t: "S&P 500", c: "#C8D8DE", a: "middle", s: 15 });
  }

  // curtain: one bar every 2 months, drawdown hanging below
  for (let i = 0; i < N; i += 2) L([P(X(i), B, 0), P(X(i), Y(EQ[i]), 0)], CY, 1.3, 0.22 + (0.55 * i) / N);
  for (let i = 0; i < N; i += 2) if (dd[i] < -0.005) L([P(X(i), B, 0), P(X(i), B + dd[i] * KD, 0)], AM, 1.3, 0.85);

  // $ levels (multiples of starting cash) --> back-wall lines, milestones where Regent first crossed each
  const step = hi <= 10 ? 1 : hi <= 20 ? 2 : hi <= 50 ? 5 : 10;
  const levels: number[] = [];
  for (let lv = step; lv <= hi; lv += step) if (lv >= lo) levels.push(lv);
  for (const lv of levels) {
    if (lv <= 1) continue;
    const y = Y(lv), i = EQ.findIndex((x) => x >= lv);
    if (i > 0) { L([P(X(i), y, 0), P(X(i), y, wz)], BR, 1, 0.8, "2 3"); tag(P(X(i), y, 0), MONTHS[i].slice(0, 4), BR, "middle", 9, -8); }
  }

  const fr = EQ.map((x, i) => P(X(i), Y(x), 0));
  L(fr, CY, 2.2, 1); L([P(-1.6, B, 0), P(1.6, B, 0)], TX, 1, 0.35);
  tag(P(1.66, Y(SPY[N - 1]), wz), `S&P 500 ${run.stats.spy_multiple.toFixed(2)}×`, DIM, "start", 10, 4);

  // quiet axes: years along the front of the floor, $ levels up the back wall
  for (let yr = run.start_year; yr <= run.end_year; yr += 3) {
    let i = MONTHS.findIndex((m) => m.startsWith(String(yr)));
    if (i < 0) i = N - 1;
    const q = P(X(i), FY, nearZ);
    tags.push({ x: q[0], y: q[1] + 14, t: String(yr), c: DIM, a: "middle", s: 12 });
  }
  for (const lv of levels) {
    const y = Y(lv);
    L([P(x0, y, wz), P(x1, y, wz)], DK, 1, 0.9);
    const q = P(x0, y, wz);
    tags.push({ x: q[0] - 6, y: q[1] + 3, t: dollarsShort(lv * run.start_cash), c: DIM, a: "end", s: 12 });
  }
  tag(P(1.66, Y(EQ[N - 1]), 0), "REGENT", CY, "start", 10, 4);

  return { bg, lines, tags, now: fr[N - 1] };
}

export default function GrowthBox({ run }: { run: RunData }) {
  const cam = useRef({ rot: -0.45, ph: 0.3, auto: true, drag: null as null | { x: number; y: number }, snap: null as null | { rot: number; ph: number }, last: Date.now(), t0: Date.now() });
  const [t, setT] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const iv = setInterval(() => {
      const c = cam.current, n = Date.now(), dt = (n - c.last) / 1000;
      c.last = n;
      if (c.snap && !c.drag) {
        const k = Math.min(1, dt * 5);
        c.rot += (c.snap.rot - c.rot) * k;
        c.ph += (c.snap.ph - c.ph) * k;
        if (Math.abs(c.snap.rot - c.rot) < 0.002 && Math.abs(c.snap.ph - c.ph) < 0.002) c.snap = null;
      } else if (c.auto && !c.drag) c.rot += 0.3 * dt;
      setT((n - c.t0) / 1000);
    }, 50);
    return () => clearInterval(iv);
  }, []);

  const c = cam.current;
  const { bg, lines, tags, now } = scene(run, c.rot, c.ph);
  const ph2 = (t % 2.4) / 2.4;
  const s = run.stats;
  const navStr = "$" + Math.round(run.nav).toLocaleString("en-US");
  const stats = [
    { l: "WORST DROP", v: "−" + Math.abs(s.worst * 100).toFixed(1) + "%", c: AM },
    { l: "SPY WORST", v: "−" + Math.abs(s.spy_worst * 100).toFixed(1) + "%", c: DIM },
    { l: "SHARPE", v: s.sharpe.toFixed(2), c: TX },
  ];

  const onDown = (e: RPointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest?.("button")) return;
    e.preventDefault();
    c.drag = { x: e.clientX, y: e.clientY };
    c.auto = false;
    c.snap = null;
    setPaused(true);
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* ignore */ }
  };
  const onMove = (e: RPointerEvent<HTMLDivElement>) => {
    if (!c.drag) return;
    c.rot += (e.clientX - c.drag.x) * 0.01;
    c.ph = Math.max(0.05, Math.min(0.5, c.ph + (e.clientY - c.drag.y) * 0.005));
    c.drag = { x: e.clientX, y: e.clientY };
  };
  const onUp = () => { c.drag = null; };
  const resume = () => { c.auto = true; c.snap = null; setPaused(false); };
  const snapTo = (rot: number, ph: number) => () => {
    const near = rot + 2 * Math.PI * Math.round((c.rot - rot) / (2 * Math.PI));
    c.auto = false;
    c.snap = { rot: near, ph };
    setPaused(true);
  };

  const anchor = (a: Tag["a"]) => (a === "middle" ? "translate(-50%,-100%)" : a === "end" ? "translate(-100%,-100%)" : "translate(0,-100%)");

  return (
    <div onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}
      style={{ position: "relative", width: 760, height: 600, boxSizing: "border-box", border: `1px solid ${C.line2}`, background: C.panel, color: TX, fontFamily: "'Azeret Mono',monospace", fontSize: 12, overflow: "hidden", cursor: "grab", touchAction: "none", userSelect: "none" }}>
      <div style={{ position: "absolute", zIndex: 1, left: 16, right: 16, top: 12, display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "1px solid rgba(201,161,90,.35)", paddingBottom: 6 }}>
        <span style={{ fontFamily: "'Cormorant SC',serif", fontSize: 22, fontWeight: 600, letterSpacing: 3, color: BR, lineHeight: 1 }}>Portfolio</span>
        {paused && (
          <button aria-label="Resume rotation" onClick={resume} style={{ font: "inherit", fontSize: 11, letterSpacing: 1, color: CY, background: "transparent", border: `1px solid ${GR}`, padding: "5px 10px", minHeight: 28, cursor: "pointer" }}>↻ ROTATE</button>
        )}
      </div>
      <svg viewBox="0 0 760 600" style={{ position: "absolute", inset: 0, width: 761, height: 600, cursor: "grab", touchAction: "none", left: -1 }} role="img"
        aria-label={`Portfolio growth since ${run.start_year} against the S&P 500. Drag to rotate.`}>
        {bg.map((g, i) => <polygon key={"b" + i} points={g.p} fill={g.f} stroke={g.s} strokeWidth={1} />)}
        {lines.map((l, i) => <polyline key={"l" + i} points={l.p} fill="none" stroke={l.c} strokeWidth={l.w} opacity={l.o} strokeDasharray={l.d} />)}
        <circle cx={fx(now[0])} cy={fx(now[1])} r={(6 + 14 * ph2).toFixed(1)} fill="none" stroke={BR} opacity={(1 - ph2).toFixed(2)} />
        <circle cx={fx(now[0])} cy={fx(now[1])} r={5} fill={BR} />
      </svg>
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        {tags.map((k, i) => (
          <span key={i} style={{ position: "absolute", left: fx(k.x) + "px", top: fx(k.y) + "px", transform: anchor(k.a), color: k.c, fontSize: k.s, letterSpacing: 1, whiteSpace: "nowrap", lineHeight: 1 }}>{k.t}</span>
        ))}
      </div>
      <div style={{ position: "absolute", left: 24, top: 50, display: "flex", flexDirection: "column", gap: 3 }}>
        <span style={{ fontSize: 10, letterSpacing: 2, color: DIM }}>NET ASSET VALUE</span>
        <span style={{ fontSize: 28, fontWeight: 600, letterSpacing: 1, lineHeight: 1, color: TX }}>{navStr}</span>
        <span style={{ color: DIM }}>{s.multiple.toFixed(2)}× since {run.start_year} · SPY {s.spy_multiple.toFixed(2)}×</span>
      </div>
      <div style={{ position: "absolute", right: 24, top: 56, display: "flex", gap: 22, textAlign: "right" }}>
        {stats.map((x) => (
          <div key={x.l} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 10, letterSpacing: 2, color: DIM }}>{x.l}</span>
            <span style={{ fontSize: 18, color: x.c }}>{x.v}</span>
          </div>
        ))}
      </div>
      <div style={{ position: "absolute", right: 16, bottom: 14, display: "flex", gap: 4 }}>
        {VIEWS.map((v) => (
          <button key={v.n} aria-label={`Snap to ${v.n.toLowerCase()} view`} onClick={snapTo(v.rot, v.ph)}
            style={{ font: "inherit", fontSize: 10, letterSpacing: 1, color: DIM, background: "rgba(6,12,16,.8)", border: `1px solid ${GR}`, padding: "5px 9px", minHeight: 28, cursor: "pointer" }}>{v.n}</button>
        ))}
      </div>
    </div>
  );
}
