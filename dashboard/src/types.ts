// Shapes written by export_data.py

export type Sleeve = "reserve" | "equity" | "spread" | "vol";
export type State = "stressed-bull" | "stressed-bear" | "calm-bull" | "calm-bear";

export interface RunListItem { run_id: string; notes: string | null }

export interface Checks {
  ran_at: string;
  checks: { name: string; ok: boolean; error: string }[];
}

export interface RunData {
  run_id: string;
  mode: string;
  broker: string;
  sleeves_on: boolean;
  regime_run_id: string | null;
  data_to: string;
  start_year: number;
  end_year: number;
  last_run: string;
  duration_s: number | null;
  nav: number;
  start_cash: number;
  mood: Record<State, number>;
  trades: { d: string; sleeve: string; qty: number; sym: string; price: number }[];
  trade_count: number;
  capital: { from: string; to: string; layers: Record<Sleeve, number[]>; now: Record<Sleeve, number> };
  pnl: { month: string; rows: { n: string; today: number; mtd: number }[]; cum: Record<Sleeve, number[]> };
  breaker: { active: boolean; text: string };
  events: { d: string; kind: "MOOD" | "REBAL"; state?: State; msg: string }[];
  growth: { months: string[]; eq: number[]; spy: number[]; st: number[] };
  stats: { worst: number; spy_worst: number; sharpe: number; multiple: number; spy_multiple: number };
  checks_passed: number | null;
  checks_total: number | null;
}
