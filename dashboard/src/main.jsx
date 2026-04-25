import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './styles.css';

const SESSION_STORAGE_KEY = 'perishguard.sessionToken';
const RISK_QUERY = 'Show me the highest risk batches';
const ANOMALY_QUERY = 'Show me the latest anomalies';
const TELEMETRY_QUERY = 'Show me the latest sensor readings';
const DEFAULT_SETTINGS = {
  riskThresholds: { CRITICAL: 0.8, HIGH: 0.6, MEDIUM: 0.35 },
  anomalyConfig: {
    humidityWarning: 85,
    humidityCritical: 90,
    gasCriticalMultiplier: 1.5,
    temperatureRateDelta: 2.0,
    temperatureCriticalDelta: 4.0,
  },
  alertConfig: {
    cooldownMinutes: 30,
    logisticsHoursLeftTrigger: 12,
    emailEnabled: true,
    slackEnabled: true,
  },
  routeConfig: {},
};

async function fetchJson(url, options = {}) {
  const { token, headers, ...rest } = options;
  const response = await fetch(url, {
    ...rest,
    headers: {
      ...(headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
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

function useApiResource(loader, { enabled = true } = {}) {
  const [state, setState] = useState({ status: enabled ? 'loading' : 'idle', data: null, error: null });

  const refresh = useCallback(async () => {
    if (!enabled) {
      setState({ status: 'idle', data: null, error: null });
      return;
    }
    setState((current) => ({
      status: current.data ? 'refreshing' : 'loading',
      data: current.data,
      error: null,
    }));
    try {
      const data = await loader();
      setState({ status: 'ready', data, error: null });
    } catch (error) {
      setState((current) => ({
        status: 'error',
        data: current.data,
        error: error.message,
      }));
    }
  }, [enabled, loader]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}

function App() {
  const [token, setToken] = useState(() => window.localStorage.getItem(SESSION_STORAGE_KEY) || '');
  const [loginEmail, setLoginEmail] = useState('admin@perishguard.local');
  const [loginPassword, setLoginPassword] = useState('perishguard-demo');
  const [loginState, setLoginState] = useState({ status: 'idle', error: null });
  const [question, setQuestion] = useState('Which routes are showing the highest spoilage risk right now?');
  const [chat, setChat] = useState({ status: 'idle', data: null, error: null });
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [ackingEventId, setAckingEventId] = useState(null);
  const [settingsForm, setSettingsForm] = useState(DEFAULT_SETTINGS);
  const [settingsSaveState, setSettingsSaveState] = useState({ status: 'idle', error: null });
  const [trainingState, setTrainingState] = useState({ status: 'idle', error: null, result: null });

  const session = useApiResource(
    useCallback(() => fetchJson('/api/session', { token }), [token]),
    { enabled: Boolean(token) },
  );

  const activeSession = session.data?.session ?? null;
  const customerId = activeSession?.activeCustomerId ?? '';
  const isAuthed = Boolean(token && activeSession);

  const risk = useApiResource(
    useCallback(
      () => fetchJson('/api/nl-query', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: RISK_QUERY }),
      }),
      [token],
    ),
    { enabled: isAuthed },
  );

  const anomalies = useApiResource(
    useCallback(
      () => fetchJson('/api/nl-query', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: ANOMALY_QUERY }),
      }),
      [token],
    ),
    { enabled: isAuthed },
  );

  const telemetry = useApiResource(
    useCallback(
      () => fetchJson('/api/nl-query', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: TELEMETRY_QUERY }),
      }),
      [token],
    ),
    { enabled: isAuthed },
  );

  const batchDetail = useApiResource(
    useCallback(
      () => fetchJson(`/api/batches/${encodeURIComponent(selectedBatchId)}`, { token }),
      [selectedBatchId, token],
    ),
    { enabled: isAuthed && Boolean(selectedBatchId) },
  );

  const performance = useApiResource(
    useCallback(() => fetchJson('/api/model-performance', { token }), [token]),
    { enabled: isAuthed },
  );

  const routeOverview = useApiResource(
    useCallback(() => fetchJson('/api/routes/overview', { token }), [token]),
    { enabled: isAuthed },
  );

  const customerSettings = useApiResource(
    useCallback(() => fetchJson('/api/customer-settings', { token }), [token]),
    { enabled: isAuthed },
  );

  const trainingRuns = useApiResource(
    useCallback(() => fetchJson('/api/model-training', { token }), [token]),
    { enabled: isAuthed },
  );

  useEffect(() => {
    if (!token || session.status !== 'error') {
      return;
    }
    if ((session.error || '').toLowerCase().includes('session')) {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      setToken('');
    }
  }, [session.error, session.status, token]);

  useEffect(() => {
    if (!isAuthed) {
      setSelectedBatchId('');
      return;
    }
    const rows = risk.data?.rows ?? [];
    if (!rows.length) {
      setSelectedBatchId('');
      return;
    }
    if (!selectedBatchId || !rows.some((row) => row.BatchId === selectedBatchId)) {
      setSelectedBatchId(rows[0].BatchId);
    }
  }, [isAuthed, risk.data, selectedBatchId]);

  useEffect(() => {
    if (customerSettings.data) {
      setSettingsForm({
        riskThresholds: { ...DEFAULT_SETTINGS.riskThresholds, ...(customerSettings.data.riskThresholds || {}) },
        anomalyConfig: { ...DEFAULT_SETTINGS.anomalyConfig, ...(customerSettings.data.anomalyConfig || {}) },
        alertConfig: { ...DEFAULT_SETTINGS.alertConfig, ...(customerSettings.data.alertConfig || {}) },
        routeConfig: customerSettings.data.routeConfig || {},
      });
    }
  }, [customerSettings.data]);

  const totals = useMemo(() => {
    const rows = risk.data?.rows ?? [];
    const critical = rows.filter((row) => row.RiskLevel === 'CRITICAL').length;
    const hours = rows.map((row) => Number(row.EstimatedHoursLeft) || 0);
    const openAlerts = (anomalies.data?.rows ?? []).filter((row) => !row.Acknowledged && row.Severity !== 'INFO').length;
    return {
      active: rows.length,
      critical,
      avgHours: hours.length ? (hours.reduce((sum, value) => sum + value, 0) / hours.length).toFixed(1) : '—',
      alerts: openAlerts,
    };
  }, [anomalies.data, risk.data]);

  const telemetryTrend = useMemo(
    () => ((telemetry.data?.rows ?? []).slice().reverse()).map((row) => ({
      time: formatClock(row.ReadingAt),
      temperature: Number(row.Temperature) || 0,
    })),
    [telemetry.data],
  );

  const detailSensorTrend = useMemo(
    () => (batchDetail.data?.sensorHistory ?? []).map((row) => ({
      time: formatClock(row.ReadingAt),
      temperature: Number(row.Temperature) || 0,
      humidity: Number(row.Humidity) || 0,
    })),
    [batchDetail.data],
  );

  const predictionTrend = useMemo(
    () => (batchDetail.data?.predictionHistory ?? []).map((row) => ({
      time: formatClock(row.PredictedAt),
      probability: Math.round((Number(row.SpoilageProbability) || 0) * 100),
    })),
    [batchDetail.data],
  );

  const selectedSummary = batchDetail.data?.summary ?? null;
  const performanceOverview = performance.data?.overview ?? {};
  const routeRows = routeOverview.data?.routes ?? [];
  const runRows = trainingRuns.data?.runs ?? [];

  async function handleLogin(event) {
    event.preventDefault();
    setLoginState({ status: 'loading', error: null });
    try {
      const result = await fetchJson('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      window.localStorage.setItem(SESSION_STORAGE_KEY, result.token);
      setToken(result.token);
      setLoginState({ status: 'ready', error: null });
    } catch (error) {
      setLoginState({ status: 'error', error: error.message });
    }
  }

  async function handleLogout() {
    try {
      if (token) {
        await fetchJson('/api/logout', { method: 'POST', token });
      }
    } catch {
      // Ignore logout failures and clear the local session anyway.
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    setToken('');
    setChat({ status: 'idle', data: null, error: null });
  }

  async function handleCustomerSwitch(nextCustomerId) {
    if (!nextCustomerId || nextCustomerId === customerId) {
      return;
    }
    await fetchJson('/api/session/customer', {
      method: 'POST',
      token,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customerId: nextCustomerId }),
    });
    setSelectedBatchId('');
    await Promise.all([
      session.refresh(),
      risk.refresh(),
      anomalies.refresh(),
      telemetry.refresh(),
      performance.refresh(),
      routeOverview.refresh(),
      customerSettings.refresh(),
      trainingRuns.refresh(),
    ]);
  }

  async function askQuestion(event) {
    event.preventDefault();
    setChat({ status: 'loading', data: null, error: null });
    try {
      const data = await fetchJson('/api/nl-query', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      setChat({ status: 'ready', data, error: null });
    } catch (error) {
      setChat({ status: 'error', data: null, error: error.message });
    }
  }

  async function onAcknowledge(eventId) {
    setAckingEventId(eventId);
    try {
      await fetchJson(`/api/anomalies/${eventId}/ack`, {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      await Promise.all([anomalies.refresh(), batchDetail.refresh()]);
    } catch (error) {
      window.alert(error.message);
    } finally {
      setAckingEventId(null);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    setSettingsSaveState({ status: 'saving', error: null });
    try {
      await fetchJson('/api/customer-settings', {
        method: 'PUT',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm),
      });
      await Promise.all([customerSettings.refresh(), risk.refresh()]);
      setSettingsSaveState({ status: 'saved', error: null });
    } catch (error) {
      setSettingsSaveState({ status: 'error', error: error.message });
    }
  }

  async function triggerRetraining(scope) {
    setTrainingState({ status: 'running', error: null, result: null });
    try {
      const result = await fetchJson('/api/model-training', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope }),
      });
      await Promise.all([trainingRuns.refresh(), performance.refresh(), risk.refresh()]);
      setTrainingState({ status: 'ready', error: null, result });
    } catch (error) {
      setTrainingState({ status: 'error', error: error.message, result: null });
    }
  }

  function refreshAll() {
    risk.refresh();
    anomalies.refresh();
    telemetry.refresh();
    performance.refresh();
    routeOverview.refresh();
    customerSettings.refresh();
    trainingRuns.refresh();
    if (selectedBatchId) {
      batchDetail.refresh();
    }
  }

  if (!token) {
    return (
      <main className="loginPage">
        <section className="loginCard">
          <p className="eyebrow">PerishGuard Pulse</p>
          <h1>Perishable operations, live</h1>
          <p className="loginCopy">
            Sign in to load your permitted customers, scoped dashboard queries, route-risk map, settings, and model retraining tools.
          </p>
          <form className="loginForm" onSubmit={handleLogin}>
            <label>
              <span>Email</span>
              <input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                value={loginPassword}
                onChange={(event) => setLoginPassword(event.target.value)}
              />
            </label>
            <button type="submit" className="primaryButton" disabled={loginState.status === 'loading'}>
              {loginState.status === 'loading' ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          {loginState.error && <p className="errorText">{loginState.error}</p>}
          <div className="loginHint">
            <strong>Demo users</strong>
            <span>`admin@perishguard.local` for all customers, or `ops+c010@perishguard.local` for a single tenant.</span>
            <span>Password: `perishguard-demo`</span>
          </div>
        </section>
      </main>
    );
  }

  if (session.status === 'loading' && !activeSession) {
    return (
      <main className="loginPage">
        <section className="loginCard">
          <h2>Loading session…</h2>
        </section>
      </main>
    );
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">PerishGuard Pulse</p>
          <h1>Perishable operations, live</h1>
          <p className="subtitle">
            Signed in as {activeSession?.displayName} · Active customer {customerId}
          </p>
        </div>
        <div className="topbarActions">
          <label className="customerSelect">
            <span>Customer</span>
            <select value={customerId} onChange={(event) => handleCustomerSwitch(event.target.value)}>
              {(activeSession?.customers ?? []).map((customer) => (
                <option key={customer.customerId} value={customer.customerId}>
                  {customer.customerId} · {customer.customerName}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ghostButton" onClick={refreshAll}>
            Refresh
          </button>
          <button type="button" className="ghostButton" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      <section className="metrics">
        <Metric icon="batch" label="Active batches" value={totals.active} />
        <Metric icon="warning" label="Critical risk" value={totals.critical} tone="danger" />
        <Metric icon="clock" label="Avg hours left" value={totals.avgHours} />
        <Metric icon="pulse" label="Open anomalies" value={totals.alerts} tone="warn" />
      </section>

      <section className="workspace">
        <section className="panel">
          <SectionHeader eyebrow="Spoilage risk" title="Batch priority queue" action={<button type="button" className="iconButton" onClick={refreshAll}><Icon name="refresh" /></button>} />
          <PanelBody state={risk}>
            <div className="riskList">
              {(risk.data?.rows ?? []).map((row) => (
                <button
                  key={row.BatchId}
                  type="button"
                  className={`riskRow ${selectedBatchId === row.BatchId ? 'active' : ''}`}
                  onClick={() => setSelectedBatchId(row.BatchId)}
                >
                  <div className="riskIdentity">
                    <strong>{row.BatchId}</strong>
                    <span>{row.ProductType} · {row.Origin} → {row.Destination}</span>
                  </div>
                  <RiskBadge risk={row.RiskLevel || 'LOW'} />
                  <div className="probability">
                    <span>{formatPercent(row.SpoilageProbability)}</span>
                    <div><i style={{ width: `${(Number(row.SpoilageProbability) || 0) * 100}%` }} /></div>
                  </div>
                  <strong className="hours">{formatHours(row.EstimatedHoursLeft)}</strong>
                </button>
              ))}
            </div>
          </PanelBody>
        </section>

        <section className="panel">
          <SectionHeader eyebrow="Telemetry" title="Recent temperature" />
          <PanelBody state={telemetry}>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={telemetryTrend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid stroke="#d9e2dc" vertical={false} />
                <XAxis dataKey="time" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Line type="monotone" dataKey="temperature" stroke="#2c7a5a" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </PanelBody>
        </section>
      </section>

      <section className="threeUp">
        <section className="panel">
          <SectionHeader eyebrow="Anomalies" title="Live flags" />
          <PanelBody state={anomalies}>
            <div className="stackList">
              {(anomalies.data?.rows ?? []).slice(0, 8).map((row) => (
                <div className="stackRow" key={row.EventId || `${row.BatchId}-${row.DetectedAt}`}>
                  <div>
                    <strong>{row.SensorType} · {row.BatchId}</strong>
                    <span>{row.AnomalyType} · {Number(row.ReadingValue ?? 0).toFixed(2)} · {formatTimestamp(row.DetectedAt)}</span>
                  </div>
                  <div className="rowActions">
                    <RiskBadge risk={row.Severity || 'INFO'} />
                    <button
                      type="button"
                      className={`ghostButton ${row.Acknowledged ? 'done' : ''}`}
                      disabled={Boolean(row.Acknowledged) || ackingEventId === row.EventId}
                      onClick={() => onAcknowledge(row.EventId)}
                    >
                      {row.Acknowledged ? 'Acknowledged' : ackingEventId === row.EventId ? 'Saving…' : 'Acknowledge'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </PanelBody>
        </section>

        <section className="panel">
          <SectionHeader eyebrow="Routes" title="Geospatial risk view" />
          <PanelBody state={routeOverview}>
            <RouteMap routes={routeRows} />
          </PanelBody>
        </section>

        <section className="panel">
          <SectionHeader eyebrow="Ask data" title="Shipment chat" />
          <form className="askForm" onSubmit={askQuestion}>
            <input value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button type="submit" className="iconButton" disabled={chat.status === 'loading'}>
              <Icon name="send" />
            </button>
          </form>
          <div className="answer">
            {chat.status === 'loading' && <p>Thinking…</p>}
            {chat.status === 'error' && <p className="errorText">{chat.error}</p>}
            {chat.status === 'ready' && chat.data && (
              <>
                <p>{chat.data.summary}</p>
                <span>{chat.data.chart} · {(chat.data.rows || []).length} rows</span>
              </>
            )}
            {chat.status === 'idle' && (
              <p>Ask about routes, spoilage risk, anomalies, vendors, carriers, or model performance.</p>
            )}
          </div>
        </section>
      </section>

      <section className="panel detailPanel">
        <SectionHeader
          eyebrow="Batch drill-down"
          title={selectedBatchId || 'Select a batch'}
          subtitle={selectedSummary ? `${selectedSummary.Origin} → ${selectedSummary.Destination}` : 'Choose a batch from the queue to inspect live history.'}
        />
        <PanelBody state={batchDetail}>
          {selectedSummary && (
            <>
              <div className="metricGrid compactGrid">
                <MetricCard label="Probability" value={formatPercent(selectedSummary.SpoilageProbability)} />
                <MetricCard label="Hours left" value={formatHours(selectedSummary.EstimatedHoursLeft)} />
                <MetricCard label="Cold-chain breaks" value={selectedSummary.ColdChainBreaks ?? 0} />
                <MetricCard label="Alert channel" value={selectedSummary.AlertChannel || 'None'} />
              </div>
              <div className="detailGrid">
                <section className="subPanel">
                  <SectionHeader eyebrow="Sensor history" title="Temperature and humidity" />
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={detailSensorTrend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid stroke="#d9e2dc" vertical={false} />
                      <XAxis dataKey="time" tickLine={false} axisLine={false} />
                      <YAxis tickLine={false} axisLine={false} />
                      <Tooltip />
                      <Line type="monotone" dataKey="temperature" stroke="#2c7a5a" strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="humidity" stroke="#285f9f" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </section>
                <section className="subPanel">
                  <SectionHeader eyebrow="Prediction history" title="Spoilage probability" />
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={predictionTrend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid stroke="#d9e2dc" vertical={false} />
                      <XAxis dataKey="time" tickLine={false} axisLine={false} />
                      <YAxis tickLine={false} axisLine={false} domain={[0, 100]} />
                      <Tooltip />
                      <Line type="monotone" dataKey="probability" stroke="#c9472b" strokeWidth={3} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </section>
              </div>
              <div className="detailGrid">
                <StackList
                  eyebrow="Alert log"
                  title="Delivery history"
                  rows={(batchDetail.data?.alertLog ?? []).map((entry) => ({
                    key: entry.LogId,
                    title: entry.Channel,
                    subtitle: `${formatTimestamp(entry.AttemptedAt)} · ${entry.Provider || 'system'} · ${entry.Target || 'n/a'}`,
                    status: entry.DeliveryStatus,
                  }))}
                />
                <StackList
                  eyebrow="Batch anomalies"
                  title="Latest events"
                  rows={(batchDetail.data?.anomalies ?? []).map((entry) => ({
                    key: entry.EventId,
                    title: `${entry.SensorType} · ${entry.AnomalyType}`,
                    subtitle: `${formatTimestamp(entry.DetectedAt)} · value ${Number(entry.ReadingValue ?? 0).toFixed(2)}`,
                    action: (
                      <button
                        type="button"
                        className={`ghostButton ${entry.Acknowledged ? 'done' : ''}`}
                        disabled={Boolean(entry.Acknowledged) || ackingEventId === entry.EventId}
                        onClick={() => onAcknowledge(entry.EventId)}
                      >
                        {entry.Acknowledged ? 'Acknowledged' : ackingEventId === entry.EventId ? 'Saving…' : 'Acknowledge'}
                      </button>
                    ),
                  }))}
                />
              </div>
            </>
          )}
        </PanelBody>
      </section>

      <section className="twoUp">
        <section className="panel">
          <SectionHeader eyebrow="Thresholds and alerts" title="Runtime customer config" subtitle="Changes apply without rebuilding the dashboard or Functions image." />
          <PanelBody state={customerSettings}>
            <form className="settingsForm" onSubmit={saveSettings}>
              <div className="settingsGrid">
                <NumberField
                  label="Critical risk"
                  value={settingsForm.riskThresholds.CRITICAL}
                  step="0.01"
                  onChange={(value) => updateSection(setSettingsForm, 'riskThresholds', 'CRITICAL', value)}
                />
                <NumberField
                  label="High risk"
                  value={settingsForm.riskThresholds.HIGH}
                  step="0.01"
                  onChange={(value) => updateSection(setSettingsForm, 'riskThresholds', 'HIGH', value)}
                />
                <NumberField
                  label="Medium risk"
                  value={settingsForm.riskThresholds.MEDIUM}
                  step="0.01"
                  onChange={(value) => updateSection(setSettingsForm, 'riskThresholds', 'MEDIUM', value)}
                />
                <NumberField
                  label="Cooldown minutes"
                  value={settingsForm.alertConfig.cooldownMinutes}
                  step="1"
                  onChange={(value) => updateSection(setSettingsForm, 'alertConfig', 'cooldownMinutes', value)}
                />
                <NumberField
                  label="Humidity warning"
                  value={settingsForm.anomalyConfig.humidityWarning}
                  step="1"
                  onChange={(value) => updateSection(setSettingsForm, 'anomalyConfig', 'humidityWarning', value)}
                />
                <NumberField
                  label="Humidity critical"
                  value={settingsForm.anomalyConfig.humidityCritical}
                  step="1"
                  onChange={(value) => updateSection(setSettingsForm, 'anomalyConfig', 'humidityCritical', value)}
                />
                <NumberField
                  label="Temp rate delta"
                  value={settingsForm.anomalyConfig.temperatureRateDelta}
                  step="0.1"
                  onChange={(value) => updateSection(setSettingsForm, 'anomalyConfig', 'temperatureRateDelta', value)}
                />
                <NumberField
                  label="Logistics hours trigger"
                  value={settingsForm.alertConfig.logisticsHoursLeftTrigger}
                  step="1"
                  onChange={(value) => updateSection(setSettingsForm, 'alertConfig', 'logisticsHoursLeftTrigger', value)}
                />
              </div>
              <div className="toggleRow">
                <ToggleField
                  label="Slack alerts enabled"
                  checked={Boolean(settingsForm.alertConfig.slackEnabled)}
                  onChange={(value) => updateSection(setSettingsForm, 'alertConfig', 'slackEnabled', value)}
                />
                <ToggleField
                  label="Email alerts enabled"
                  checked={Boolean(settingsForm.alertConfig.emailEnabled)}
                  onChange={(value) => updateSection(setSettingsForm, 'alertConfig', 'emailEnabled', value)}
                />
              </div>
              <div className="formActions">
                <button type="submit" className="primaryButton" disabled={settingsSaveState.status === 'saving'}>
                  {settingsSaveState.status === 'saving' ? 'Saving…' : 'Save settings'}
                </button>
                {settingsSaveState.status === 'saved' && <span className="successText">Saved</span>}
                {settingsSaveState.error && <span className="errorText">{settingsSaveState.error}</span>}
              </div>
            </form>
          </PanelBody>
        </section>

        <section className="panel">
          <SectionHeader eyebrow="MLOps retraining" title="Training loop" subtitle="Retrain from labeled PostgreSQL data and hot-reload the ONNX bundle through the shared model volume." />
          <div className="formActions">
            <button
              type="button"
              className="primaryButton"
              disabled={trainingState.status === 'running'}
              onClick={() => triggerRetraining('global')}
            >
              {trainingState.status === 'running' ? 'Retraining…' : 'Retrain global model'}
            </button>
            <button
              type="button"
              className="ghostButton"
              disabled={trainingState.status === 'running'}
              onClick={() => triggerRetraining('customer')}
            >
              Retrain active customer model
            </button>
          </div>
          {trainingState.error && <p className="errorText">{trainingState.error}</p>}
          {trainingState.result && (
            <div className="trainingSummary">
              <strong>{trainingState.result.modelVersion}</strong>
              <span>
                ROC-AUC {trainingState.result.metrics?.cv_metrics?.classifier_roc_auc ?? '—'} · MAE {trainingState.result.metrics?.cv_metrics?.regressor_mae_hours ?? '—'}h
              </span>
            </div>
          )}
          <StackList
            eyebrow="Recent runs"
            title="Training history"
            rows={runRows.map((run) => ({
              key: run.RunId,
              title: `${run.ModelVersion || 'Pending version'} · ${run.Status}`,
              subtitle: `${formatTimestamp(run.StartedAt)}${run.CompletedAt ? ` → ${formatTimestamp(run.CompletedAt)}` : ''}`,
              status: run.Status,
            }))}
          />
        </section>
      </section>

      <section className="panel">
        <SectionHeader eyebrow="Model performance" title="Prediction vs truth" />
        <PanelBody state={performance}>
          <div className="metricGrid compactGrid">
            <MetricCard label="Accuracy" value={formatPercent(performanceOverview.Accuracy)} />
            <MetricCard label="Mean absolute error" value={formatHours(performanceOverview.MeanAbsoluteError)} />
            <MetricCard label="Evaluated batches" value={performanceOverview.EvaluatedBatchCount ?? 0} />
            <MetricCard label="Avg spoilage probability" value={formatPercent(performanceOverview.AverageSpoilageProbability)} />
          </div>
          <div className="detailGrid">
            <SimpleTable
              eyebrow="Product breakdown"
              title="Performance by product"
              columns={['Product', 'Accuracy', 'MAE', 'Batches']}
              rows={(performance.data?.productBreakdown ?? []).map((row) => [
                row.ProductType,
                formatPercent(row.Accuracy),
                formatHours(row.MeanAbsoluteError),
                row.EvaluatedBatchCount,
              ])}
            />
            <SimpleTable
              eyebrow="Recent labeled batches"
              title="Latest outcomes"
              columns={['Batch', 'Outcome', 'Risk', 'Probability']}
              rows={(performance.data?.recentBatches ?? []).slice(0, 8).map((row) => [
                row.BatchId,
                row.OutcomeLabel,
                row.RiskLevel,
                formatPercent(row.SpoilageProbability),
              ])}
            />
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
    return <p className="errorText">{state.error}</p>;
  }
  return (
    <>
      {children}
      {state.status === 'error' && state.data && <p className="errorText">{state.error}</p>}
    </>
  );
}

function SectionHeader({ eyebrow, title, subtitle, action = null }) {
  return (
    <div className="sectionHeader">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {subtitle && <p className="sectionSubtitle">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function Metric({ icon, label, value, tone = '' }) {
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
  const normalized = String(risk || 'LOW').toLowerCase();
  return <span className={`riskBadge ${normalized}`}>{String(risk || 'LOW')}</span>;
}

function StackList({ eyebrow, title, rows }) {
  return (
    <section className="subPanel">
      <SectionHeader eyebrow={eyebrow} title={title} />
      <div className="stackList">
        {rows.length === 0 && <p className="empty">No records available.</p>}
        {rows.map((row) => (
          <div className="stackRow" key={row.key}>
            <div>
              <strong>{row.title}</strong>
              <span>{row.subtitle}</span>
            </div>
            {row.status && <span className={`statusPill ${String(row.status).toLowerCase().replace(/\s+/g, '_')}`}>{row.status}</span>}
            {row.action}
          </div>
        ))}
      </div>
    </section>
  );
}

function SimpleTable({ eyebrow, title, columns, rows }) {
  return (
    <section className="subPanel">
      <SectionHeader eyebrow={eyebrow} title={title} />
      <div className="simpleTable">
        <div className="tableHeader">
          {columns.map((column) => <strong key={column}>{column}</strong>)}
        </div>
        {rows.length === 0 && <p className="empty">No rows available.</p>}
        {rows.map((row, index) => (
          <div className="tableRow" key={`${index}-${row[0]}`}>
            {row.map((cell, cellIndex) => <span key={`${index}-${cellIndex}`}>{cell}</span>)}
          </div>
        ))}
      </div>
    </section>
  );
}

function NumberField({ label, value, step, onChange }) {
  return (
    <label className="settingsField">
      <span>{label}</span>
      <input type="number" step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function ToggleField({ label, checked, onChange }) {
  return (
    <label className="toggleField">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function RouteMap({ routes }) {
  if (!routes.length) {
    return <p className="empty">No route data available for this customer.</p>;
  }

  const points = routes.flatMap((route) => ([
    [Number(route.OriginLongitude), Number(route.OriginLatitude)],
    [Number(route.DestinationLongitude), Number(route.DestinationLatitude)],
  ])).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));

  if (!points.length) {
    return <p className="empty">Route coordinates are missing for this customer.</p>;
  }

  const minX = Math.min(...points.map(([x]) => x));
  const maxX = Math.max(...points.map(([x]) => x));
  const minY = Math.min(...points.map(([, y]) => y));
  const maxY = Math.max(...points.map(([, y]) => y));
  const width = 620;
  const height = 280;
  const padding = 36;

  const project = (longitude, latitude) => ({
    x: padding + ((longitude - minX) / Math.max(maxX - minX, 1)) * (width - padding * 2),
    y: height - padding - ((latitude - minY) / Math.max(maxY - minY, 1)) * (height - padding * 2),
  });

  return (
    <div className="routeMapWrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="routeMapSvg" aria-label="Route risk map">
        <rect x="0" y="0" width={width} height={height} rx="20" fill="#f4f7f2" />
        {routes.map((route) => {
          const start = project(Number(route.OriginLongitude), Number(route.OriginLatitude));
          const end = project(Number(route.DestinationLongitude), Number(route.DestinationLatitude));
          const probability = Number(route.AverageSpoilageProbability) || 0;
          const color = probability >= 0.7 ? '#c9472b' : probability >= 0.45 ? '#d49635' : '#2c7a5a';
          const strokeWidth = 2 + Math.min(Number(route.BatchCount) || 0, 8);
          return (
            <g key={`${route.Origin}-${route.Destination}`}>
              <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke={color} strokeWidth={strokeWidth} strokeOpacity="0.72" />
              <circle cx={start.x} cy={start.y} r="4.5" fill="#17221d" />
              <circle cx={end.x} cy={end.y} r="4.5" fill="#17221d" />
              <text x={start.x + 6} y={start.y - 8} fontSize="11" fill="#17221d">{route.Origin}</text>
              <text x={end.x + 6} y={end.y - 8} fontSize="11" fill="#17221d">{route.Destination}</text>
            </g>
          );
        })}
      </svg>
      <div className="stackList">
        {routes.slice(0, 4).map((route) => (
          <div className="stackRow" key={`${route.Origin}-${route.Destination}-summary`}>
            <div>
              <strong>{route.Origin} → {route.Destination}</strong>
              <span>{route.BatchCount} batches · {formatPercent(route.AverageSpoilageProbability)} average spoilage probability</span>
            </div>
            <RiskBadge risk={riskLabelFromProbability(route.AverageSpoilageProbability)} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Icon({ name }) {
  const paths = {
    refresh: <path d="M20 11a8 8 0 1 0 2 5m0-10v5h-5" />,
    send: <path d="m22 2-7 20-4-9-9-4Z" />,
    batch: <path d="M4 7h16M4 12h16M4 17h10" />,
    warning: <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />,
    clock: <path d="M12 6v6l4 2M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" />,
    pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name] || paths.batch}</svg>;
}

function updateSection(setter, section, key, value) {
  setter((current) => ({
    ...current,
    [section]: {
      ...current[section],
      [key]: value,
    },
  }));
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function formatHours(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${Number(value).toFixed(1)}h`;
}

function formatClock(value) {
  if (!value) {
    return '—';
  }
  return String(value).slice(11, 16) || '—';
}

function formatTimestamp(value) {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function riskLabelFromProbability(value) {
  const probability = Number(value) || 0;
  if (probability >= 0.8) {
    return 'CRITICAL';
  }
  if (probability >= 0.6) {
    return 'HIGH';
  }
  if (probability >= 0.35) {
    return 'MEDIUM';
  }
  return 'LOW';
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
