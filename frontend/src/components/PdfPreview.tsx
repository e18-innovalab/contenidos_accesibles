import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, FileText } from 'lucide-react';

interface PdfPreviewProps {
  file: File | null;
  fallbackText: string;
  pageCount: number;
}

export function PdfPreview({ file, fallbackText, pageCount }: PdfPreviewProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const isPdf = Boolean(file && /\.pdf$/i.test(file.name));
  const totalPages = Math.max(1, pageCount || 1);

  useEffect(() => {
    setCurrentPage(1);
    if (!file || !/\.pdf$/i.test(file.name)) {
      setObjectUrl(null);
      return;
    }

    const url = URL.createObjectURL(file);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pageUrl = objectUrl
    ? `${objectUrl}#page=${currentPage}&toolbar=0&navpanes=0`
    : null;

  return (
    <section className="via-document-preview" aria-label="Previsualización del documento">
      <div className="via-document-preview-frame">
        {pageUrl ? (
          <iframe
            key={pageUrl}
            className="via-document-preview-iframe"
            src={pageUrl}
            title={`Vista previa del documento, página ${currentPage}`}
          />
        ) : fallbackText.trim() ? (
          <article className="via-document-preview-text">
            <div className="via-document-preview-paper">
              <p>{fallbackText}</p>
            </div>
          </article>
        ) : (
          <div className="via-document-preview-empty">
            <FileText size={30} aria-hidden="true" />
            <p>
              {file
                ? 'La vista previa está disponible para archivos PDF.'
                : 'No hay un documento disponible para previsualizar.'}
            </p>
          </div>
        )}
      </div>

      <div className="via-document-preview-controls">
        <button
          type="button"
          className="via-btn via-btn-primary via-btn-sm"
          onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
          disabled={!isPdf || currentPage <= 1}
          aria-label="Página anterior"
        >
          <ChevronLeft size={15} />
          <span>Página anterior</span>
        </button>
        {isPdf && (
          <span className="via-document-preview-page" aria-live="polite">
            Página {currentPage} de {totalPages}
          </span>
        )}
        <button
          type="button"
          className="via-btn via-btn-primary via-btn-sm"
          onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
          disabled={!isPdf || currentPage >= totalPages}
          aria-label="Página siguiente"
        >
          <span>Página siguiente</span>
          <ChevronRight size={15} />
        </button>
      </div>
    </section>
  );
}
