import { useEffect, useState } from 'react';
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
  Save,
  Undo2,
  XCircle,
} from 'lucide-react';
import {
  ApiError,
  createAdaptationProposal,
  decideAdaptation,
  getAdaptationProposal,
  listAdaptations,
  undoAdaptation,
} from '../services/api';
import type {
  AccessibilityAnalysisResponse,
  AdaptationProposal,
  AdaptationType,
  Barrier,
  Dimension,
} from '../types/analysis';

interface AnalysisResultsProps {
  data: AccessibilityAnalysisResponse | null;
  onGenerateAdapted?: () => void;
  onViewAdapted?: () => void;
  onResetAnalysis?: () => void;
}

const ADAPTATION_TYPE_OPTIONS: { value: AdaptationType; label: string }[] = [
  { value: 'lenguaje_claro', label: 'Lenguaje claro' },
  { value: 'consigna_en_pasos', label: 'Consigna en pasos' },
  { value: 'reorganizar', label: 'Reorganizar en bloques' },
  { value: 'mejorar_estructura', label: 'Mejorar estructura' },
];

function inferDefaultAdaptationType(category: string, issue: string): AdaptationType {
  const text = `${category} ${issue}`.toLowerCase();
  if (text.includes('paso') || text.includes('acción') || text.includes('accion') || text.includes('consigna')) {
    return 'consigna_en_pasos';
  }
  if (text.includes('estructur') || text.includes('título') || text.includes('titulo') || text.includes('lista')) {
    return 'mejorar_estructura';
  }
  if (text.includes('párrafo') || text.includes('parrafo') || text.includes('extens') || text.includes('reorganiz')) {
    return 'reorganizar';
  }
  return 'lenguaje_claro';
}

function isSevereBarrier(severity?: string): boolean {
  const normalized = (severity || '').toLowerCase();
  return normalized === 'barrera_detectada' || normalized === 'high' || normalized === 'alta';
}

export function AnalysisResults({
  data,
  onGenerateAdapted,
  onViewAdapted,
  onResetAnalysis,
}: AnalysisResultsProps) {
  const [openDimensions, setOpenDimensions] = useState<Record<string, boolean>>({});
  const [openBarriers, setOpenBarriers] = useState<Record<string, boolean>>({});

  // Estado de propuestas por barrier.id
  const [proposalsByBarrier, setProposalsByBarrier] = useState<Record<string, AdaptationProposal>>({});
  const [selectedTypeByBarrier, setSelectedTypeByBarrier] = useState<Record<string, AdaptationType>>({});
  const [editableTextByBarrier, setEditableTextByBarrier] = useState<Record<string, string>>({});
  const [customFragmentByBarrier, setCustomFragmentByBarrier] = useState<Record<string, string>>({});
  const [useMockAi, setUseMockAi] = useState<boolean>(false);

  // Estados de carga y error por barrera
  const [generatingByBarrier, setGeneratingByBarrier] = useState<Record<string, boolean>>({});
  const [savingByBarrier, setSavingByBarrier] = useState<Record<string, boolean>>({});
  const [errorByBarrier, setErrorByBarrier] = useState<Record<string, string | null>>({});

  useEffect(() => {
    if (!data?.analysis_id) return;
    let cancelled = false;

    listAdaptations(data.analysis_id)
      .then((existingProposals) => {
        if (cancelled || !Array.isArray(existingProposals)) return;
        const latestByBarrier: Record<string, AdaptationProposal> = {};
        for (const prop of existingProposals) {
          latestByBarrier[prop.barrier_id] = prop;
        }
        setProposalsByBarrier(latestByBarrier);
        setEditableTextByBarrier((prev) => {
          const next = { ...prev };
          for (const [bId, prop] of Object.entries(latestByBarrier)) {
            if (next[bId] === undefined) {
              next[bId] = prop.final_text ?? prop.edited_text ?? prop.proposed_text;
            }
          }
          return next;
        });
      })
      .catch(() => {
        // Si no hay propuestas previas o el diagnóstico es local/sin persistencia, no bloquea la vista
      });

    return () => {
      cancelled = true;
    };
  }, [data?.analysis_id]);

  if (!data) return null;

  const { analysis_id, estimated_score, summary, dimensions, barriers } = data;

  const resolvedCount = Object.values(proposalsByBarrier).filter(
    (p) => p.status === 'aceptada' || p.status === 'editada'
  ).length;

  const criticalDimensionsCount = dimensions
    ? dimensions.filter((d) => {
        const st = (d.status || '').toLowerCase();
        return st !== 'correcta' && st !== 'ok' && st !== 'óptimo' && st !== 'optimo';
      }).length
    : 0;

  function toggleDimension(category: string) {
    setOpenDimensions((prev) => ({
      ...prev,
      [category]: prev[category] === undefined ? false : !prev[category],
    }));
  }

  function toggleBarrier(barrier: Barrier) {
    setOpenBarriers((prev) => {
      const nextOpen = !prev[barrier.id];
      if (nextOpen) {
        setSelectedTypeByBarrier((typePrev) => ({
          ...typePrev,
          [barrier.id]:
            typePrev[barrier.id] ?? inferDefaultAdaptationType(barrier.category, barrier.issue),
        }));
        setEditableTextByBarrier((textPrev) => {
          if (textPrev[barrier.id] !== undefined) return textPrev;
          const existing = proposalsByBarrier[barrier.id];
          const initialText =
            existing?.final_text ??
            existing?.edited_text ??
            existing?.proposed_text ??
            barrier.suggested_rewrite ??
            barrier.original_text ??
            '';
          return { ...textPrev, [barrier.id]: initialText };
        });
      }
      return { ...prev, [barrier.id]: nextOpen };
    });
  }

  async function handleGenerateAiSuggestion(barrier: Barrier) {
    if (!analysis_id) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrier.id]: 'No se encontró un ID de diagnóstico válido para generar propuestas con IA.',
      }));
      return;
    }

    const adaptationType =
      selectedTypeByBarrier[barrier.id] ?? inferDefaultAdaptationType(barrier.category, barrier.issue);
    const fragmentToSend = (customFragmentByBarrier[barrier.id] ?? barrier.original_text ?? '').trim();

    setGeneratingByBarrier((prev) => ({ ...prev, [barrier.id]: true }));
    setErrorByBarrier((prev) => ({ ...prev, [barrier.id]: null }));

    try {
      const proposal = await createAdaptationProposal(
        {
          analysis_id,
          barrier_id: barrier.id,
          adaptation_type: adaptationType,
          fragment: fragmentToSend.length >= 10 ? fragmentToSend : undefined,
        },
        { mock: useMockAi }
      );

      setProposalsByBarrier((prev) => ({ ...prev, [barrier.id]: proposal }));
      setEditableTextByBarrier((prev) => ({ ...prev, [barrier.id]: proposal.proposed_text }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.proposal_id) {
        try {
          const pendingProp = await getAdaptationProposal(err.proposal_id);
          setProposalsByBarrier((prev) => ({ ...prev, [barrier.id]: pendingProp }));
          setEditableTextByBarrier((prev) => ({
            ...prev,
            [barrier.id]: pendingProp.proposed_text,
          }));
          setErrorByBarrier((prev) => ({
            ...prev,
            [barrier.id]:
              'Ya existe una propuesta pendiente para esta barrera. Se cargó para que puedas aceptarla, editarla o descartarla.',
          }));
        } catch {
          setErrorByBarrier((prev) => ({
            ...prev,
            [barrier.id]: err.message,
          }));
        }
      } else if (err instanceof ApiError) {
        setErrorByBarrier((prev) => ({ ...prev, [barrier.id]: err.message }));
      } else {
        setErrorByBarrier((prev) => ({
          ...prev,
          [barrier.id]: 'Ocurrió un error al generar la sugerencia con IA.',
        }));
      }
    } finally {
      setGeneratingByBarrier((prev) => ({ ...prev, [barrier.id]: false }));
    }
  }

  function handleApplyProposalToEditor(barrierId: string, text: string) {
    setEditableTextByBarrier((prev) => ({ ...prev, [barrierId]: text }));
  }

  async function handleSaveDecision(barrier: Barrier) {
    const proposal = proposalsByBarrier[barrier.id];
    const currentText = (editableTextByBarrier[barrier.id] ?? '').trim();

    if (!currentText) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrier.id]: 'La versión editable no puede estar vacía para guardar cambios.',
      }));
      return;
    }

    if (!proposal) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrier.id]: 'Primero generá una sugerencia con IA para registrar la decisión en el backend.',
      }));
      return;
    }

    setSavingByBarrier((prev) => ({ ...prev, [barrier.id]: true }));
    setErrorByBarrier((prev) => ({ ...prev, [barrier.id]: null }));

    try {
      let activeProposal = proposal;
      if (activeProposal.status !== 'pendiente') {
        activeProposal = await undoAdaptation(activeProposal.proposal_id);
      }

      const isModified = currentText !== activeProposal.proposed_text.trim();
      const updated = await decideAdaptation(
        activeProposal.proposal_id,
        isModified
          ? { decision: 'editada', edited_text: currentText }
          : { decision: 'aceptada' }
      );

      setProposalsByBarrier((prev) => ({ ...prev, [barrier.id]: updated }));
      setEditableTextByBarrier((prev) => ({
        ...prev,
        [barrier.id]: updated.final_text ?? currentText,
      }));
    } catch (err) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrier.id]: err instanceof ApiError ? err.message : 'No se pudo guardar la decisión.',
      }));
    } finally {
      setSavingByBarrier((prev) => ({ ...prev, [barrier.id]: false }));
    }
  }

  async function handleDiscardProposal(barrierId: string) {
    const proposal = proposalsByBarrier[barrierId];
    if (!proposal) return;

    setSavingByBarrier((prev) => ({ ...prev, [barrierId]: true }));
    setErrorByBarrier((prev) => ({ ...prev, [barrierId]: null }));

    try {
      let activeProposal = proposal;
      if (activeProposal.status !== 'pendiente') {
        activeProposal = await undoAdaptation(activeProposal.proposal_id);
      }
      const updated = await decideAdaptation(activeProposal.proposal_id, {
        decision: 'descartada',
      });
      setProposalsByBarrier((prev) => ({ ...prev, [barrierId]: updated }));
    } catch (err) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrierId]: err instanceof ApiError ? err.message : 'No se pudo descartar la propuesta.',
      }));
    } finally {
      setSavingByBarrier((prev) => ({ ...prev, [barrierId]: false }));
    }
  }

  async function handleUndoDecision(barrierId: string) {
    const proposal = proposalsByBarrier[barrierId];
    if (!proposal || proposal.status === 'pendiente') return;

    setSavingByBarrier((prev) => ({ ...prev, [barrierId]: true }));
    setErrorByBarrier((prev) => ({ ...prev, [barrierId]: null }));

    try {
      const reverted = await undoAdaptation(proposal.proposal_id);
      setProposalsByBarrier((prev) => ({ ...prev, [barrierId]: reverted }));
      setEditableTextByBarrier((prev) => ({ ...prev, [barrierId]: reverted.proposed_text }));
    } catch (err) {
      setErrorByBarrier((prev) => ({
        ...prev,
        [barrierId]: err instanceof ApiError ? err.message : 'No se pudo deshacer la decisión.',
      }));
    } finally {
      setSavingByBarrier((prev) => ({ ...prev, [barrierId]: false }));
    }
  }

  function getDimensionIcon(category: string) {
    const cat = category.toLowerCase();
    if (cat.includes('comprens')) return <BookOpen size={20} />;
    if (cat.includes('estructur')) return <ListTree size={20} />;
    return <Eye size={20} />;
  }

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (estimated_score / 100) * circumference;

  return (
    <div className="via-detail-container">
      <div className="via-detail-top-meta">
        {onResetAnalysis ? (
          <button type="button" className="via-btn-new-analysis"  onClick={onResetAnalysis} >
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

      <section className="via-findings-section">
        <div className="via-findings-header">
          <div>
            <span className="via-section-eyebrow">REVISIÓN DETALLADA</span>
            <h3 className="via-findings-title">Detalle de hallazgos</h3>
          </div>
          <div className="via-findings-header-right">
            <label className="via-mock-toggle">
              <input
                type="checkbox"
                checked={useMockAi}
                onChange={(e) => setUseMockAi(e.target.checked)}
              />
              <span>Simular IA (mock)</span>
            </label>
            <span className="via-selected-counter">
              {resolvedCount} {resolvedCount === 1 ? 'hallazgo resuelto' : 'hallazgos resueltos'}
            </span>
          </div>
        </div>

        <div className="via-dimensions-accordion-list">
          {dimensions &&
            dimensions.map((dim: Dimension, idx: number) => {
              const dimBarriers = (barriers || []).filter(
                (b) => b.category.toLowerCase() === dim.category.toLowerCase()
              );
              const isOpen =
                openDimensions[dim.category] !== undefined
                  ? openDimensions[dim.category]
                  : idx === 0;

 return (
  <div key={dim.category} className="via-dimension-card">
    <button  type="button" className="via-dimension-header" onClick={() => toggleDimension(dim.category)}  aria-expanded={isOpen} >
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
                        const proposal = proposalsByBarrier[barrier.id];
                        const editableText =
                          editableTextByBarrier[barrier.id] ??
                          proposal?.final_text ??
                          proposal?.edited_text ??
                          proposal?.proposed_text ??
                          barrier.suggested_rewrite ??
                          barrier.original_text ??
                          '';
                        const selectedType =
                          selectedTypeByBarrier[barrier.id] ??
                          inferDefaultAdaptationType(barrier.category, barrier.issue);
                        const isGenerating = Boolean(generatingByBarrier[barrier.id]);
                        const isSaving = Boolean(savingByBarrier[barrier.id]);
                        const barrierError = errorByBarrier[barrier.id];
                        const severe = isSevereBarrier(barrier.severity);

                        return (
                          <div key={barrier.id} className="via-barrier-row-wrapper">
                            <div className="via-barrier-row">
                              <div className="via-barrier-main">
                                <span className={`via-status-dot ${
                                    severe ? 'dot-danger' : 'dot-warning'
                                  }`}
                                />
                                <span className="via-barrier-issue">{barrier.issue}</span>
                                <span
                                  className={`via-barrier-tag ${
                                    severe ? 'tag-danger' : 'tag-warning'
                                  }`}
                                >
                                  {severe ? 'Barrera detectada' : 'Para revisar'}
                                </span>
                                {proposal && proposal.status !== 'pendiente' && (
                                  <span className={`via-proposal-status-badge status-${proposal.status}`}>
                                    {proposal.status === 'aceptada' && '✓ Aceptada'}
                                    {proposal.status === 'editada' && '✎ Editada'}
                                    {proposal.status === 'descartada' && '✕ Descartada'}
                                  </span>
                                )}
                              </div>

                              <div className="via-barrier-actions">
                                <button type="button"  className="via-btn-detail-toggle"  onClick={() => toggleBarrier(barrier)} >
                                  <span>{isDetailOpen ? 'Ocultar edición' : 'Ver detalles'}</span>
                                  {isDetailOpen ? (
                                    <ChevronUp size={15} />
                                  ) : (
                                    <ChevronDown size={15} />
                                  )}
                                </button>
                              </div>
                            </div>

                            {isDetailOpen && (
                              <div className="via-barrier-expanded-panel">
                                <p className="via-barrier-explanation">{barrier.explanation}</p>
                                <div className="via-barrier-recommendation">
                                  <strong>Recomendación:</strong> {barrier.recommendation}
                                </div>

                                <div className="via-assisted-editor-box">
                                  <div className="via-assisted-header">
                                    <div>
                                      <span className="via-assisted-eyebrow">EDICIÓN ASISTIDA</span>
                                      <h4 className="via-assisted-title">
                                        Revisá y adaptá el enunciado
                                      </h4>
                                    </div>

                                    <div className="via-assisted-controls">
                                      <select
                                        aria-label="Tipo de adaptación con IA"
                                        className="via-adaptation-select"
                                        value={selectedType}
                                        onChange={(e) =>
                                          setSelectedTypeByBarrier((prev) => ({
                                            ...prev,
                                            [barrier.id]: e.target.value as AdaptationType,
                                          }))
                                        }
                                      >
                                        {ADAPTATION_TYPE_OPTIONS.map((opt) => (
                                          <option key={opt.value} value={opt.value}>
                                            {opt.label}
                                          </option>
                                        ))}
                                      </select>

                                      <button
                                        type="button"
                                        className="via-btn via-btn-primary via-btn-sm"
                                        onClick={() => handleGenerateAiSuggestion(barrier)}
                                        disabled={isGenerating || isSaving}
                                      >
                                        <Sparkles size={15} />
                                        <span>
                                          {isGenerating ? 'Generando...' : 'Sugerencias con IA'}
                                        </span>
                                      </button>
                                    </div>
                                  </div>

                                  <div className="via-assisted-grid">
                                    <div className="via-original-box">
                                      <span className="via-box-label">Enunciado original</span>
                                      {barrier.original_text ? (
                                        <p className="via-original-text">{barrier.original_text}</p>
                                      ) : (
                                        <div className="via-custom-fragment-wrap">
                                          <p className="via-original-muted">
                                            Esta barrera no cita un fragmento textual. Podés indicar un fragmento (mín. 10 caracteres):
                                          </p>
                                          <textarea
                                            rows={3}
                                            className="via-textarea"
                                            placeholder="Escribí o pegá el fragmento a adaptar..."
                                            value={customFragmentByBarrier[barrier.id] ?? ''}
                                            onChange={(e) =>
                                              setCustomFragmentByBarrier((prev) => ({
                                                ...prev,
                                                [barrier.id]: e.target.value,
                                              }))
                                            }
                                          />
                                        </div>
                                      )}
                                    </div>

                                    <div className="via-editable-box">
                                      <label htmlFor={`editable-${barrier.id}`} className="via-box-label">
                                        Versión editable
                                      </label>
                                      <textarea
                                        id={`editable-${barrier.id}`}
                                        rows={4}
                                        className="via-textarea"
                                        value={editableText}
                                        onChange={(e) =>
                                          setEditableTextByBarrier((prev) => ({
                                            ...prev,
                                            [barrier.id]: e.target.value,
                                          }))
                                        }
                                        placeholder="Escribí la versión adaptada o generá una sugerencia con IA..."
                                      />
                                      <div className="via-editable-footer">
                                        <span className="via-text-counter">
                                          {editableText.length} caracteres
                                        </span>

                                        <div className="via-editable-actions">
                                          {proposal && proposal.status !== 'pendiente' && (
                                            <button
                                              type="button"
                                              className="via-btn via-btn-outline via-btn-sm"
                                              onClick={() => handleUndoDecision(barrier.id)}
                                              disabled={isSaving || isGenerating}
                                            >
                                              <Undo2 size={14} />
                                              <span>Deshacer</span>
                                            </button>
                                          )}

                                          {proposal && proposal.status !== 'descartada' && (
                                            <button
                                              type="button"
                                              className="via-btn via-btn-outline-danger via-btn-sm"
                                              onClick={() => handleDiscardProposal(barrier.id)}
                                              disabled={isSaving || isGenerating}
                                            >
                                              <XCircle size={14} />
                                              <span>Descartar</span>
                                            </button>
                                          )}

                                          <button
                                            type="button"
                                            className="via-btn via-btn-yellow via-btn-sm"
                                            onClick={() => handleSaveDecision(barrier)}
                                            disabled={isSaving || isGenerating}
                                          >
                                            <Save size={14} />
                                            <span>{isSaving ? 'Guardando...' : 'Guardar cambios'}</span>
                                          </button>
                                        </div>
                                      </div>
                                    </div>
                                  </div>

                                  {barrierError && (
                                    <p className="via-validation-error" role="alert">
                                      {barrierError}
                                    </p>
                                  )}

                                  {(proposal || barrier.suggested_rewrite) && (
                                    <div className="via-proposals-section">
                                      <div className="via-proposals-header">
                                        <span className="via-box-label">Alternativas sugeridas</span>
                                      </div>

                                      <div className="via-proposals-grid">
                                        {proposal && (
                                          <div
                                            className={`via-proposal-card ${
                                              editableText.trim() === proposal.proposed_text.trim()
                                                ? 'is-selected'
                                                : ''
                                            }`}
                                          >
                                            <div className="via-proposal-top">
                                              <span className="via-proposal-index">01</span>
                                              <span className="via-proposal-tag">PROPUESTA IA</span>
                                            </div>
                                            <p className="via-proposal-text">{proposal.proposed_text}</p>
                                            <div className="via-proposal-why">
                                              <strong>POR QUÉ SE HACE ESTE CAMBIO</strong>
                                              <p>{proposal.explanation}</p>
                                            </div>
                                            <div className="via-proposal-objective">
                                              <strong>Objetivo conservado:</strong>{' '}
                                              {proposal.preserved_objective}
                                            </div>
                                            <button
                                              type="button"
                                              className="via-btn via-btn-outline via-btn-sm"
                                              onClick={() =>
                                                handleApplyProposalToEditor(
                                                  barrier.id,
                                                  proposal.proposed_text
                                                )
                                              }
                                            >
                                              Usar en versión editable
                                            </button>
                                          </div>
                                        )}

                                        {barrier.suggested_rewrite && (
                                          <div className="via-proposal-card">
                                            <div className="via-proposal-top">
                                              <span className="via-proposal-index">
                                                {proposal ? '02' : '01'}
                                              </span>
                                              <span className="via-proposal-tag">SUGERENCIA DIAGNÓSTICO</span>
                                            </div>
                                            <p className="via-proposal-text">
                                              {barrier.suggested_rewrite}
                                            </p>
                                            <button
                                              type="button"
                                              className="via-btn via-btn-outline via-btn-sm"
                                              onClick={() =>
                                                handleApplyProposalToEditor(
                                                  barrier.id,
                                                  barrier.suggested_rewrite!
                                                )
                                              }
                                            >
                                              Usar en versión editable
                                            </button>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}
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
          <button type="button" className="via-btn-cta-outline" onClick={onViewAdapted} >
            <span>Ver versión adaptada</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </div>
  );
}