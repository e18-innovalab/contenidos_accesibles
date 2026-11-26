import { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Cpu,
  FileCheck2,
  FolderUp,
  RefreshCw,
  Share2,
  Sparkles,
  Table2,
} from 'lucide-react';
import { getMyMetrics } from '../../services/api';
import type {
  MetricsRange,
  UserMetricsResponse,
  UserRecentEvent,
} from '../../types/analysis';

const RANGE_OPTIONS: { value: MetricsRange; label: string }[] = [
  { value: '24h', label: 'Últimas 24 h' },
  { value: '7d', label: '7 días' },
  { value: '30d', label: '30 días' },
];

const ACTION_LABELS: Record<string, string> = {
  analysis: 'Diagnóstico ejecutado',
  proposal: 'Propuesta de adaptación',
  decision: 'Decisión docente',
  upload: 'Archivo subido',
  upload_rejected: 'Archivo rechazado',
  export: 'Exportación generada',
  download: 'Descarga de archivo',
  share_created: 'Enlace compartido creado',
  share_opened: 'Enlace compartido abierto',
  share_revoked: 'Enlace compartido revocado',
  transformation: 'Transformación solicitada',
  transformation_decision: 'Revisión de transformación',
  ai_call: 'Procesamiento con IA',
  rate_limited: 'Límite de uso alcanzado',
};

function formatBucketLabel(iso: string, range: MetricsRange): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  if (range === '24h') {
    return date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatNumber(n: number): string {
  return n.toLocaleString('es-AR');
}

function describeEvent(ev: UserRecentEvent): string {
  const parts: string[] = [];
  if (ev.format) parts.push(ev.format.toUpperCase());
  if (ev.adaptation_type) parts.push(ev.adaptation_type.replace(/_/g, ' '));
  if (ev.detail && ev.detail !== 'ok') parts.push(ev.detail);
  if (typeof ev.score === 'number') parts.push(`Puntaje ${ev.score}/100`);
  if (typeof ev.barriers === 'number') parts.push(`${ev.barriers} barrera(s)`);
  if (ev.mock === 1) parts.push('Modo prueba');
  return parts.join(' · ') || '—';
}

export function MetricsView() {
  const [range, setRange] = useState<MetricsRange>('7d');
  const [data, setData] = useState<UserMetricsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState<boolean>(false);

  async function load(selectedRange: MetricsRange) {
    setLoading(true);
    setError(null);
    try {
      const res = await getMyMetrics(selectedRange);
      setData(res);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No se pudieron cargar tus métricas.',
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(range);
  }, [range]);

  const stats = data?.in_range;
  const allTime = data?.all_time;

  const accepted = (stats?.decisions?.aceptada ?? 0) + (stats?.decisions?.editada ?? 0);
  const discarded = stats?.decisions?.descartada ?? 0;
  const totalDecisions = accepted + discarded;
  const acceptanceRate =
    totalDecisions > 0 ? Math.round((accepted / totalDecisions) * 100) : null;

  const totalOutputs =
    (stats?.transformations ?? 0) +
    (stats?.exports ?? 0) +
    (stats?.shares_created ?? 0);

  const buckets = data?.buckets ?? [];
  const tokenSeries = data?.tokens ?? [];
  const activityByBucket = buckets.map((_, idx) =>
    Object.values(data?.activity ?? {}).reduce((acc, arr) => acc + (arr[idx] ?? 0), 0),
  );
  const maxTokens = Math.max(...tokenSeries, 1);

  return (
    <div className="via-metrics-page">
      {/* Cabecera */}
      <header className="via-metrics-header">
        <div>
          <div className="via-metrics-eyebrow">
            <BarChart3 size={14} />
            <span>ACTIVIDAD DOCENTE</span>
          </div>
          <h1 className="via-page-title">Métricas</h1>
          <p className="via-page-subtitle">
            Resumen de tus diagnósticos, adaptaciones, salidas generadas y consumo de tokens.
          </p>
        </div>

        <div className="via-metrics-controls">
          <div className="via-segmented" role="group" aria-label="Período de métricas">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`via-segmented-btn ${range === opt.value ? 'active' : ''}`}
                onClick={() => setRange(opt.value)}
                disabled={loading}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="via-btn-new-analysis"
            onClick={() => void load(range)}
            disabled={loading}
          >
            <RefreshCw size={15} className={loading ? 'via-spin' : ''} />
            <span>{loading ? 'Actualizando…' : 'Actualizar'}</span>
          </button>
        </div>
      </header>

      {error && (
        <div className="via-alert via-alert-danger" role="alert">
          <span>{error}</span>
        </div>
      )}

      {data && stats && allTime && (
        <>
          {/* 4 Tarjetas KPI */}
          <section className="via-metrics-kpis" aria-label="Indicadores principales">
            <article className="via-metric-card">
              <div className="via-metric-icon teal">
                <FileCheck2 size={20} />
              </div>
              <div className="via-metric-label">Diagnósticos realizados</div>
              <div className="via-metric-value">{formatNumber(stats.analyses)}</div>
              <div className="via-metric-sub">
                {stats.mock_analyses > 0
                  ? `${stats.mock_analyses} en modo prueba · `
                  : ''}
                Histórico total: {formatNumber(allTime.analyses)}
              </div>
            </article>

            <article className="via-metric-card">
              <div className="via-metric-icon green">
                <CheckCircle2 size={20} />
              </div>
              <div className="via-metric-label">Decisiones docentes</div>
              <div className="via-metric-value">{formatNumber(totalDecisions)}</div>
              <div className="via-metric-sub">
                {acceptanceRate !== null
                  ? `${acceptanceRate}% aprovechadas (${accepted} acept./edit.)`
                  : `${formatNumber(stats.proposals)} propuestas generadas`}
              </div>
            </article>

            <article className="via-metric-card">
              <div className="via-metric-icon blue">
                <Sparkles size={20} />
              </div>
              <div className="via-metric-label">Transformaciones y salidas</div>
              <div className="via-metric-value">{formatNumber(totalOutputs)}</div>
              <div className="via-metric-sub">
                {stats.transformations} transform. · {stats.exports} export. · {stats.share_opens} aperturas
              </div>
            </article>

            <article className="via-metric-card accent">
              <div className="via-metric-icon gold">
                <Cpu size={20} />
              </div>
              <div className="via-metric-label">Tokens consumidos</div>
              <div className="via-metric-value">{formatNumber(stats.tokens)}</div>
              <div className="via-metric-sub">
                {formatNumber(stats.ai_calls)} llamadas con IA · Histórico: {formatNumber(allTime.tokens)}
              </div>
            </article>
          </section>

          {/* Gráfico de evolución de tokens */}
          <section className="via-metrics-panel" aria-label="Evolución de tokens y actividad">
            <div className="via-metrics-panel-head">
              <div>
                <h2 className="via-metrics-panel-title">Consumo de tokens en el período</h2>
                <p className="via-metrics-panel-sub">
                  Distribución por {data.unit === 'hour' ? 'hora' : 'día'} según tu zona horaria.
                </p>
              </div>
              <button
                type="button"
                className="via-btn-detail-toggle"
                onClick={() => setShowTable((v) => !v)}
              >
                <Table2 size={15} />
                <span>{showTable ? 'Ver gráfico' : 'Ver como tabla'}</span>
              </button>
            </div>

            {showTable ? (
              <div className="via-table-scroll">
                <table className="via-metrics-table">
                  <thead>
                    <tr>
                      <th>Período</th>
                      <th>Tokens</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buckets.map((b, idx) => (
                      <tr key={b}>
                        <td>{formatBucketLabel(b, range)}</td>
                        <td>{formatNumber(tokenSeries[idx] ?? 0)}</td>
                        <td>{formatNumber(activityByBucket[idx] ?? 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="via-chart-box">
                <div className="via-bars" role="img" aria-label="Gráfico de barras de tokens por período">
                  {buckets.map((b, idx) => {
                    const val = tokenSeries[idx] ?? 0;
                    const pct = Math.max(val > 0 ? 6 : 2, Math.round((val / maxTokens) * 100));
                    return (
                      <div key={b} className="via-bar-col" title={`${formatBucketLabel(b, range)}: ${formatNumber(val)} tokens`}>
                        <div className="via-bar-track">
                          <div
                            className={`via-bar-fill ${val > 0 ? 'has-value' : ''}`}
                            style={{ height: `${pct}%` }}
                          />
                        </div>
                        <span className="via-bar-label">
                          {buckets.length <= 12 || idx % Math.ceil(buckets.length / 8) === 0
                            ? formatBucketLabel(b, range)
                            : ''}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>

          {/* Desglose en 2 tarjetas */}
          <section className="via-metrics-two-col">
            <article className="via-metrics-panel">
              <div className="via-metrics-panel-head">
                <h2 className="via-metrics-panel-title">Adaptaciones y Transformaciones</h2>
                <Activity size={18} color="#063f4e" />
              </div>

              <div className="via-breakdown-list">
                <div className="via-breakdown-row">
                  <span>Propuestas aceptadas</span>
                  <strong>{formatNumber(stats.decisions?.aceptada ?? 0)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Propuestas editadas por vos</span>
                  <strong>{formatNumber(stats.decisions?.editada ?? 0)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Propuestas descartadas</span>
                  <strong>{formatNumber(stats.decisions?.descartada ?? 0)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Transformaciones aceptadas / editadas</span>
                  <strong>
                    {formatNumber(
                      (stats.transformation_decisions?.aceptada ?? 0) +
                        (stats.transformation_decisions?.editada ?? 0),
                    )}
                  </strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Límites por minuto alcanzados</span>
                  <strong>{formatNumber(stats.rate_limited)}</strong>
                </div>
              </div>
            </article>

            <article className="via-metrics-panel">
              <div className="via-metrics-panel-head">
                <h2 className="via-metrics-panel-title">Materiales y Alcance</h2>
                <Share2 size={18} color="#0072ce" />
              </div>

              <div className="via-breakdown-list">
                <div className="via-breakdown-row">
                  <span><FolderUp size={14} className="via-inline-icon" /> Archivos subidos</span>
                  <strong>{formatNumber(stats.uploads)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Exportaciones generadas</span>
                  <strong>{formatNumber(stats.exports)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Descargas directas</span>
                  <strong>{formatNumber(stats.downloads)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Enlaces compartidos creados</span>
                  <strong>{formatNumber(stats.shares_created)}</strong>
                </div>
                <div className="via-breakdown-row">
                  <span>Aperturas de tus enlaces compartidos</span>
                  <strong>{formatNumber(stats.share_opens)}</strong>
                </div>
              </div>
            </article>
          </section>

          {/* Actividad reciente */}
          <section className="via-metrics-panel" aria-label="Actividad reciente">
            <div className="via-metrics-panel-head">
              <div>
                <h2 className="via-metrics-panel-title">Actividad reciente</h2>
                <p className="via-metrics-panel-sub">
                  Últimos eventos registrados en tu cuenta (sin detalles internos de modelo).
                </p>
              </div>
            </div>

            {data.recent.length === 0 ? (
              <p className="via-metrics-empty">Todavía no hay actividad registrada en tu cuenta.</p>
            ) : (
              <div className="via-table-scroll">
                <table className="via-metrics-table">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Acción</th>
                      <th>Detalle</th>
                      <th>Latencia</th>
                      <th>Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((ev, idx) => (
                      <tr key={`${ev.created_at}-${idx}`}>
                        <td>{formatDateTime(ev.created_at)}</td>
                        <td>
                          <strong>{ACTION_LABELS[ev.action] ?? ev.action}</strong>
                        </td>
                        <td>{describeEvent(ev)}</td>
                        <td>{typeof ev.latency_ms === 'number' ? `${ev.latency_ms} ms` : '—'}</td>
                        <td>{ev.tokens > 0 ? formatNumber(ev.tokens) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
