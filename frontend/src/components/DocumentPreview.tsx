import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, FileText } from 'lucide-react';
import {
  applyDocumentReplacements,
  extractDocumentText,
  paginateDocumentText,
  type DocumentReplacement,
} from '../utils/documentPreview';

interface DocumentPreviewProps {
  file: File | null;
  fallbackText: string;
  replacements: DocumentReplacement[];
}

export function DocumentPreview({
  file,
  fallbackText,
  replacements,
}: DocumentPreviewProps) {
  const [documentText, setDocumentText] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  useEffect(() => {
    let cancelled = false;
    setCurrentPage(1);

    if (!file) {
      setDocumentText(fallbackText);
      setLoadError(null);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setDocumentText('');
    setLoadError(null);
    setLoading(true);

    extractDocumentText(file)
      .then((text) => {
        if (!cancelled) setDocumentText(text);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(
            error instanceof Error
              ? error.message
              : 'No se pudo extraer el texto del documento para la vista previa.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [file, fallbackText]);

  const adaptedPreview = useMemo(
    () => applyDocumentReplacements(documentText, replacements),
    [documentText, replacements],
  );
  const pages = useMemo(
    () => paginateDocumentText(adaptedPreview.text),
    [adaptedPreview.text],
  );
  const totalPages = Math.max(1, pages.length);
  const safePage = Math.min(currentPage, totalPages);
  const currentPageText = pages[safePage - 1] ?? '';

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  return (
    <section className="via-document-preview" aria-label="Vista previa del documento adaptado">
      <div className="via-document-preview-frame">
        {loading ? (
          <div className="via-document-preview-empty" role="status" aria-live="polite">
            <p>Preparando vista previa del documento...</p>
          </div>
        ) : loadError ? (
          <div className="via-document-preview-empty" role="alert">
            <FileText size={30} aria-hidden="true" />
            <p>{loadError}</p>
          </div>
        ) : currentPageText ? (
          <article className="via-document-preview-paper">
            <div className="via-document-preview-page-label">
              Vista previa adaptada · borrador
            </div>
            <p>{currentPageText}</p>
          </article>
        ) : (
          <div className="via-document-preview-empty">
            <FileText size={30} aria-hidden="true" />
            <p>
              {file
                ? 'No se encontró texto seleccionable para mostrar. Los PDF escaneados requieren OCR.'
                : 'No hay contenido disponible para previsualizar.'}
            </p>
          </div>
        )}
      </div>

      <div className="via-document-preview-controls">
        <button
          type="button"
          className="via-btn via-btn-primary via-btn-sm"
          onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
          disabled={loading || safePage <= 1}
          aria-label="Página anterior"
        >
          <ChevronLeft size={15} />
          <span>Página anterior</span>
        </button>
        <span className="via-document-preview-page" aria-live="polite">
          Página {safePage} de {totalPages}
        </span>
        <button
          type="button"
          className="via-btn via-btn-primary via-btn-sm"
          onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
          disabled={loading || safePage >= totalPages}
          aria-label="Página siguiente"
        >
          <span>Página siguiente</span>
          <ChevronRight size={15} />
        </button>
      </div>

      {!loading && !loadError && adaptedPreview.unmatchedCount > 0 && (
        <p className="via-document-preview-notice" role="status">
          {adaptedPreview.unmatchedCount === 1
            ? 'No se pudo ubicar un cambio en el documento extraído.'
            : `No se pudieron ubicar ${adaptedPreview.unmatchedCount} cambios en el documento extraído.`}
        </p>
      )}
    </section>
  );
}
