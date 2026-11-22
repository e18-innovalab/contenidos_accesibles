import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  Download,
  FileText,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Search,
  PanelLeft,
} from 'lucide-react';
import { exportAdaptedContent, getAdaptedDocument } from '../services/api';
import type {
  AccessibilityAnalysisResponse,
  AdaptedDocumentResponse,
  AdaptationProposal,
} from '../types/analysis';

export interface AdaptedVersionViewProps {
  analysis: AccessibilityAnalysisResponse;
  proposalsByBarrier?: Record<string, AdaptationProposal>;
  originalSourceText?: string;
  onBackToAnalysis: () => void;
}

type ViewMode = 'adapted' | 'original';

function buildFallbackOriginalText(analysis: AccessibilityAnalysisResponse): string {
  const parts: string[] = [];
  if (analysis.summary) {
    parts.push(analysis.summary);
  }
  for (const b of analysis.barriers || []) {
    if (b.original_text?.trim()) {
      parts.push(b.original_text.trim());
    }
  }
  return parts.join('\n\n') || 'No hay contenido original disponible para mostrar.';
}

function buildFallbackAdaptedText(
  baseOriginalText: string,
  proposalsByBarrier: Record<string, AdaptationProposal>,
): string {
  let text = baseOriginalText;
  const resolvedProposals = Object.values(proposalsByBarrier).filter(
    (p) => p.status === 'aceptada' || p.status === 'editada',
  );

  for (const prop of resolvedProposals) {
    const replacement = (prop.final_text ?? prop.edited_text ?? prop.proposed_text ?? '').trim();
    if (!replacement) continue;
    if (prop.original_text && text.includes(prop.original_text)) {
      text = text.replace(prop.original_text, replacement);
    } else {
      text = `${text}\n\n[${prop.adaptation_type}] ${replacement}`;
    }
  }

  return text;
}

function paginateText(content: string, charsPerPage = 1100): string[] {
  const normalized = content.trim() || 'Sin contenido disponible.';
  if (normalized.length <= charsPerPage) return [normalized];

  const paragraphs = normalized.split(/\n\s*\n/);
  const pages: string[] = [];
  let current = '';

  for (const para of paragraphs) {
    const candidate = current ? `${current}\n\n${para}` : para;
    if (candidate.length > charsPerPage && current) {
      pages.push(current);
      current = para;
    } else {
      current = candidate;
    }
  }
  if (current) pages.push(current);
  return pages.length > 0 ? pages : [normalized];
}

export function AdaptedVersionView({
  analysis,
  proposalsByBarrier = {},
  originalSourceText,
  onBackToAnalysis,
}: AdaptedVersionViewProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('adapted');
  const [adaptedDoc, setAdaptedDoc] = useState<AdaptedDocumentResponse | null>(null);
  const [loadingDoc, setLoadingDoc] = useState<boolean>(false);
  const [downloading, setDownloading] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [showThumbnails, setShowThumbnails] = useState<boolean>(true);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [zoom, setZoom] = useState<number>(100);
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    if (!analysis.analysis_id) return;
    let cancelled = false;
    setLoadingDoc(true);

    getAdaptedDocument(analysis.analysis_id)
      .then((doc) => {
        if (!cancelled) setAdaptedDoc(doc);
      })
      .catch(() => {
        // Si aún no hay versión armada en el backend, se usa el respaldo con propuestas aceptadas/editadas
      })
      .finally(() => {
        if (!cancelled) setLoadingDoc(false);
      });

    return () => {
      cancelled = true;
    };
  }, [analysis.analysis_id]);

  const fallbackOriginal = useMemo(() => {
    if (originalSourceText?.trim()) return originalSourceText.trim();
    return buildFallbackOriginalText(analysis);
  }, [originalSourceText, analysis]);

  const originalText = useMemo(() => {
    const fromBackend = adaptedDoc?.original_text?.trim();
    if (fromBackend && fromBackend !== adaptedDoc?.adapted_text?.trim()) {
      return fromBackend;
    }
    return fallbackOriginal;
  }, [adaptedDoc, fallbackOriginal]);

  const adaptedText = useMemo(() => {
    const fromBackend = adaptedDoc?.adapted_text?.trim();
    if (fromBackend) return fromBackend;
    return buildFallbackAdaptedText(fallbackOriginal, proposalsByBarrier);
  }, [adaptedDoc, fallbackOriginal, proposalsByBarrier]);

  const activeText = viewMode === 'adapted' ? adaptedText : originalText;

  const pages = useMemo(() => paginateText(activeText), [activeText]);
  const totalPages = Math.max(1, pages.length);

  useEffect(() => {
    setCurrentPage(1);
  }, [viewMode, pages.length]);

  const safePageIndex = Math.min(Math.max(currentPage - 1, 0), totalPages - 1);
  const currentPageContent = pages[safePageIndex] ?? '';

  const filename =
    analysis.metadata?.filename ||
    (analysis.metadata?.source_type === 'text'
      ? 'Texto_analizado.txt'
      : `Documento_adaptado.${analysis.metadata?.source_type || 'txt'}`);

  async function handleDownload() {
    setDownloading(true);
    setActionMessage(null);
    try {
      if (analysis.analysis_id) {
        const res = await exportAdaptedContent(analysis.analysis_id, 'docx', 'link');
        if (res && 'download' in res && res.download?.url) {
          window.open(res.download.url, '_blank', 'noopener,noreferrer');
          return;
        }
      }
      const blob = new Blob([adaptedText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename.replace(/\.[^.]+$/, '') + '_adaptado.txt';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setActionMessage('No se pudo exportar desde el servidor; intentá de nuevo en unos instantes.');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="via-adapted-view" aria-label="Revisión de versión adaptada">
      <div className="via-adapted-header">
        <div className="via-adapted-doc-meta">
          <div className="via-adapted-doc-icon" aria-hidden="true">
            <FileText size={22} />
          </div>
          <div>
            <h2 className="via-adapted-doc-title">{filename}</h2>
            <p className="via-adapted-doc-subtitle">
              {(analysis.metadata?.source_type || 'DOCUMENTO').toUpperCase()}
              {analysis.metadata?.page_count
                ? ` · ${analysis.metadata.page_count} págs.`
                : ''}
              {adaptedDoc
                ? ` · ${adaptedDoc.applied_count} adaptaciones aplicadas`
                : ''}
            </p>
          </div>
        </div>

        <div className="via-adapted-header-actions">
          <button
            type="button"
            className="via-btn via-btn-outline"
            onClick={onBackToAnalysis}
          >
            <ArrowLeft size={16} />
            <span>Volver al análisis</span>
          </button>

          <button
            type="button"
            className="via-btn via-btn-primary"
            onClick={handleDownload}
            disabled={downloading}
          >
            <Download size={16} />
            <span>{downloading ? 'Descargando...' : 'Descargar contenido'}</span>
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="via-alert via-alert-danger" role="alert">
          <span>{actionMessage}</span>
        </div>
      )}

      <div className="via-mode-switch" role="tablist" aria-label="Tipo de versión a visualizar">
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'adapted'}
          className={`via-mode-tab ${viewMode === 'adapted' ? 'is-active' : ''}`}
          onClick={() => setViewMode('adapted')}
        >
          Adaptación
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'original'}
          className={`via-mode-tab ${viewMode === 'original' ? 'is-active' : ''}`}
          onClick={() => setViewMode('original')}
        >
          Original
        </button>
      </div>

      <div className="via-viewer-shell">
        <div className="via-viewer-toolbar">
          <button
            type="button"
            className="via-toolbar-btn"
            onClick={() => setShowThumbnails((prev) => !prev)}
            aria-label="Alternar miniaturas de páginas"
          >
            <PanelLeft size={16} />
          </button>

          <div className="via-viewer-pagination">
            <button
              type="button"
              className="via-toolbar-btn"
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              aria-label="Página anterior"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="via-page-indicator">
              <strong>{currentPage}</strong> de {totalPages}
            </span>
            <button
              type="button"
              className="via-toolbar-btn"
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              aria-label="Página siguiente"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <div className="via-viewer-zoom">
            <button
              type="button"
              className="via-toolbar-btn"
              onClick={() => setZoom((z) => Math.max(70, z - 10))}
              aria-label="Alejar"
            >
              <ZoomOut size={16} />
            </button>
            <span className="via-zoom-value">{zoom}%</span>
            <button
              type="button"
              className="via-toolbar-btn"
              onClick={() => setZoom((z) => Math.min(150, z + 10))}
              aria-label="Acercar"
            >
              <ZoomIn size={16} />
            </button>
            <button
              type="button"
              className="via-toolbar-btn via-fit-btn"
              onClick={() => setZoom(100)}
            >
              <Maximize2 size={14} />
              <span>Ajustar a la página</span>
            </button>
          </div>

          <div className="via-viewer-search">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar en el documento"
              aria-label="Buscar en el documento"
            />
          </div>
        </div>

        <div className="via-viewer-body">
          {showThumbnails && (
            <aside className="via-viewer-thumbnails" aria-label="Miniaturas de páginas">
              {pages.map((pageText, idx) => {
                const pageNum = idx + 1;
                const isSelected = pageNum === currentPage;
                return (
                  <button
                    key={pageNum}
                    type="button"
                    className={`via-thumbnail-item ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setCurrentPage(pageNum)}
                  >
                    <div className="via-thumbnail-preview">
                      {pageText.slice(0, 110)}...
                    </div>
                    <span className="via-thumbnail-label">{pageNum}</span>
                  </button>
                );
              })}
            </aside>
          )}

          <div className="via-viewer-canvas-wrap">
            {loadingDoc ? (
              <p className="via-viewer-loading">Cargando versión adaptada...</p>
            ) : (
              <article
                className="via-viewer-page"
                style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}
              >
                <div className="via-viewer-page-mode-banner">
                  {viewMode === 'adapted'
                    ? `Versión adaptada (${adaptedText.length} caracteres)`
                    : `Versión original (${originalText.length} caracteres)`}
                </div>
                <p className="via-viewer-page-text" style={{ whiteSpace: 'pre-line' }}>
                  {currentPageContent}
                </p>
              </article>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}