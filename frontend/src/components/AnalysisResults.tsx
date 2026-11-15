import { useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  BookOpen,
  ListTree,
  Eye,
  Sparkles,
  ArrowRight,
  RotateCcw,
} from 'lucide-react';
import type {
  AccessibilityAnalysisResponse,
  Barrier,
  Dimension,
} from '../types/analysis';

interface AnalysisResultsProps {
  data: AccessibilityAnalysisResponse | null;
  onGenerateAdapted?: () => void;
  onViewAdapted?: () => void;
  onResetAnalysis?: () => void;
}

export function AnalysisResults({
  data,
  onGenerateAdapted,
  onViewAdapted,
  onResetAnalysis,
}: AnalysisResultsProps) {
  const [decisions, setDecisions] = useState<Record<string, 'accepted' | 'rejected'>>({});
  const [openDimensions, setOpenDimensions] = useState<Record<string, boolean>>({});
  const [openBarriers, setOpenBarriers] = useState<Record<string, boolean>>({});

  if (!data) return null;

  const { estimated_score, summary, dimensions, barriers } = data;

  const acceptedCount = Object.values(decisions).filter((d) => d === 'accepted').length;
  const criticalDimensionsCount = dimensions
    ? dimensions.filter((d) => d.status?.toLowerCase() !== 'ok' && d.status?.toLowerCase() !== 'óptimo').length
    : 0;

  function toggleDimension(category: string) {
    setOpenDimensions((prev) => ({
      ...prev,
      [category]: prev[category] === undefined ? false : !prev[category],
    }));
  }

  function toggleBarrier(barrierId: string) {
    setOpenBarriers((prev) => ({
      ...prev,
      [barrierId]: !prev[barrierId],
    }));
  }

  function handleDecision(barrierId: string, decision: 'accepted' | 'rejected') {
    setDecisions((prev) => ({
      ...prev,
      [barrierId]: decision,
    }));
  }

  // Ícono según la categoría de la dimensión
  function getDimensionIcon(category: string) {
    const cat = category.toLowerCase();
    if (cat.includes('comprens')) return <BookOpen size={20} />;
    if (cat.includes('estructur')) return <ListTree size={20} />;
    return <Eye size={20} />;
  }

  // Cálculo para el anillo SVG del puntaje
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (estimated_score / 100) * circumference;

  return (
    <div className="via-detail-container">
      {/* Meta superior: Botón "Nuevo análisis" y Badge de estado alineados */}
      <div className="via-detail-top-meta">
        {onResetAnalysis ? (
          <button
            type="button"
            className="via-btn-new-analysis"
            onClick={onResetAnalysis}
          >
            <RotateCcw size={16} />
            <span>Nuevo análisis</span>
          </button>
        ) : (
          <span className="via-detail-file-info">Documento analizado</span>
        )}

        <span className="via-status-pill-success">
          <CheckCircle2 size={14} /> ANÁLISIS COMPLETADO
        </span>
      </div>

      {/* Tarjeta de Resumen General */}
      <section className="via-summary-card">
        <div className="via-score-column">
          <div className="via-donut-wrapper">
            <svg width="104" height="104" viewBox="0 0 104 104">
              <circle
                cx="52"
                cy="52"
                r={radius}
                fill="none"
                stroke="#E5E9F0"
                strokeWidth="9"
              />
              <circle
                cx="52"
                cy="52"
                r={radius}
                fill="none"
                stroke="#0B6E86"
                strokeWidth="9"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                transform="rotate(-90 52 52)"
              />
            </svg>
            <div className="via-donut-center">
              <span className="via-donut-number">{estimated_score}</span>
              <span className="via-donut-total">de 100</span>
            </div>
          </div>
          <p className="via-score-caption">
            Nivel orientativo<br />de accesibilidad
          </p>
        </div>

        <div className="via-summary-content">
          <span className="via-section-eyebrow">RESUMEN GENERAL</span>
          <h2 className="via-summary-title">Resultados del análisis de accesibilidad</h2>
          <p className="via-summary-text">
            {summary ||
              'Se analizaron las dimensiones de accesibilidad: comprensión, estructura, presentación visual, representación alternativa y navegación. El puntaje es orientativo y no constituye una certificación formal de accesibilidad.'}
          </p>

          <div className="via-summary-pills">
            {criticalDimensionsCount > 0 && (
              <span className="via-pill-alert via-pill-danger">
                <span className="via-pill-dot">{criticalDimensionsCount}</span>
                Dimensiones requieren atención
              </span>
            )}
            {barriers && barriers.length > 0 && (
              <span className="via-pill-alert via-pill-warning">
                <span className="via-pill-dot">{barriers.length}</span>
                Contenidos para revisar
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Sección Revisión Detallada */}
      <section className="via-findings-section">
        <div className="via-findings-header">
          <div>
            <span className="via-section-eyebrow">REVISIÓN DETALLADA</span>
            <h3 className="via-findings-title">Detalle de hallazgos</h3>
          </div>
          <span className="via-selected-counter">
            {acceptedCount} {acceptedCount === 1 ? 'hallazgo seleccionado' : 'hallazgos seleccionados'}
          </span>
        </div>

        <div className="via-dimensions-accordion-list">
          {dimensions &&
            dimensions.map((dim: Dimension, idx: number) => {
              const dimBarriers = (barriers || []).filter(
                (b) => b.category.toLowerCase() === dim.category.toLowerCase()
              );
              // Por defecto abrimos la primera dimensión para que se vea como en Figma
              const isOpen =
                openDimensions[dim.category] !== undefined
                  ? openDimensions[dim.category]
                  : idx === 0;

              return (
                <div key={dim.category} className="via-dimension-card">
                  <button
                    type="button"
                    className="via-dimension-header"
                    onClick={() => toggleDimension(dim.category)}
                    aria-expanded={isOpen}
                  >
                    <div className="via-dimension-left">
                      <div className="via-dimension-icon">
                        {getDimensionIcon(dim.category)}
                      </div>
                      <div>
                        <div className="via-dimension-title-row">
                          <span className="via-dimension-name">{dim.category}</span>
                          {dimBarriers.length > 0 && (
                            <span className="via-barrier-count-badge">
                              {dimBarriers.length}{' '}
                              {dimBarriers.length === 1 ? 'Barrera' : 'Barreras'}
                            </span>
                          )}
                        </div>
                        <p className="via-dimension-subtitle">{dim.comment}</p>
                      </div>
                    </div>
                    <span className="via-chevron-icon">
                      {isOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                    </span>
                  </button>

                  {isOpen && dimBarriers.length > 0 && (
                    <div className="via-dimension-body">
                      {dimBarriers.map((barrier: Barrier) => {
                        const isDetailOpen = Boolean(openBarriers[barrier.id]);
                        const currentDecision = decisions[barrier.id];
                        const isHigh =
                          barrier.severity?.toLowerCase() === 'high' ||
                          barrier.severity?.toLowerCase() === 'alta';

                        return (
                          <div key={barrier.id} className="via-barrier-row-wrapper">
                            <div className="via-barrier-row">
                              <div className="via-barrier-main">
                                <span
                                  className={`via-status-dot ${
                                    isHigh ? 'dot-danger' : 'dot-warning'
                                  }`}
                                />
                                <span className="via-barrier-issue">{barrier.issue}</span>
                                <span
                                  className={`via-barrier-tag ${
                                    isHigh ? 'tag-danger' : 'tag-warning'
                                  }`}
                                >
                                  {isHigh ? 'Barrera detectada' : 'Para revisar'}
                                </span>
                              </div>

                              <div className="via-barrier-actions">
                                <button
                                  type="button"
                                  className="via-btn-detail-toggle"
                                  onClick={() => toggleBarrier(barrier.id)}
                                >
                                  <span>Ver detalles</span>
                                  {isDetailOpen ? (
                                    <ChevronUp size={15} />
                                  ) : (
                                    <ChevronDown size={15} />
                                  )}
                                </button>
                              </div>
                            </div>

                            {/* Panel desplegable al hacer clic en "Ver detalles" */}
                            {isDetailOpen && (
                              <div className="via-barrier-expanded-panel">
                                <p className="via-barrier-explanation">{barrier.explanation}</p>
                                <div className="via-barrier-recommendation">
                                  <strong>Recomendación:</strong> {barrier.recommendation}
                                </div>
                                {barrier.suggested_rewrite && (
                                  <div className="via-barrier-rewrite">
                                    <strong>Sugerencia de redacción:</strong>{' '}
                                    <em>“{barrier.suggested_rewrite}”</em>
                                  </div>
                                )}
                                <div className="via-barrier-decision-btns">
                                  <button
                                    type="button"
                                    className={`via-decision-btn accept ${
                                      currentDecision === 'accepted' ? 'active' : ''
                                    }`}
                                    onClick={() => handleDecision(barrier.id, 'accepted')}
                                  >
                                    {currentDecision === 'accepted'
                                      ? '✓ Cambio aceptado'
                                      : 'Aceptar cambio'}
                                  </button>
                                  <button
                                    type="button"
                                    className={`via-decision-btn reject ${
                                      currentDecision === 'rejected' ? 'active' : ''
                                    }`}
                                    onClick={() => handleDecision(barrier.id, 'rejected')}
                                  >
                                    {currentDecision === 'rejected'
                                      ? '✕ Rechazado'
                                      : 'Rechazar'}
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </section>

      {/* Banner inferior oscuro "Generar versión adaptada con IA" */}
      <section className="via-ai-cta-banner">
        <div className="via-ai-cta-left">
          <div className="via-ai-cta-icon">
            <Sparkles size={22} />
          </div>
          <div>
            <h4 className="via-ai-cta-title">Generar versión adaptada con IA</h4>
            <p className="via-ai-cta-desc">
              Generá toda una versión completa con IA, así podés solo revisar para adaptar pequeños detalles.
            </p>
          </div>
        </div>

        <div className="via-ai-cta-buttons">
          <button
            type="button"
            className="via-btn-cta-light"
            onClick={onGenerateAdapted}
          >
            <Sparkles size={16} />
            <span>Generar propuestas</span>
          </button>
          <button
            type="button"
            className="via-btn-cta-outline"
            onClick={onViewAdapted}
          >
            <span>Ver versión adaptada</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </div>
  );
}