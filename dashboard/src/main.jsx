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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.error || `API ${response.status}`);
  }
  return payload;
}

async function nlQuery(customerId, question) {
  return fetchJson('/api/nl-query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customerId, question }),
  });
}

async function fetchBatchDetail(customerId, batchId) {
  return fetchJson(`/api/batches/${encodeURIComponent(batchId)}?customerId=${encodeURIComponent(customerId)}`);
}

async function fetchModelPerformance(customerId) {
  return fetchJson(`/api/model-performance?customerId=${encodeURIComponent(customerId)}`);
}

async function acknowledgeAnomaly(customerId, eventId) {
  return fetchJson(`/api/anomalies/${eventId}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customerId }),
  });
}

function useNlQuery(customerId, question) {
  const loader = useCallback(() => nlQuery(customerId, question), [customerId, question]);
  return useApiResource(loader, { enabled: Boolean(customerId && question) });
}

function useApiResource(loader, { enabled = true } = {}) {
  const [state, setState] = useState({ status: enabled ? 'loading' : 'idle', data: null, error: null });

  const refresh = useCallback(async () => {
    if (!enabled) {
      setState({ status: 'idle', data: null, error: null });
      return;
    }
    setState((current) => ({ status: current.data ? 'refreshing' : 'loading', data: current.data, error: null }));
    try {
      const data = await loader();
      setState({ status: 'ready', data, error: null });
    } catch (error) {
      setState((current) => ({ status: 'error', data: current.data, error: error.message }));
    }
  }, [enabled, loader]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}

function App() {
  const [customerId, setCustomerId] = useState(DEFAULT_CUSTOMER);
  const [pendingCustomer, setPendingCustomer] = useState(DEFAULT_CUSTOMER);
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [question, setQuestion] = useState('Which batches are at the highest spoilage risk?');
  const [chat, setChat] = useState({ status: 'idle', data: null, error: null });
  const [ackingEventId, setAckingEventId] = useState(null);

  const risk = useNlQuery(customerId, RISK_QUERY);
  const anomalies = useNlQuery(customerId, ANOMALY_QUERY);
  const telemetry = useNlQuery(customerId, TELEMETRY_QUERY);

  const batchLoader = useCallback(
    () => fetchBatchDetail(customerId, selectedBatchId),
    [customerId, selectedBatchId],
  );
  const batchDetail = useApiResource(batchLoader, { enabled: Boolean(customerId && selectedBatchId) });

  const performanceLoader = useCallback(
    () => fetchModelPerformance(customerId),
    [customerId],
  );
  const performance = useApiResource(performanceLoader, { enabled: Boolean(customerId) });

  useEffect(() => {
    const rows = risk.data?.rows ?? [];
    if (!rows.length) {
      setSelectedBatchId('');
      return;
    }
    if (!selectedBatchId || !rows.some((row) => row.BatchId === selectedBatchId)) {
      setSelectedBatchId(rows[0].BatchId);
    }
  }, [risk.data, selectedBatchId]);

  const totals = useMemo(() => {
    const rows = risk.data?.rows ?? [];
    const active = rows.length;
    const critical = rows.filter((row) => row.RiskLevel === 'CRITICAL').length;
    const hours = rows.map((row) => Number(row.EstimatedHoursLeft) || 0);
    const avgHours = hours.length ? (hours.reduce((sum, value) => sum + value, 0) / hours.length).toFixed(1) : '—';
    const open = (anomalies.data?.rows ?? []).filter((row) => !row.Acknowledged && row.Severity !== 'INFO').length;
    return { active, critical, avgHours, alerts: open };
  }, [anomalies.data, risk.data]);

  const trend = useMemo(() => {
    const rows = (telemetry.data?.rows ?? []).slice().reverse();
    return rows.map((row) => ({
      time: formatClock(row.ReadingAt),
      temp: Number(row.Temperature) || 0,
    }));
  }, [telemetry.data]);

  const routeScores = useMemo(() => {
    const rows = risk.data?.rows ?? [];
    const totalsByProduct = new Map();
    for (const row of rows) {
      const key = row.ProductType || 'unknown';
      const current = totalsByProduct.get(key) || { sum: 0, count: 0 };
      current.sum += Number(row.SpoilageProbability) || 0;
      current.count += 1;
      totalsByProduct.set(key, current);
    }
    return [...totalsByProduct.entries()].map(([name, value]) => ({
      name,
      spoilage: Math.round((value.sum / value.count) * 100),
    }));
  }, [risk.data]);

  const detailSensorTrend = useMemo(() => {
    const rows = batchDetail.data?.sensorHistory ?? [];
    return rows.map((row) => ({
      time: formatClock(row.ReadingAt),
      temperature: Number(row.Temperature) || 0,
      humidity: Number(row.Humidity) || 0,
    }));
  }, [batchDetail.data]);

  const predictionTrend = useMemo(() => {
    const rows = batchDetail.data?.predictionHistory ?? [];
    return rows.map((row) => ({
      time: formatClock(row.PredictedAt),
      probability: Math.round((Number(row.SpoilageProbability) || 0) * 100),
      hoursLeft: Number(row.EstimatedHoursLeft) || 0,
    }));
  }, [batchDetail.data]);

  const selectedSummary = batchDetail.data?.summary ?? null;
  const performanceOverview = performance.data?.overview ?? {};

  async function askQuestion(event) {
    event.preventDefault();
    setChat({ status: 'loading', data: null, error: null });
    try {
      const data = await nlQuery(customerId, question);
      setChat({ status: 'ready', data, error: null });
    } catch (error) {
      setChat({ status: 'error', data: null, error: error.message });
    }
  }

  function applyCustomer(event) {
    event.preventDefault();
    const next = pendingCustomer.trim();
    if (next) {
      setCustomerId(next);
      setSelectedBatchId('');
    }
  }

  function refreshAll() {
    risk.refresh();
    anomalies.refresh();
    telemetry.refresh();
    performance.refresh();
    if (selectedBatchId) {
      batchDetail.refresh();
    }
  }

  async function onAcknowledge(eventId) {
    setAckingEventId(eventId);
    try {
      await acknowledgeAnomaly(customerId, eventId);
      anomalies.refresh();
      if (selectedBatchId) {
        batchDetail.refresh();
      }
    } catch (error) {
      window.alert(error.message);
    } finally {
      setAckingEventId(null);
    }
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
            onChange={(event) => setPendingCustomer(event.target.value)}
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
                <button
                  type="button"
                  className={`riskRow ${selectedBatchId === row.BatchId ? 'active' : ''}`}
                  key={row.BatchId}
                  onClick={() => setSelectedBatchId(row.BatchId)}
                >
                  <div>
                    <strong>{row.BatchId}</strong>
                    <span>{row.ProductType}</span>
                  </div>
                  <RiskBadge risk={row.RiskLevel || 'LOW'} />
                  <div className="probability">
                    <span>{formatPercent(row.SpoilageProbability)}</span>
                    <div><i style={{ width: `${(Number(row.SpoilageProbability) || 0) * 100}%` }} /></div>
                  </div>
                  <div className="hours">
                    {row.EstimatedHoursLeft != null ? `${Number(row.EstimatedHoursLeft).toFixed(1)}h` : '—'}
                  </div>
                </button>
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
              {(anomalies.data?.rows ?? []).slice(0, 8).map((row) => (
                <div className="anomaly" key={row.EventId || `${row.BatchId}-${row.DetectedAt}`}>
                  <RiskBadge risk={row.Severity || 'INFO'} />
                  <div className="anomalyContent">
                    <strong>{row.SensorType}</strong>
                    <span>{row.BatchId} | {row.AnomalyType} | {Number(row.ReadingValue ?? 0).toFixed(2)}</span>
                  </div>
                  <button
                    type="button"
                    className={`ghostButton ${row.Acknowledged ? 'done' : ''}`}
                    disabled={Boolean(row.Acknowledged) || ackingEventId === row.EventId}
                    onClick={() => onAcknowledge(row.EventId)}
                  >
                    {row.Acknowledged ? 'Acknowledged' : ackingEventId === row.EventId ? 'Saving…' : 'Acknowledge'}
                  </button>
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
                  {routeScores.map((row) => (
                    <Cell
                      key={row.name}
                      fill={row.spoilage >= 70 ? '#c9472b' : row.spoilage >= 40 ? '#e0a458' : '#2c7a5a'}
                    />
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
            <input value={question} onChange={(event) => setQuestion(event.target.value)} />
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
              <p>Ask about risk, anomalies, routes, carriers, packaging, vendors, or model performance.</p>
            )}
          </div>
        </div>
      </section>

      <section className="detailSection">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Batch drill-down</p>
            <h2>{selectedBatchId || 'Select a batch'}</h2>
          </div>
          {selectedSummary && (
            <div className="detailHeaderMeta">
              <span>{selectedSummary.Origin} → {selectedSummary.Destination}</span>
              <RiskBadge risk={selectedSummary.RiskLevel || 'LOW'} />
            </div>
          )}
        </div>
        <PanelBody state={batchDetail}>
          {selectedSummary ? (
            <>
              <div className="detailMetrics">
                <MetricCard label="Probability" value={formatPercent(selectedSummary.SpoilageProbability)} />
                <MetricCard label="Hours left" value={formatHours(selectedSummary.EstimatedHoursLeft)} />
                <MetricCard label="Cold-chain breaks" value={selectedSummary.ColdChainBreaks ?? '0'} />
                <MetricCard label="Alert channels" value={selectedSummary.AlertChannel || 'None'} />
              </div>

              <div className="detailGrid">
                <div className="panel chartPanel">
                  <div className="sectionHeader compact">
                    <div>
                      <p className="eyebrow">Sensor history</p>
                      <h2>Temperature and humidity</h2>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={detailSensorTrend} margin={{ left: -18, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid stroke="#d9e2dc" vertical={false} />
                      <XAxis dataKey="time" tickLine={false} axisLine={false} />
                      <YAxis tickLine={false} axisLine={false} />
                      <Tooltip />
                      <Line type="monotone" dataKey="temperature" stroke="#2c7a5a" strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="humidity" stroke="#285f9f" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="panel chartPanel">
                  <div className="sectionHeader compact">
                    <div>
                      <p className="eyebrow">Prediction history</p>
                      <h2>Spoilage probability over time</h2>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={predictionTrend} margin={{ left: -18, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid stroke="#d9e2dc" vertical={false} />
                      <XAxis dataKey="time" tickLine={false} axisLine={false} />
                      <YAxis tickLine={false} axisLine={false} domain={[0, 100]} />
                      <Tooltip />
                      <Line type="monotone" dataKey="probability" stroke="#c9472b" strokeWidth={3} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="detailLists">
                <div className="panel">
                  <div className="sectionHeader compact">
                    <div>
                      <p className="eyebrow">Alert log</p>
                      <h2>Delivery history</h2>
                    </div>
                  </div>
                  <div className="logList">
                    {(batchDetail.data?.alertLog ?? []).map((entry) => (
                      <div className="logRow" key={entry.LogId}>
                        <div>
                          <strong>{entry.Channel}</strong>
                          <span>{formatTimestamp(entry.AttemptedAt)} | {entry.Provider || 'system'} | {entry.Target || 'n/a'}</span>
                        </div>
                        <span className={`statusPill ${String(entry.DeliveryStatus).toLowerCase()}`}>{entry.DeliveryStatus}</span>
                      </div>
                    ))}
                    {(batchDetail.data?.alertLog ?? []).length === 0 && (
                      <p className="empty">No alert deliveries recorded for this batch.</p>
                    )}
                  </div>
                </div>

                <div className="panel">
                  <div className="sectionHeader compact">
                    <div>
                      <p className="eyebrow">Batch anomalies</p>
                      <h2>Latest events</h2>
                    </div>
                  </div>
                  <div className="logList">
                    {(batchDetail.data?.anomalies ?? []).map((entry) => (
                      <div className="logRow" key={entry.EventId}>
                        <div>
                          <strong>{entry.SensorType} | {entry.AnomalyType}</strong>
                          <span>{formatTimestamp(entry.DetectedAt)} | value {Number(entry.ReadingValue ?? 0).toFixed(2)}</span>
                        </div>
                        <button
                          type="button"
                          className={`ghostButton ${entry.Acknowledged ? 'done' : ''}`}
                          disabled={Boolean(entry.Acknowledged) || ackingEventId === entry.EventId}
                          onClick={() => onAcknowledge(entry.EventId)}
                        >
                          {entry.Acknowledged ? 'Acknowledged' : ackingEventId === entry.EventId ? 'Saving…' : 'Acknowledge'}
                        </button>
                      </div>
                    ))}
                    {(batchDetail.data?.anomalies ?? []).length === 0 && (
                      <p className="empty">No anomalies recorded for this batch.</p>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <p className="empty">Select a batch from the priority queue to inspect its telemetry, prediction history, and alert log.</p>
          )}
        </PanelBody>
      </section>

      <section className="performanceSection">
        <div className="sectionHeader">
          <div>
            <p className="eyebrow">Model performance</p>
            <h2>Prediction trust vs observed spoilage</h2>
          </div>
        </div>
        <PanelBody state={performance}>
          <div className="detailMetrics">
            <MetricCard label="Evaluated batches" value={performanceOverview.EvaluatedBatchCount ?? '0'} />
            <MetricCard label="Accuracy" value={formatPercent(performanceOverview.Accuracy)} />
            <MetricCard label="Mean absolute error" value={formatDecimal(performanceOverview.MeanAbsoluteError)} />
            <MetricCard
              label="Avg predicted risk"
              value={formatPercent(performanceOverview.AverageSpoilageProbability)}
            />
          </div>

          <div className="performanceGrid">
            <div className="panel">
              <div className="sectionHeader compact">
                <div>
                  <p className="eyebrow">Confusion matrix</p>
                  <h2>Latest evaluated batches</h2>
                </div>
              </div>
              <div className="matrixGrid">
                <MetricCard label="True positive" value={performanceOverview.TruePositiveCount ?? '0'} />
                <MetricCard label="False positive" value={performanceOverview.FalsePositiveCount ?? '0'} />
                <MetricCard label="True negative" value={performanceOverview.TrueNegativeCount ?? '0'} />
                <MetricCard label="False negative" value={performanceOverview.FalseNegativeCount ?? '0'} />
              </div>
            </div>

            <div className="panel">
              <div className="sectionHeader compact">
                <div>
                  <p className="eyebrow">By product</p>
                  <h2>Accuracy and error</h2>
                </div>
              </div>
              <div className="tableList">
                {(performance.data?.productBreakdown ?? []).map((row) => (
                  <div className="tableRow" key={row.ProductType}>
                    <strong>{row.ProductType}</strong>
                    <span>{row.EvaluatedBatchCount} batches</span>
                    <span>{formatPercent(row.Accuracy)} accuracy</span>
                    <span>{formatDecimal(row.MeanAbsoluteError)} MAE</span>
                  </div>
                ))}
                {(performance.data?.productBreakdown ?? []).length === 0 && (
                  <p className="empty">No evaluated batches yet for this customer.</p>
                )}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="sectionHeader compact">
              <div>
                <p className="eyebrow">Recent evaluations</p>
                <h2>Truth vs latest prediction</h2>
              </div>
            </div>
            <div className="tableList">
              {(performance.data?.recentBatches ?? []).slice(0, 8).map((row) => (
                <div className="tableRow" key={row.BatchId}>
                  <strong>{row.BatchId}</strong>
                  <span>{row.ProductType}</span>
                  <span>{formatPercent(row.SpoilageProbability)} predicted</span>
                  <span>{row.WasSpoiled ? 'Spoiled' : 'Fresh'}</span>
                  <span className={`statusPill ${String(row.OutcomeLabel || '').toLowerCase()}`}>{row.OutcomeLabel}</span>
                </div>
              ))}
              {(performance.data?.recentBatches ?? []).length === 0 && (
                <p className="empty">Model performance appears once batches have both predictions and observed outcomes.</p>
              )}
            </div>
          </div>
        </PanelBody>
      </section>
    </main>
  );
}

function PanelBody({ state, children }) {
  if (state.status === 'loading' && !state.data) {
    return <p className="empty">Loading…</p>;
  }
  if (state.status === 'error' && !state.data) {
    return <p className="errorText">Failed to load: {state.error}</p>;
  }
  return (
    <>
      {state.status === 'error' && state.data && <p className="errorText">Refresh failed: {state.error}</p>}
      {children}
    </>
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

function MetricCard({ label, value }) {
  return (
    <div className="miniMetric">
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

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Math.round(Number(value) * 100)}%`;
}

function formatHours(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}h`;
}

function formatDecimal(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(2);
}

function formatClock(value) {
  if (!value) return '—';
  return String(value).slice(11, 16) || '—';
}

function formatTimestamp(value) {
  if (!value) return '—';
  return String(value).replace('T', ' ').slice(0, 16);
}

createRoot(document.getElementById('root')).render(<App />);
