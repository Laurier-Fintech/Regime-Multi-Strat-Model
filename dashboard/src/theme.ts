// Colours and formatters, copied from the design files

export const C = {
  bg: "#04070A", panel: "#060C10", line: "#12313A", line2: "#1F5866",
  text: "#D6E8EC", dim: "#7F9EA8", cyan: "#5EE6FF", amber: "#FFAE42",
  green: "#3DDC97", red: "#FF5C4D", brass: "#C9A15A", cream: "#EDE3CF",
};

export const MOOD_COL = { "stressed-bull": "#C9A15A", "stressed-bear": "#FFAE42", "calm-bull": "#5EE6FF", "calm-bear": "#2F8FB0" } as const;
export const SLEEVE_COL = { reserve: "#5EE6FF", equity: "#1B6E80", spread: "#C9A15A", vol: "#2FA7C0" } as const;

// 0.9985 --> "99.8%", 0.0015 --> "0.1%", 0 --> "0%"
export const pctMood = (v: number) => {
  const s = (v * 100).toFixed(1).replace(/\.0$/, "");
  return (s === "-0" ? "0" : s) + "%";
};

// weights: 0.79 --> "79%", 0.0055 --> "0.5%", 0 --> "0%"
export const pctW = (v: number) => {
  const p = v * 100;
  if (Math.abs(p) < 0.05) return "0%";
  return (Math.abs(p) < 1 ? p.toFixed(1) : Math.round(p).toString()) + "%";
};

// signed dollars: 21392 --> "+$21,392", -53184 --> "−$53,184"
export const money = (v: number) => {
  const r = Math.round(v);
  if (r === 0) return "0";
  return (r > 0 ? "+" : "−") + "$" + Math.abs(r).toLocaleString("en-US");
};

// $ millions for axis labels: 2e6 --> "+$2M", -2e5 --> "−$0.2M"
export const millions = (v: number) => {
  const m = Math.round((v / 1e6) * 10) / 10;
  if (m === 0) return "$0";
  return (m > 0 ? "+" : "−") + "$" + Math.abs(m).toString() + "M";
};

export const dollarsShort = (v: number) => {
  const m = v / 1e6;
  return "$" + (Number.isInteger(Math.round(m * 10) / 10) ? Math.round(m).toString() : m.toFixed(1)) + "M";
};

export const posNegCol = (v: number) => (Math.round(v) > 0 ? C.cyan : Math.round(v) < 0 ? C.amber : C.dim);
