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
const THEME_STORAGE_KEY = 'perishguard.themePreference';
const RISK_QUERY = 'Show me the highest risk batches';
const ANOMALY_QUERY = 'Show me the latest anomalies';
const TELEMETRY_QUERY = 'Show me the latest sensor readings';
const QUICK_PROMPTS = [
  'Which routes are showing the highest spoilage risk right now?',
  'Show me the latest anomalies by severity',
  'Which carriers are producing the most risk this week?',
];
const WORKSPACES = [
  { id: 'overview', label: 'Overview', icon: 'grid' },
  { id: 'routes', label: 'Routes', icon: 'route' },
  { id: 'intelligence', label: 'Intelligence', icon: 'spark' },
  { id: 'controls', label: 'Controls', icon: 'sliders' },
];
const THEME_OPTIONS = [
  { value: 'system', label: 'System' },
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
];
const RISK_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
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
  const [themePreference, setThemePreference] = useState(
    () => window.localStorage.getItem(THEME_STORAGE_KEY) || 'system',
  );
  const [systemTheme, setSystemTheme] = useState(() => getSystemTheme());
  const [loginEmail, setLoginEmail] = useState('admin@perishguard.local');
  const [loginPassword, setLoginPassword] = useState('perishguard-demo');
  const [loginState, setLoginState] = useState({ status: 'idle', error: null });
  const [workspace, setWorkspace] = useState('overview');
  const [question, setQuestion] = useState(QUICK_PROMPTS[0]);
  const [chat, setChat] = useState({ status: 'idle', data: null, error: null });
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [isBatchDrawerOpen, setBatchDrawerOpen] = useState(false);
  const [riskFilter, setRiskFilter] = useState('ALL');
  const [searchText, setSearchText] = useState('');
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
  const resolvedTheme = themePreference === 'system' ? systemTheme : themePreference;
  const chartPalette = useMemo(
    () => ({
      grid: 'var(--chart-grid)',
      axis: 'var(--chart-axis)',
      temperature: 'var(--chart-temp)',
      humidity: 'var(--chart-humidity)',
      probability: 'var(--chart-prob)',
    }),
    [],
  );

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
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const updateTheme = (event) => {
      setSystemTheme(event.matches ? 'dark' : 'light');
    };
    updateTheme(mediaQuery);
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateTheme);
      return () => mediaQuery.removeEventListener('change', updateTheme);
    }
    mediaQuery.addListener(updateTheme);
    return () => mediaQuery.removeListener(updateTheme);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_STORAGE_KEY, themePreference);
  }, [themePreference]);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  useEffect(() => {
    if (!isAuthed) {
      setSelectedBatchId('');
      setBatchDrawerOpen(false);
      return;
    }
    const rows = risk.data?.rows ?? [];
    if (!rows.length) {
      setSelectedBatchId('');
      setBatchDrawerOpen(false);
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
      humidity: Number(row.Humidity) || 0,
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
      hoursLeft: Number(row.EstimatedHoursLeft) || 0,
    })),
    [batchDetail.data],
  );

  const selectedSummary = batchDetail.data?.summary ?? null;
  const performanceOverview = performance.data?.overview ?? {};
  const routeRows = routeOverview.data?.routes ?? [];
  const runRows = trainingRuns.data?.runs ?? [];

  const filteredRiskRows = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    return (risk.data?.rows ?? []).filter((row) => {
      const riskMatches = matchesRiskFilter(row.RiskLevel, riskFilter);
      if (!riskMatches) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [row.BatchId, row.ProductType, row.Origin, row.Destination, row.Carrier]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [risk.data, riskFilter, searchText]);

  const filteredRoutes = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    return routeRows.filter((route) => {
      const routeRisk = riskLabelFromProbability(route.AverageSpoilageProbability);
      if (!matchesRiskFilter(routeRisk, riskFilter)) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [route.Origin, route.Destination, route.CustomerId]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [routeRows, riskFilter, searchText]);

  const visibleAnomalies = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    return (anomalies.data?.rows ?? []).filter((row) => {
      if (!matchesRiskFilter(row.Severity, riskFilter)) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [row.BatchId, row.SensorType, row.AnomalyType]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query));
    });
  }, [anomalies.data, riskFilter, searchText]);

  const openBatchDrawer = useCallback((batchId) => {
    setSelectedBatchId(batchId);
    setBatchDrawerOpen(true);
  }, []);

  const missionFeed = useMemo(() => {
    const anomalyItems = visibleAnomalies.slice(0, 4).map((row) => ({
      key: `anomaly-${row.EventId}`,
      category: 'Anomaly',
      title: `${row.SensorType} spike on ${row.BatchId}`,
      subtitle: `${row.AnomalyType} · ${formatTimestamp(row.DetectedAt)}`,
      badge: row.Severity || 'INFO',
      onOpen: () => openBatchDrawer(row.BatchId),
    }));
    const riskItems = filteredRiskRows.slice(0, 4).map((row) => ({
      key: `risk-${row.BatchId}`,
      category: 'Risk',
      title: `${row.BatchId} · ${row.ProductType}`,
      subtitle: `${row.Origin} → ${row.Destination} · ${formatHours(row.EstimatedHoursLeft)} left`,
      badge: row.RiskLevel || 'LOW',
      onOpen: () => openBatchDrawer(row.BatchId),
    }));
    return [...anomalyItems, ...riskItems].slice(0, 6);
  }, [filteredRiskRows, openBatchDrawer, visibleAnomalies]);

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
    setBatchDrawerOpen(false);
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
    setBatchDrawerOpen(false);
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

  async function runQuestion(nextQuestion) {
    const prompt = nextQuestion || question;
    setQuestion(prompt);
    setChat({ status: 'loading', data: null, error: null });
    try {
      const data = await fetchJson('/api/nl-query', {
        method: 'POST',
        token,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: prompt }),
      });
      setChat({ status: 'ready', data, error: null });
    } catch (error) {
      setChat({ status: 'error', data: null, error: error.message });
    }
  }

  async function askQuestion(event) {
    event.preventDefault();
    await runQuestion(question);
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

  function handleThemeChange(event) {
    setThemePreference(event.target.value);
  }

  if (!token) {
    return (
      <main className="loginPage">
        <section className="loginScreen">
          <div className="loginHero">
            <div className="heroBadge">PerishGuard Pulse</div>
            <h1>Live supply chain control, built for perishables.</h1>
            <p>
              Monitor route risk, triage anomalies, tune thresholds, and retrain models from one modern control surface.
            </p>
            <div className="loginHeroStats">
              <HeroStat label="Live surfaces" value="7" />
              <HeroStat label="Primary lanes" value="12" />
              <HeroStat label="Demo customers" value="12" />
            </div>
          </div>
          <section className="loginCard">
            <p className="eyebrow">Secure access</p>
            <h2>Sign in to PerishGuard Pulse</h2>
            <label className="themeSelect">
              <span>Theme</span>
              <select value={themePreference} onChange={handleThemeChange}>
                {THEME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
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
              <button type="submit" className="primaryButton loginButton" disabled={loginState.status === 'loading'}>
                {loginState.status === 'loading' ? 'Signing in…' : 'Enter control tower'}
              </button>
            </form>
            {loginState.error && <p className="errorText">{loginState.error}</p>}
            <div className="loginHint">
              <strong>Demo users</strong>
              <span>`admin@perishguard.local` for all customers</span>
              <span>`ops+c010@perishguard.local` for a single tenant</span>
              <span>Password: `perishguard-demo`</span>
            </div>
          </section>
        </section>
      </main>
    );
  }

  if (session.status === 'loading' && !activeSession) {
    return (
      <main className="loginPage">
        <section className="loginCard centeredCard">
          <h2>Loading session…</h2>
          <p className="sectionSubtitle">Syncing your routes, alerts, and customer context.</p>
        </section>
      </main>
    );
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brandBlock">
          <div className="brandMark">P</div>
          <div>
            <p className="eyebrow">PerishGuard</p>
            <strong>Pulse</strong>
          </div>
        </div>
        <nav className="workspaceNav" aria-label="Workspace">
          {WORKSPACES.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`navButton ${workspace === item.id ? 'active' : ''}`}
              onClick={() => setWorkspace(item.id)}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebarCard">
          <p className="eyebrow">Session</p>
          <strong>{activeSession?.displayName}</strong>
          <span>{customerId} · {activeSession?.customers?.length ?? 0} accessible customers</span>
          <div className="sidebarMetrics">
            <SmallStat label="Open anomalies" value={totals.alerts} />
            <SmallStat label="Critical batches" value={totals.critical} />
          </div>
        </div>
        <div className="sidebarCard compact">
          <p className="eyebrow">Quick prompts</p>
          <div className="promptStack">
            {QUICK_PROMPTS.map((prompt) => (
              <button key={prompt} type="button" className="chipButton" onClick={() => runQuestion(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="shellMain">
        <header className="commandBar">
          <div className="commandCopy">
            <div className="heroBadge">PerishGuard Pulse</div>
            <h1>Perishable operations, live</h1>
            <p className="subtitle">
              Real-time control tower for route risk, anomalies, and model-led interventions.
            </p>
          </div>
          <div className="commandControls">
            <label className="themeSelect">
              <span>Theme</span>
              <select value={themePreference} onChange={handleThemeChange}>
                {THEME_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
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
            <label className="searchField">
              <Icon name="search" />
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Search batch, route, product, carrier…"
              />
            </label>
            <button type="button" className="ghostButton" onClick={refreshAll}>Refresh</button>
            <button type="button" className="ghostButton" onClick={handleLogout}>Sign out</button>
          </div>
        </header>

        <section className="filterDock">
          <div className="chipGroup">
            {RISK_FILTERS.map((value) => (
              <button
                key={value}
                type="button"
                className={`chipButton ${riskFilter === value ? 'active' : ''}`}
                onClick={() => setRiskFilter(value)}
              >
                {value}
              </button>
            ))}
          </div>
          <form className="commandAsk" onSubmit={askQuestion}>
            <input value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button type="submit" className="primaryButton" disabled={chat.status === 'loading'}>
              {chat.status === 'loading' ? 'Running…' : 'Ask'}
            </button>
          </form>
        </section>

        <section className="heroMetrics">
          <HeroMetric label="Tracked batches" value={totals.active} tone="neutral" />
          <HeroMetric label="Critical risk now" value={totals.critical} tone="danger" />
          <HeroMetric label="Average shelf-life left" value={`${totals.avgHours}h`} tone="neutral" />
          <HeroMetric label="Open anomaly queue" value={totals.alerts} tone="warn" />
        </section>

        {workspace === 'overview' && (
          <>
            <section className="heroGrid">
              <section className="heroPanel mapHeroPanel">
                <SectionHeader
                  eyebrow="Network view"
                  title="Route risk command surface"
                  subtitle="Map-first visibility for the most exposed lanes in your current tenant."
                />
                <PanelBody state={routeOverview}>
                  <RouteMap routes={filteredRoutes} compact={false} />
                </PanelBody>
              </section>

              <section className="heroPanel attentionPanel">
                <SectionHeader eyebrow="Mission feed" title="What needs action right now" />
                <div className="missionFeed">
                  {missionFeed.length === 0 && <p className="empty">No urgent signals match the current filters.</p>}
                  {missionFeed.map((item) => (
                    <button key={item.key} type="button" className="missionRow" onClick={item.onOpen}>
                      <div>
                        <span className="missionLabel">{item.category}</span>
                        <strong>{item.title}</strong>
                        <span>{item.subtitle}</span>
                      </div>
                      <RiskBadge risk={item.badge} />
                    </button>
                  ))}
                </div>
                <div className="answerPanel">
                  <p className="eyebrow">AI brief</p>
                  {chat.status === 'loading' && <p>Generating operational readout…</p>}
                  {chat.status === 'error' && <p className="errorText">{chat.error}</p>}
                  {chat.status === 'ready' && chat.data && (
                    <>
                      <strong>{chat.data.summary}</strong>
                      <span>{chat.data.chart} · {(chat.data.rows || []).length} rows</span>
                    </>
                  )}
                  {chat.status === 'idle' && (
                    <p className="sectionSubtitle">Run one of the quick prompts to generate a current operations brief.</p>
                  )}
                </div>
              </section>
            </section>

            <section className="contentGrid">
              <section className="contentPanel wide">
                <SectionHeader
                  eyebrow="Risk queue"
                  title="Batch priority lane"
                  subtitle="High-density exception queue with route and time-left context."
                />
                <PanelBody state={risk}>
                  <div className="queueTable">
                    {filteredRiskRows.map((row) => (
                      <button
                        key={row.BatchId}
                        type="button"
                        className={`queueRow ${selectedBatchId === row.BatchId ? 'active' : ''}`}
                        onClick={() => openBatchDrawer(row.BatchId)}
                      >
                        <div className="queuePrimary">
                          <strong>{row.BatchId}</strong>
                          <span>{row.ProductType} · {row.Origin} → {row.Destination}</span>
                        </div>
                        <div className="queueMeta">
                          <span>{row.Carrier || 'Carrier n/a'}</span>
                          <span>{formatPercent(row.SpoilageProbability)}</span>
                        </div>
                        <RiskBadge risk={row.RiskLevel || 'LOW'} />
                        <strong className="hours">{formatHours(row.EstimatedHoursLeft)}</strong>
                      </button>
                    ))}
                    {filteredRiskRows.length === 0 && <p className="empty">No batches match the current filters.</p>}
                  </div>
                </PanelBody>
              </section>

              <section className="contentPanel">
                <SectionHeader eyebrow="Live telemetry" title="Sensor stream" subtitle="Temperature and humidity trend for the active customer." />
                <PanelBody state={telemetry}>
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={telemetryTrend} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid stroke={chartPalette.grid} vertical={false} />
                      <XAxis dataKey="time" tickLine={false} axisLine={false} stroke={chartPalette.axis} />
                      <YAxis tickLine={false} axisLine={false} stroke={chartPalette.axis} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Line type="monotone" dataKey="temperature" stroke={chartPalette.temperature} strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="humidity" stroke={chartPalette.humidity} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </PanelBody>
              </section>
            </section>
          </>
        )}

        {workspace === 'routes' && (
          <section className="routesWorkspace">
            <section className="heroPanel mapHeroPanel">
              <SectionHeader eyebrow="Route network" title="Geospatial route control" subtitle="Lane-level spoilage risk, density, and critical clusters." />
              <PanelBody state={routeOverview}>
                <RouteMap routes={filteredRoutes} compact={false} />
              </PanelBody>
            </section>
            <section className="contentPanel">
              <SectionHeader eyebrow="Lane list" title="Highest-risk routes" subtitle="Filtered route list with current route health and density." />
              <PanelBody state={routeOverview}>
                <div className="stackList">
                  {filteredRoutes.map((route) => (
                    <div key={`${route.Origin}-${route.Destination}`} className="stackRow dark">
                      <div>
                        <strong>{route.Origin} → {route.Destination}</strong>
                        <span>{route.BatchCount} batches · {route.CriticalBatchCount} critical · {formatPercent(route.AverageSpoilageProbability)} avg spoilage probability</span>
                      </div>
                      <RiskBadge risk={riskLabelFromProbability(route.AverageSpoilageProbability)} />
                    </div>
                  ))}
                  {filteredRoutes.length === 0 && <p className="empty">No routes match the current filters.</p>}
                </div>
              </PanelBody>
            </section>
          </section>
        )}

        {workspace === 'intelligence' && (
          <section className="intelligenceGrid">
            <section className="contentPanel">
              <SectionHeader eyebrow="Model quality" title="Prediction vs truth" subtitle="Accuracy and error trends for the latest labeled outcomes." />
              <PanelBody state={performance}>
                <div className="heroMetrics compact">
                  <HeroMetric label="Accuracy" value={formatPercent(performanceOverview.Accuracy)} tone="success" />
                  <HeroMetric label="Mean absolute error" value={formatHours(performanceOverview.MeanAbsoluteError)} tone="neutral" />
                  <HeroMetric label="Evaluated batches" value={performanceOverview.EvaluatedBatchCount ?? 0} tone="neutral" />
                  <HeroMetric label="Avg spoilage probability" value={formatPercent(performanceOverview.AverageSpoilageProbability)} tone="warn" />
                </div>
                <div className="detailSplit">
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
                    eyebrow="Recent outcomes"
                    title="Latest labeled batches"
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

            <section className="contentPanel">
              <SectionHeader eyebrow="Narrative intelligence" title="Operational query feed" subtitle="Use natural language to summarize risk, vendors, routes, and model drift." />
              <form className="commandAsk large" onSubmit={askQuestion}>
                <input value={question} onChange={(event) => setQuestion(event.target.value)} />
                <button type="submit" className="primaryButton" disabled={chat.status === 'loading'}>
                  {chat.status === 'loading' ? 'Running…' : 'Generate brief'}
                </button>
              </form>
              <div className="answerPanel tall">
                {chat.status === 'loading' && <p>Generating operational brief…</p>}
                {chat.status === 'error' && <p className="errorText">{chat.error}</p>}
                {chat.status === 'ready' && chat.data && (
                  <>
                    <strong>{chat.data.summary}</strong>
                    <span>{chat.data.chart} · {(chat.data.rows || []).length} rows returned</span>
                  </>
                )}
                {chat.status === 'idle' && <p className="sectionSubtitle">Use prompts from the left rail or write a custom operational question.</p>}
              </div>
              <div className="promptStack inline">
                {QUICK_PROMPTS.map((prompt) => (
                  <button key={prompt} type="button" className="chipButton" onClick={() => runQuestion(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </section>
          </section>
        )}

        {workspace === 'controls' && (
          <section className="controlsGrid">
            <section className="contentPanel">
              <SectionHeader eyebrow="Runtime config" title="Threshold and alert tuning" subtitle="Customer-scoped controls that affect anomaly detection, risk bands, and alert routing." />
              <PanelBody state={customerSettings}>
                <form className="settingsForm modern" onSubmit={saveSettings}>
                  <div className="settingsCluster">
                    <strong>Risk bands</strong>
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
                    </div>
                  </div>

                  <div className="settingsCluster">
                    <strong>Anomaly thresholds</strong>
                    <div className="settingsGrid">
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
                      {settingsSaveState.status === 'saving' ? 'Saving…' : 'Publish config'}
                    </button>
                    {settingsSaveState.status === 'saved' && <span className="successText">Config published</span>}
                    {settingsSaveState.error && <span className="errorText">{settingsSaveState.error}</span>}
                  </div>
                </form>
              </PanelBody>
            </section>

            <section className="contentPanel">
              <SectionHeader eyebrow="MLOps" title="Retraining loop" subtitle="Retrain from PostgreSQL labels and hot-reload the live ONNX bundle." />
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
                eyebrow="Training history"
                title="Recent runs"
                rows={runRows.map((run) => ({
                  key: run.RunId,
                  title: `${run.ModelVersion || 'Pending version'} · ${run.Status}`,
                  subtitle: `${formatTimestamp(run.StartedAt)}${run.CompletedAt ? ` → ${formatTimestamp(run.CompletedAt)}` : ''}`,
                  status: run.Status,
                }))}
              />
            </section>
          </section>
        )}
      </main>

      <BatchDrawer
        open={isBatchDrawerOpen && Boolean(selectedBatchId)}
        state={batchDetail}
        chartPalette={chartPalette}
        selectedBatchId={selectedBatchId}
        summary={selectedSummary}
        sensorTrend={detailSensorTrend}
        predictionTrend={predictionTrend}
        ackingEventId={ackingEventId}
        onClose={() => setBatchDrawerOpen(false)}
        onAcknowledge={onAcknowledge}
      />
    </div>
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

function HeroMetric({ label, value, tone = 'neutral' }) {
  return (
    <div className={`heroMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function HeroStat({ label, value }) {
  return (
    <div className="heroStat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SmallStat({ label, value }) {
  return (
    <div className="smallStat">
      <strong>{value}</strong>
      <span>{label}</span>
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
          <div className="stackRow dark" key={row.key}>
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

function BatchDrawer({
  chartPalette,
  open,
  state,
  selectedBatchId,
  summary,
  sensorTrend,
  predictionTrend,
  ackingEventId,
  onClose,
  onAcknowledge,
}) {
  if (!open) {
    return null;
  }

  const explanation = state.data?.explanation ?? null;

  return (
    <div className="drawerShell" role="presentation">
      <button type="button" className="drawerBackdrop" onClick={onClose} aria-label="Close batch drawer" />
      <aside className="drawerPanel">
        <div className="drawerHeader">
          <div>
            <p className="eyebrow">Batch drill-down</p>
            <h2>{selectedBatchId}</h2>
            <p className="sectionSubtitle">{summary ? `${summary.Origin} → ${summary.Destination}` : 'Loading route context…'}</p>
          </div>
          <button type="button" className="ghostButton" onClick={onClose}>Close</button>
        </div>
        <PanelBody state={state}>
          {summary && (
            <>
              <div className="drawerMetrics">
                <HeroMetric label="Spoilage probability" value={formatPercent(summary.SpoilageProbability)} tone="danger" />
                <HeroMetric label="Hours left" value={formatHours(summary.EstimatedHoursLeft)} tone="neutral" />
                <HeroMetric label="Cold-chain breaks" value={summary.ColdChainBreaks ?? 0} tone="warn" />
                <HeroMetric label="Alert channel" value={summary.AlertChannel || 'None'} tone="neutral" />
              </div>
              {explanation && (
                <div className="drawerInsight">
                  <SectionHeader eyebrow="Explanation layer" title="Why the model flagged this batch" />
                  <strong>{explanation.summary}</strong>
                  <p className="sectionSubtitle">{explanation.recommendedAction}</p>
                  {!!explanation.contributingFactors?.length && (
                    <div className="factorList">
                      {explanation.contributingFactors.map((factor) => (
                        <span key={factor} className="factorPill">{factor}</span>
                      ))}
                    </div>
                  )}
                  <span className="drawerMeta">Generated by {explanation.generatedBy}</span>
                </div>
              )}
              <div className="drawerChart">
                <SectionHeader eyebrow="Sensor history" title="Temperature + humidity" />
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={sensorTrend} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
                    <CartesianGrid stroke={chartPalette.grid} vertical={false} />
                    <XAxis dataKey="time" tickLine={false} axisLine={false} stroke={chartPalette.axis} />
                    <YAxis tickLine={false} axisLine={false} stroke={chartPalette.axis} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="temperature" stroke={chartPalette.temperature} strokeWidth={3} dot={false} />
                    <Line type="monotone" dataKey="humidity" stroke={chartPalette.humidity} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="drawerChart">
                <SectionHeader eyebrow="Prediction history" title="Probability over time" />
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={predictionTrend} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
                    <CartesianGrid stroke={chartPalette.grid} vertical={false} />
                    <XAxis dataKey="time" tickLine={false} axisLine={false} stroke={chartPalette.axis} />
                    <YAxis tickLine={false} axisLine={false} domain={[0, 100]} stroke={chartPalette.axis} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="probability" stroke={chartPalette.probability} strokeWidth={3} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <StackList
                eyebrow="Anomalies"
                title="Latest batch events"
                rows={(state.data?.anomalies ?? []).map((entry) => ({
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
              <StackList
                eyebrow="Alert log"
                title="Delivery history"
                rows={(state.data?.alertLog ?? []).map((entry) => ({
                  key: entry.LogId,
                  title: entry.Channel,
                  subtitle: `${formatTimestamp(entry.AttemptedAt)} · ${entry.Provider || 'system'} · ${entry.Target || 'n/a'}`,
                  status: entry.DeliveryStatus,
                }))}
              />
            </>
          )}
        </PanelBody>
      </aside>
    </div>
  );
}

function RouteMap({ routes, compact = false }) {
  if (!routes.length) {
    return <p className="empty">No route data matches the current filters.</p>;
  }

  const validRoutes = routes.filter((route) => (
    Number.isFinite(Number(route.OriginLongitude))
    && Number.isFinite(Number(route.OriginLatitude))
    && Number.isFinite(Number(route.DestinationLongitude))
    && Number.isFinite(Number(route.DestinationLatitude))
  ));

  if (!validRoutes.length) {
    return <p className="empty">Route coordinates are not available for the current filters.</p>;
  }

  const points = validRoutes.flatMap((route) => ([
    [Number(route.OriginLongitude), Number(route.OriginLatitude)],
    [Number(route.DestinationLongitude), Number(route.DestinationLatitude)],
  ]));
  const minX = Math.min(...points.map(([x]) => x));
  const maxX = Math.max(...points.map(([x]) => x));
  const minY = Math.min(...points.map(([, y]) => y));
  const maxY = Math.max(...points.map(([, y]) => y));
  const width = compact ? 560 : 960;
  const height = compact ? 280 : 440;
  const padding = compact ? 32 : 52;

  const project = (longitude, latitude) => ({
    x: padding + ((longitude - minX) / Math.max(maxX - minX, 1)) * (width - padding * 2),
    y: height - padding - ((latitude - minY) / Math.max(maxY - minY, 1)) * (height - padding * 2),
  });

  return (
    <div className="routeMapWrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="routeMapSvg" aria-label="Route risk map">
        <defs>
          <linearGradient id="routeGlow" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#57d0ff" stopOpacity="0.65" />
            <stop offset="100%" stopColor="#7fffd4" stopOpacity="0.18" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={width} height={height} rx="26" fill="var(--map-bg)" />
        {[0.2, 0.4, 0.6, 0.8].map((marker) => (
          <g key={marker} opacity="0.18">
            <line x1={padding} x2={width - padding} y1={height * marker} y2={height * marker} stroke="var(--map-grid)" />
            <line x1={width * marker} x2={width * marker} y1={padding} y2={height - padding} stroke="var(--map-grid)" />
          </g>
        ))}
        {validRoutes.map((route) => {
          const start = project(Number(route.OriginLongitude), Number(route.OriginLatitude));
          const end = project(Number(route.DestinationLongitude), Number(route.DestinationLatitude));
          const midX = (start.x + end.x) / 2;
          const midY = Math.min(start.y, end.y) - (compact ? 18 : 28);
          const probability = Number(route.AverageSpoilageProbability) || 0;
          const color = probability >= 0.7 ? '#ff6b7a' : probability >= 0.45 ? '#f7c66c' : '#57d0ff';
          const strokeWidth = 1.8 + Math.min(Number(route.BatchCount) || 0, 8) * 0.4;
          const routeKey = `${route.Origin}-${route.Destination}`;
          return (
            <g key={routeKey}>
              <path
                d={`M ${start.x} ${start.y} Q ${midX} ${midY} ${end.x} ${end.y}`}
                stroke={color}
                strokeWidth={strokeWidth}
                fill="none"
                strokeOpacity="0.85"
              />
              <circle cx={start.x} cy={start.y} r="5.5" fill="var(--map-origin)" />
              <circle cx={end.x} cy={end.y} r="5.5" fill="var(--map-destination)" />
              {!compact && (
                <>
                  <text x={start.x + 8} y={start.y - 10} fontSize="12" fill="var(--map-text)">{route.Origin}</text>
                  <text x={end.x + 8} y={end.y - 10} fontSize="12" fill="var(--map-text)">{route.Destination}</text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      <div className="routeLegend">
        {validRoutes.slice(0, compact ? 3 : 5).map((route) => (
          <div className="routeLegendRow" key={`${route.Origin}-${route.Destination}-legend`}>
            <div>
              <strong>{route.Origin} → {route.Destination}</strong>
              <span>{route.BatchCount} batches · {route.CriticalBatchCount} critical</span>
            </div>
            <span className="legendValue">{formatPercent(route.AverageSpoilageProbability)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Icon({ name }) {
  const paths = {
    grid: <path d="M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z" />,
    route: <path d="M3 6h7l4 12h7M7 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4m10 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4" />,
    spark: <path d="m4 14 4-4 3 3 5-7 4 4M4 20h16" />,
    sliders: <path d="M4 6h10M18 6h2M10 6v12M4 18h4M12 18h8M14 18V6" />,
    search: <path d="m21 21-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name] || paths.grid}</svg>;
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

function matchesRiskFilter(value, filter) {
  if (filter === 'ALL') {
    return true;
  }
  return String(value || '').toUpperCase() === filter;
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

const tooltipStyle = {
  backgroundColor: 'var(--tooltip-bg)',
  border: '1px solid var(--tooltip-border)',
  borderRadius: '14px',
  color: 'var(--tooltip-text)',
};

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
