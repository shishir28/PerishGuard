import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './styles.css';

const DEFAULT_CUSTOMER = new URLSearchParams(window.location.search).get('customer') || 'C010';

const RISK_QUERY = 'Show me the highest risk batches';
const ANOMALY_QUERY = 'Show me the latest anomalies';
const TELEMETRY_QUERY = 'Show me the latest sensor readings';

async function nlQuery(customerId, question) {
  const response = await fetch('/api/nl-query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customerId, question }),
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}`);
  }
  return response.json();
}

function useNlQuery(customerId, question) {
  const [state, setState] = useState({ status: 'idle', data: null, error: null });

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, status: 'loading' }));
    try {
      const data = await nlQuery(customerId, question);
      setState({ status: 'ready', data, error: null });
    } catch (err) {
      setState({ status: 'error', data: null, error: err.message });
    }
  }, [customerId, question]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}

function App() {
  const [customerId, setCustomerId] = useState(DEFAULT_CUSTOMER);
  const [pendingCustomer, setPendingCustomer] = useState(DEFAULT_CUSTOMER);

  const risk = useNlQuery(customerId, RISK_QUERY);
  const anomalies = useNlQuery(customerId, ANOMALY_QUERY);
  const telemetry = useNlQuery(customerId, TELEMETRY_QUERY);

  const [question, setQuestion] = useState('Which batches are at the highest spoilage risk?');
  const [chat, setChat] = useState({ status: 'idle', data: null, error: null });

  const totals = useMemo(() => {
    const rows = risk.data?.rows ?? [];
    const active = rows.length;
    const critical = rows.filter((r) => r.RiskLevel === 'CRITICAL').length;
    const hours = rows.map((r) => Number(r.EstimatedHoursLeft) || 0);
    const avgHours = hours.length ? (hours.reduce((a, b) => a + b, 0) / hours.length).toFixed(1) : '—';
    const open = (anomalies.data?.rows ?? []).filter((r) => r.Severity !== 'INFO').length;
    return { active, critical, avgHours, alerts: open };
  }, [risk.data, anomalies.data]);

  const trend = useMemo(() => {
    const rows = (telemetry.data?.rows ?? []).slice().reverse();
    return rows.map((r) => ({
      time: String(r.ReadingAt || '').slice(11, 16) || '—',
      temp: Number(r.Temperature) || 0,
    }));
  }, [telemetry.data]);

  const routeScores = useMemo(() => {
    const rows = risk.data?.rows ?? [];
    const totals = new Map();
    for (const r of rows) {
      const key = r.ProductType || 'unknown';
      const cur = totals.get(key) || { sum: 0, n: 0 };
      cur.sum += Number(r.SpoilageProbability) || 0;
      cur.n += 1;
      totals.set(key, cur);
    }
    return [...totals.entries()].map(([name, v]) => ({
      name,
      spoilage: Math.round((v.sum / v.n) * 100),
    }));
  }, [risk.data]);

  async function askQuestion(event) {
    event.preventDefault();
    setChat({ status: 'loading', data: null, error: null });
    try {
      const data = await nlQuery(customerId, question);
      setChat({ status: 'ready', data, error: null });
    } catch (err) {
      setChat({ status: 'error', data: null, error: err.message });
    }
  }

  function applyCustomer(event) {
    event.preventDefault();
    const next = pendingCustomer.trim();
    if (next) setCustomerId(next);
  }

  function refreshAll() {
    risk.refresh();
    anomalies.refresh();
    telemetry.refresh();
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">PerishGuard</p>
          <h1>Cold-chain command center</h1>
        </div>
        <form className="customer" onSubmit={applyCustomer}>
          <Icon name="customer" />
          <input
            value={pendingCustomer}
            onChange={(e) => setPendingCustomer(e.target.value)}
            placeholder="Customer ID"
            aria-label="Customer ID"
          />
          <button type="submit" aria-label="Switch customer">→</button>
        </form>
      </header>

      <section className="metrics" aria-label="Operational metrics">
        <Metric icon="batch" label="Active batches" value={totals.active} />
        <Metric icon="warning" label="Critical risk" value={totals.critical} tone="danger" />
        <Metric icon="clock" label="Avg hours left" value={totals.avgHours} />
        <Metric icon="pulse" label="Open anomalies" value={totals.alerts} tone="warn" />
      </section>

      <section className="workspace">
        <div className="primary">
          <div className="sectionHeader">
            <div>
              <p className="eyebrow">Spoilage Risk</p>
              <h2>Batch priority queue</h2>
            </div>
            <button className="iconButton" aria-label="Refresh" title="Refresh" onClick={refreshAll}>
              <Icon name="refresh" />
            </button>
          </div>
          <PanelBody state={risk}>
            <div className="riskTable">
              {(risk.data?.rows ?? []).map((row) => (
                <article className="riskRow" key={row.BatchId}>
                  <div>
                    <strong>{row.BatchId}</strong>
                    <span>{row.ProductType}</span>
                  </div>
                  <RiskBadge risk={row.RiskLevel || 'LOW'} />
                  <div className="probability">
                    <span>{Math.round((Number(row.SpoilageProbability) || 0) * 100)}%</span>
                    <div><i style={{ width: `${(Number(row.SpoilageProbability) || 0) * 100}%` }} /></div>
                  </div>
                  <div className="hours">
                    {row.EstimatedHoursLeft != null
                      ? `${Number(row.EstimatedHoursLeft).toFixed(1)}h`
                      : '—'}
                  </div>
                </article>
              ))}
              {risk.status === 'ready' && (risk.data?.rows ?? []).length === 0 && (
                <p className="empty">No risk records for this customer yet.</p>
              )}
            </div>
          </PanelBody>
        </div>

        <div className="chartPanel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Telemetry</p>
              <h2>Recent temperature</h2>
            </div>
          </div>
          <PanelBody state={telemetry}>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={trend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#d9e2dc" vertical={false} />
                <XAxis dataKey="time" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Line type="monotone" dataKey="temp" stroke="#2c7a5a" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </PanelBody>
        </div>
      </section>

      <section className="lowerGrid">
        <div className="panel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Anomalies</p>
              <h2>Live flags</h2>
            </div>
          </div>
          <PanelBody state={anomalies}>
            <div className="anomalyList">
              {(anomalies.data?.rows ?? []).slice(0, 8).map((row, i) => (
                <div className="anomaly" key={i}>
                  <RiskBadge risk={row.Severity || 'INFO'} />
                  <div>
                    <strong>{row.SensorType}</strong>
                    <span>{row.BatchId} | {row.AnomalyType} | {Number(row.ReadingValue ?? 0).toFixed(2)}</span>
                  </div>
                </div>
              ))}
              {anomalies.status === 'ready' && (anomalies.data?.rows ?? []).length === 0 && (
                <p className="empty">No anomalies detected for this customer.</p>
              )}
            </div>
          </PanelBody>
        </div>

        <div className="panel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Risk by product</p>
              <h2>Average spoilage probability</h2>
            </div>
          </div>
          <PanelBody state={risk}>
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={routeScores} layout="vertical" margin={{ left: 12, right: 12, top: 4, bottom: 4 }}>
                <XAxis type="number" hide domain={[0, 100]} />
                <YAxis type="category" dataKey="name" width={128} tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="spoilage" radius={[0, 5, 5, 0]}>
                  {routeScores.map((d, i) => (
                    <Cell key={i} fill={d.spoilage >= 70 ? '#c9472b' : d.spoilage >= 40 ? '#e0a458' : '#2c7a5a'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </PanelBody>
        </div>

        <div className="panel chatPanel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Ask Data</p>
              <h2>Shipment chat</h2>
            </div>
          </div>
          <form onSubmit={askQuestion} className="askForm">
            <input value={question} onChange={(e) => setQuestion(e.target.value)} />
            <button type="submit" aria-label="Ask question" disabled={chat.status === 'loading'}>
              <Icon name="send" />
            </button>
          </form>
          <div className="answer">
            {chat.status === 'loading' && <p>Thinking…</p>}
            {chat.status === 'error' && <p className="errorText">Query failed: {chat.error}</p>}
            {chat.status === 'ready' && chat.data && (
              <>
                <p>{chat.data.summary}</p>
                <span>{chat.data.chart} view | {(chat.data.rows || []).length} rows</span>
              </>
            )}
            {chat.status === 'idle' && (
              <p>Ask about risk, anomalies, routes, carriers, packaging, or vendors.</p>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function PanelBody({ state, children }) {
  if (state.status === 'loading' && !state.data) {
    return <p className="empty">Loading…</p>;
  }
  if (state.status === 'error') {
    return <p className="errorText">Failed to load: {state.error}</p>;
  }
  return children;
}

function Metric({ icon, label, value, tone = 'neutral' }) {
  return (
    <div className={`metric ${tone}`}>
      <Icon name={icon} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RiskBadge({ risk }) {
  return <span className={`riskBadge ${String(risk).toLowerCase()}`}>{risk}</span>;
}

function Icon({ name }) {
  const paths = {
    batch: 'M4 7l8-4 8 4-8 4-8-4Zm0 4l8 4 8-4M4 15l8 4 8-4',
    warning: 'M12 3l9 16H3L12 3Zm0 6v4m0 3h.01',
    clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l3 2',
    pulse: 'M3 12h4l2-6 4 12 2-6h6',
    refresh: 'M20 7v5h-5M4 17v-5h5M18 9a6 6 0 0 0-10-2M6 15a6 6 0 0 0 10 2',
    send: 'M4 4l16 8-16 8 3-8-3-8Zm3 8h13',
    customer: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

createRoot(document.getElementById('root')).render(<App />);
