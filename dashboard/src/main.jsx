import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Area,
  AreaChart,
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

const riskRows = [
  { batchId: 'B000370', productType: 'produce', route: 'Fresno -> Brisbane', risk: 'CRITICAL', probability: 0.91, hours: 6.5, breaks: 4 },
  { batchId: 'B000114', productType: 'seafood', route: 'Osaka -> Sydney', risk: 'HIGH', probability: 0.73, hours: 14.2, breaks: 3 },
  { batchId: 'B000291', productType: 'dairy', route: 'Auckland -> Melbourne', risk: 'MEDIUM', probability: 0.48, hours: 31.8, breaks: 1 },
  { batchId: 'B000022', productType: 'bakery', route: 'Valencia -> Perth', risk: 'LOW', probability: 0.12, hours: 132.0, breaks: 0 },
];

const trend = [
  { time: '00:00', temp: 2.1, risk: 18 },
  { time: '04:00', temp: 2.4, risk: 21 },
  { time: '08:00', temp: 6.8, risk: 44 },
  { time: '12:00', temp: 8.2, risk: 67 },
  { time: '16:00', temp: 5.3, risk: 59 },
  { time: '20:00', temp: 3.6, risk: 38 },
];

const routeScores = [
  { name: 'Fresno -> Brisbane', spoilage: 86 },
  { name: 'Osaka -> Sydney', spoilage: 62 },
  { name: 'Auckland -> Melbourne', spoilage: 34 },
  { name: 'Rotterdam -> Perth', spoilage: 27 },
];

const anomalyRows = [
  { sensor: 'temperature', type: 'rate_of_change', severity: 'CRITICAL', value: '8.2 C', batch: 'B000370' },
  { sensor: 'temperature', type: 'statistical', severity: 'CRITICAL', value: '4.8 sigma', batch: 'B000370' },
  { sensor: 'light', type: 'light', severity: 'WARNING', value: '420 lux', batch: 'B000114' },
  { sensor: 'humidity', type: 'threshold', severity: 'WARNING', value: '87%', batch: 'B000291' },
];

const insights = [
  { label: 'Route signal', value: 'Fresno -> Brisbane', detail: 'Highest spoilage rate this period' },
  { label: 'Carrier score', value: 'FreshFleet', detail: 'Best composite quality score' },
  { label: 'Packaging', value: 'Insulated', detail: 'Lowest average cold-chain breaks' },
];

function App() {
  const [question, setQuestion] = useState('Which batches are at the highest spoilage risk?');
  const [answer, setAnswer] = useState(null);
  const [isAsking, setIsAsking] = useState(false);

  const totals = useMemo(() => {
    const active = riskRows.length;
    const critical = riskRows.filter((row) => row.risk === 'CRITICAL').length;
    const avgHours = riskRows.reduce((sum, row) => sum + row.hours, 0) / active;
    return { active, critical, avgHours: avgHours.toFixed(1), alerts: anomalyRows.length };
  }, []);

  async function askQuestion(event) {
    event.preventDefault();
    setIsAsking(true);
    try {
      const response = await fetch('/api/nl-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customerId: 'C010', question }),
      });
      if (!response.ok) throw new Error('Query unavailable');
      setAnswer(await response.json());
    } catch {
      setAnswer({
        summary: 'Highest current risk is batch B000370 on Fresno -> Brisbane with 91% spoilage probability and 6.5 hours estimated shelf life remaining.',
        chart: 'bar',
        rows: riskRows,
      });
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">PerishGuard</p>
          <h1>Cold-chain command center</h1>
        </div>
        <div className="customer">
          <Icon name="customer" />
          <span>C010</span>
        </div>
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
            <button className="iconButton" aria-label="Refresh risk queue" title="Refresh risk queue">
              <Icon name="refresh" />
            </button>
          </div>
          <div className="riskTable">
            {riskRows.map((row) => (
              <article className="riskRow" key={row.batchId}>
                <div>
                  <strong>{row.batchId}</strong>
                  <span>{row.productType} | {row.route}</span>
                </div>
                <RiskBadge risk={row.risk} />
                <div className="probability">
                  <span>{Math.round(row.probability * 100)}%</span>
                  <div><i style={{ width: `${row.probability * 100}%` }} /></div>
                </div>
                <div className="hours">{row.hours.toFixed(1)}h</div>
              </article>
            ))}
          </div>
        </div>

        <div className="chartPanel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Telemetry</p>
              <h2>Temperature and risk</h2>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
              <CartesianGrid stroke="#d9e2dc" vertical={false} />
              <XAxis dataKey="time" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip />
              <Line type="monotone" dataKey="temp" stroke="#2c7a5a" strokeWidth={3} dot={false} />
              <Line type="monotone" dataKey="risk" stroke="#c9472b" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
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
          <div className="anomalyList">
            {anomalyRows.map((row) => (
              <div className="anomaly" key={`${row.batch}-${row.sensor}-${row.type}`}>
                <RiskBadge risk={row.severity} />
                <div>
                  <strong>{row.sensor}</strong>
                  <span>{row.batch} | {row.type} | {row.value}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Business Insights</p>
              <h2>Weekly signals</h2>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={routeScores} layout="vertical" margin={{ left: 12, right: 12, top: 4, bottom: 4 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={128} tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="spoilage" radius={[0, 5, 5, 0]}>
                {routeScores.map((_, index) => <Cell key={index} fill={index === 0 ? '#c9472b' : '#2c7a5a'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="insightStrip">
            {insights.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.detail}</small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel chatPanel">
          <div className="sectionHeader compact">
            <div>
              <p className="eyebrow">Ask Data</p>
              <h2>Shipment chat</h2>
            </div>
          </div>
          <form onSubmit={askQuestion} className="askForm">
            <input value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button type="submit" aria-label="Ask question" title="Ask question" disabled={isAsking}>
              <Icon name="send" />
            </button>
          </form>
          <div className="answer">
            {answer ? (
              <>
                <p>{answer.summary}</p>
                <span>{answer.chart} view | {(answer.rows || []).length} rows</span>
              </>
            ) : (
              <p>Ask about risk, anomalies, routes, carriers, packaging, or vendors.</p>
            )}
          </div>
        </div>
      </section>
    </main>
  );
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
  return <span className={`riskBadge ${risk.toLowerCase()}`}>{risk}</span>;
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
