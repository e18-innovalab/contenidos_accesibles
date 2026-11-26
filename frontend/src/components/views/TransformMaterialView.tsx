import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Camera,
  Check,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  GitBranch,
  Headphones,
  ImageOff,
  LayoutGrid,
  Loader2,
  MousePointerClick,
  RefreshCw,
  Share2,
  Sparkles,
  Upload,
  Volume2,
  X,
} from 'lucide-react';
import {
  ApiError,
  createTransformation,
  decideTransformation,
  exportTransformation,
  getDownloadUrl,
  getTransformation,
  retryTransformationFile,
  synthesizeTestAudio,
  uploadFile,
} from '../../services/api';
import type {
  GeneratedFileInfo,
  SensitiveFinding,
  TransformationDecisionType,
  TransformationFormat,
  TransformationResponse,
} from '../../types/analysis';

export interface TransformMaterialSource {
  fileId?: string | null;
  analysisId?: string | null;
  filename: string;
  isUploaded?: boolean;
}

export interface TransformMaterialViewProps {
  initialSource?: TransformMaterialSource | null;
  useMockByDefault?: boolean;
  onSourceChange?: (source: TransformMaterialSource | null) => void;
}

interface FormatCardItem {
  id: TransformationFormat;
  code: string;
  title: string;
  description: string;
  ctaLabel: string;
  Icon: React.ComponentType<{ size?: number }>;
}

const FORMAT_CARDS: FormatCardItem[] = [
  {
    id: 'infographic',
    code: '01',
    title: 'Transformar a infografía',
    description:
      'Convertí las ideas principales en una pieza visual clara, ordenada y fácil de recorrer.',
    ctaLabel: 'SÍNTESIS VISUAL',
    Icon: LayoutGrid,
  },
  {
    id: 'audio',
    code: '02',
    title: 'Transformar a audio',
    description:
      'Generá una narración del contenido con ritmo claro, pausas y lectura comprensible.',
    ctaLabel: 'ESCUCHA ACCESIBLE',
    Icon: Headphones,
  },
  {
    id: 'mind_map',
    code: '03',
    title: 'Crear mapa mental',
    description:
      'Organizá conceptos, relaciones y palabras clave para comprender la información de un vistazo.',
    ctaLabel: 'RELACIONES CLARAS',
    Icon: GitBranch,
  },
  {
    id: 'no_images',
    code: '04',
    title: 'Modo sin imágenes',
    description:
      'Creá una versión textual que reemplaza recursos visuales por descripciones equivalentes.',
    ctaLabel: 'CONTENIDO ALTERNATIVO',
    Icon: ImageOff,
  },
];

interface ParsedSectionItem {
  text: string;
  highlight?: string;
}

interface ParsedTransformationContent {
  title?: string;
  subtitle?: string;
  summary?: string;
  closing?: string;
  items: ParsedSectionItem[];
}

function cleanDots(value: string): string {
  return value
    .replace(/\.{3,}/g, ' · ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function flattenMindMapNode(node: unknown, prefix = ''): string[] {
  if (!node || typeof node !== 'object') return [];
  const rec = node as Record<string, unknown>;
  const rawText = typeof rec.text === 'string' ? cleanDots(rec.text) : '';
  const currentLabel = rawText
    ? prefix
      ? `${prefix} › ${rawText}`
      : rawText
    : prefix;
  const children = Array.isArray(rec.children) ? rec.children : [];

  if (children.length === 0) {
    return currentLabel ? [currentLabel] : [];
  }

  const lines: string[] = [];
  for (const child of children) {
    lines.push(...flattenMindMapNode(child, currentLabel));
  }
  return lines.length > 0 ? lines : currentLabel ? [currentLabel] : [];
}

function parseTransformationPayload(
  format: TransformationFormat,
  payload: Record<string, unknown> | null | undefined,
  views?: Record<string, string> | null,
): ParsedTransformationContent {
  if (!payload || typeof payload !== 'object') {
    const fallbackText = views?.markdown || views?.transcript;
    return {
      items: fallbackText ? [{ text: cleanDots(fallbackText) }] : [],
    };
  }

  if (format === 'mind_map') {
    const root =
      payload.root && typeof payload.root === 'object'
        ? (payload.root as Record<string, unknown>)
        : null;
    const rootTitle =
      root && typeof root.text === 'string' ? cleanDots(root.text) : undefined;
    const rootChildren =
      root && Array.isArray(root.children) ? root.children : [];
    const flat = rootChildren.flatMap((child) => flattenMindMapNode(child, ''));

    return {
      title: rootTitle,
      summary: rootTitle
        ? `Tema central: ${rootTitle}`
        : 'Estructura jerárquica de conceptos e ideas clave.',
      items: flat.map((text) => ({ text })),
    };
  }

  if (format === 'infographic') {
    const title =
      typeof payload.title === 'string' ? cleanDots(payload.title) : undefined;
    const subtitle =
      typeof payload.subtitle === 'string' && payload.subtitle.trim()
        ? cleanDots(payload.subtitle)
        : undefined;
    const closing =
      typeof payload.closing === 'string' && payload.closing.trim()
        ? cleanDots(payload.closing)
        : undefined;
    const rawSections = Array.isArray(payload.sections) ? payload.sections : [];

    const items: ParsedSectionItem[] = rawSections
      .map((sec) => {
        if (!sec || typeof sec !== 'object') {
          return { text: cleanDots(String(sec ?? '')) };
        }
        const s = sec as Record<string, unknown>;
        const secTitle =
          typeof s.title === 'string' ? cleanDots(s.title) : '';
        const secText = typeof s.text === 'string' ? cleanDots(s.text) : '';
        const highlight =
          typeof s.highlight === 'string' && s.highlight.trim()
            ? cleanDots(s.highlight)
            : undefined;

        const combined =
          secTitle && secText
            ? `${secTitle}: ${secText}`
            : `${secTitle}${secText}`.trim();

        return { text: combined, highlight };
      })
      .filter((entry) => Boolean(entry.text || entry.highlight));

    return {
      title,
      subtitle,
      closing,
      items,
    };
  }

  if (format === 'audio') {
    const title =
      typeof payload.title === 'string' ? cleanDots(payload.title) : undefined;
    const rawSections = Array.isArray(payload.sections) ? payload.sections : [];

    const items: ParsedSectionItem[] = rawSections
      .map((sec) => {
        if (!sec || typeof sec !== 'object') {
          return { text: cleanDots(String(sec ?? '')) };
        }
        const s = sec as Record<string, unknown>;
        const secTitle =
          typeof s.title === 'string' ? cleanDots(s.title) : '';
        const secText = typeof s.text === 'string' ? cleanDots(s.text) : '';
        const combined =
          secTitle && secText
            ? `${secTitle}: ${secText}`
            : `${secTitle}${secText}`.trim();

        return { text: combined };
      })
      .filter((entry) => Boolean(entry.text));

    return {
      title,
      summary: 'Guion narrado listo para revisar o convertir a audio.',
      items,
    };
  }

  // format === 'no_images'
  const mainText =
    typeof payload.text === 'string' ? cleanDots(payload.text) : undefined;
  const rawImages = Array.isArray(payload.images) ? payload.images : [];
  const colorNotes = Array.isArray(payload.color_notes)
    ? payload.color_notes.filter(
        (n): n is string => typeof n === 'string' && Boolean(n.trim()),
      )
    : [];

  const items: ParsedSectionItem[] = [];
  if (mainText) {
    items.push({ text: mainText });
  }

  for (const img of rawImages) {
    if (!img || typeof img !== 'object') continue;
    const im = img as Record<string, unknown>;
    const idx =
      typeof im.image_index === 'number' ? `Imagen ${im.image_index}` : 'Imagen';
    const role = im.role === 'decorativa' ? 'Decorativa' : 'Informativa';
    const loc =
      typeof im.location === 'string' && im.location.trim()
        ? ` (${cleanDots(im.location)})`
        : '';
    const desc =
      typeof im.description === 'string' && im.description.trim()
        ? cleanDots(im.description)
        : 'Sin descripción adicional.';
    items.push({ text: `${idx} [${role}]${loc}: ${desc}` });
  }

  for (const note of colorNotes) {
    items.push({ text: `Nota de color: ${cleanDots(note)}` });
  }

  return {
    summary: 'Versión textual con descripciones equivalentes de las imágenes.',
    items,
  };
}

function findMediaUrl(
  job: TransformationResponse,
  mediaKind: 'audio' | 'any',
): string | null {
  const candidates: Array<GeneratedFileInfo | null | undefined> = [
    job.file,
    ...(job.extra_files ?? []),
  ];

  for (const item of candidates) {
    if (!item?.preview_url) continue;
    if (mediaKind === 'audio') {
      if (
        item.content_type?.startsWith('audio/') ||
        /\.(mp3|wav|ogg|m4a|webm|zip)(\?|$)/i.test(item.preview_url)
      ) {
        return item.preview_url;
      }
    } else {
      return item.preview_url;
    }
  }

  if (job.views) {
    for (const val of Object.values(job.views)) {
      if (typeof val === 'string' && /^https?:\/\//i.test(val)) {
        if (
          mediaKind !== 'audio' ||
          /\.(mp3|wav|ogg|m4a|webm|zip)(\?|$)/i.test(val)
        ) {
          return val;
        }
      }
    }
  }

  return null;
}

export function TransformMaterialView({
  initialSource = null,
  useMockByDefault = true,
  onSourceChange,
}: TransformMaterialViewProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);

  const [source, setSource] = useState<TransformMaterialSource | null>(
    initialSource,
  );
  const [selectedFormat, setSelectedFormat] =
    useState<TransformationFormat | null>(null);

  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRetryingFile, setIsRetryingFile] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isSynthesizingAudio, setIsSynthesizingAudio] = useState(false);
  const [ttsAudioUrl, setTtsAudioUrl] = useState<string | null>(null);

  const [originalDownloadUrl, setOriginalDownloadUrl] = useState<string | null>(
    null,
  );
  const [isLoadingOriginalUrl, setIsLoadingOriginalUrl] = useState(false);

  const [job, setJob] = useState<TransformationResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [compareTab, setCompareTab] = useState<'original' | 'transformation'>(
    'transformation',
  );
  const [decisionStatus, setDecisionStatus] =
    useState<TransformationDecisionType | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);

  const [sensitiveAlertOpen, setSensitiveAlertOpen] = useState(false);
  const [sensitiveFindings, setSensitiveFindings] = useState<SensitiveFinding[]>(
    [],
  );
  const [dismissedIds, setDismissedIds] = useState<string[]>([]);

  useEffect(() => {
    if (initialSource) {
      setSource(initialSource);
    }
  }, [initialSource]);

  useEffect(() => {
    setOriginalDownloadUrl(null);
  }, [source?.fileId]);

  useEffect(() => {
    return () => {
      if (ttsAudioUrl) {
        URL.revokeObjectURL(ttsAudioUrl);
      }
    };
  }, [ttsAudioUrl]);

  useEffect(() => {
    if (!job) return;
    if (job.status !== 'pending' && job.status !== 'processing') return;

    const timer = window.setInterval(async () => {
      try {
        const updated = await getTransformation(job.transformation_id);
        setJob(updated);
        if (updated.status === 'failed' && updated.error?.message) {
          setErrorMessage(updated.error.message);
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setErrorMessage(err.message);
        }
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [job]);

  const clearGeneratedAudio = () => {
    if (ttsAudioUrl) {
      URL.revokeObjectURL(ttsAudioUrl);
      setTtsAudioUrl(null);
    }
  };

  const handleOpenOriginalFile = async () => {
    const fileId =
      source?.fileId || (job?.source?.type === 'file' ? job.source.id : null);
    if (!fileId) return;

    if (originalDownloadUrl) {
      window.open(originalDownloadUrl, '_blank', 'noopener,noreferrer');
      return;
    }

    setIsLoadingOriginalUrl(true);
    try {
      const res = await getDownloadUrl(fileId);
      const url = res?.download?.url;
      if (url) {
        setOriginalDownloadUrl(url);
        window.open(url, '_blank', 'noopener,noreferrer');
      } else {
        setFeedbackNotice('No se pudo obtener el enlace del archivo original.');
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFeedbackNotice(err.message);
      } else {
        setFeedbackNotice('No se pudo abrir el archivo original.');
      }
    } finally {
      setIsLoadingOriginalUrl(false);
    }
  };

  const processSelectedFile = async (file: File) => {
    setErrorMessage(null);
    setFeedbackNotice(null);
    setDecisionStatus(null);
    clearGeneratedAudio();
    setJob(null);
    setCompareTab('transformation');
    setIsUploadingFile(true);
    setUploadPercent(0);

    try {
      const uploaded = await uploadFile(file, {
        onProgress: (pct) => setUploadPercent(pct),
      });
      const nextSource: TransformMaterialSource = {
        fileId: uploaded.file_id,
        analysisId: null,
        filename: uploaded.filename || file.name,
        isUploaded: true,
      };
      setSource(nextSource);
      onSourceChange?.(nextSource);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('No se pudo cargar el archivo. Intentá nuevamente.');
      }
    } finally {
      setIsUploadingFile(false);
      setUploadPercent(null);
    }
  };

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await processSelectedFile(file);
  };

  const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    await processSelectedFile(file);
  };

  const startTransformation = async (dismissIdsOverride?: string[]) => {
    if (!selectedFormat) {
      setErrorMessage('Seleccioná un formato para continuar.');
      return;
    }

    if (!source?.fileId && !source?.analysisId) {
      setErrorMessage(
        'Primero cargá un archivo o seleccioná un análisis para transformar.',
      );
      return;
    }

    setErrorMessage(null);
    setFeedbackNotice(null);
    setDecisionStatus(null);
    clearGeneratedAudio();
    setJob(null);
    setCompareTab('transformation');
    setIsSubmitting(true);

    const activeDismissed = dismissIdsOverride ?? dismissedIds;

    try {
      const created = await createTransformation(
        {
          format: selectedFormat,
          file_id: source.analysisId ? null : source.fileId,
          analysis_id: source.analysisId ?? null,
        },
        {
          mock: useMockByDefault,
          dismissed: activeDismissed.length > 0 ? activeDismissed : undefined,
        },
      );
      setJob(created);
      setSensitiveAlertOpen(false);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.findings && err.findings.length > 0) {
          setSensitiveFindings(err.findings);
          setSensitiveAlertOpen(true);
        } else if (
          err.code === 'sensitive_data_detected' ||
          err.message.toLowerCase().includes('datos personales') ||
          err.message.toLowerCase().includes('sensible')
        ) {
          setSensitiveAlertOpen(true);
        }
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Ocurrió un error al iniciar la transformación.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDismissFindingsAndRetry = async () => {
    const nextDismissed = Array.from(
      new Set([
        ...dismissedIds,
        ...sensitiveFindings.map((finding) => finding.id),
      ]),
    );
    setDismissedIds(nextDismissed);
    setSensitiveAlertOpen(false);
    await startTransformation(nextDismissed);
  };

  const handleSaveDecision = async () => {
    if (!job) return;
    try {
      const updated = await decideTransformation(job.transformation_id, {
        decision: 'aceptada',
      });
      if (updated) {
        setJob(updated);
      }
      setDecisionStatus('aceptada');
      setFeedbackNotice('Transformación guardada correctamente.');
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('No se pudo guardar la transformación.');
      }
    }
  };

  const handleRetryFile = async () => {
    if (!job) return;
    setIsRetryingFile(true);
    setFeedbackNotice(null);
    try {
      const updated = await retryTransformationFile(job.transformation_id);
      setJob(updated);
      setFeedbackNotice('Se actualizó el estado del archivo de la transformación.');
    } catch (err) {
      if (err instanceof ApiError) {
        setFeedbackNotice(err.message);
      } else {
        setFeedbackNotice('No se pudo generar o reintentar el archivo.');
      }
    } finally {
      setIsRetryingFile(false);
    }
  };

  const handleSynthesizeAudio = async (scriptText: string) => {
    setIsSynthesizingAudio(true);
    setFeedbackNotice(null);
    try {
      const result = await synthesizeTestAudio(scriptText, {
        mock: useMockByDefault,
      });
      clearGeneratedAudio();
      setTtsAudioUrl(result.audioUrl);
      setFeedbackNotice('Audio generado listo para reproducir.');
    } catch (err) {
      if (err instanceof ApiError) {
        setFeedbackNotice(err.message);
      } else {
        setFeedbackNotice('No se pudo generar el audio en este momento.');
      }
    } finally {
      setIsSynthesizingAudio(false);
    }
  };

  const handleExportLink = async (mode: 'download' | 'share') => {
    if (!job) return;
    const directUrl =
      job.format === 'audio'
        ? findMediaUrl(job, 'audio') || ttsAudioUrl || findMediaUrl(job, 'any')
        : findMediaUrl(job, 'any');

    if (directUrl) {
      if (mode === 'share' && navigator.clipboard) {
        await navigator.clipboard.writeText(directUrl);
        setFeedbackNotice('Enlace copiado al portapapeles.');
      } else {
        window.open(directUrl, '_blank', 'noopener,noreferrer');
      }
      return;
    }

    setIsExporting(true);
    try {
      const targetFormat = job.format === 'audio' ? 'mp3' : 'txt';
      const exported = await exportTransformation(
        job.transformation_id,
        targetFormat,
        'link',
      );
      const url = exported?.download?.url;
      if (url) {
        if (mode === 'share' && navigator.clipboard) {
          await navigator.clipboard.writeText(url);
          setFeedbackNotice('Enlace de exportación copiado al portapapeles.');
        } else {
          window.open(url, '_blank', 'noopener,noreferrer');
        }
      } else {
        setFeedbackNotice(
          mode === 'share'
            ? 'Resultado listo para revisar.'
            : 'Este formato no devolvió un archivo descargable todavía.',
        );
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFeedbackNotice(err.message);
      } else {
        setFeedbackNotice(
          mode === 'share'
            ? 'Resultado listo para revisar.'
            : 'No se pudo exportar el resultado.',
        );
      }
    } finally {
      setIsExporting(false);
    }
  };

  const handleBackToFormats = () => {
    clearGeneratedAudio();
    setJob(null);
    setErrorMessage(null);
    setFeedbackNotice(null);
    setDecisionStatus(null);
  };

  const hasFile = Boolean(source?.filename);
  const hasFormat = Boolean(selectedFormat);
  const isProcessingJob =
    isSubmitting || job?.status === 'pending' || job?.status === 'processing';
  const isReadyWithResult = Boolean(job && job.status === 'ready');

  const isStep2Locked = !hasFile;
  const isStep3Locked = !hasFile || !selectedFormat;

  const step1Done = hasFile;
  const step2Done = hasFile && hasFormat;
  const step2Active = hasFile && !hasFormat && !isReadyWithResult;
  const step3Active =
    (hasFile && hasFormat && !isReadyWithResult) || isProcessingJob;

  const selectedCard = FORMAT_CARDS.find((card) => card.id === selectedFormat);
  const SelectedIcon = selectedCard?.Icon;

  if (isReadyWithResult && job) {
    const audioUrl = findMediaUrl(job, 'audio') || ttsAudioUrl;
    const anyUrl = findMediaUrl(job, 'any');
    const payload = job.final_result ?? job.edited_result ?? job.result;
    const parsed = parseTransformationPayload(job.format, payload, job.views);
    const displayTitle =
      parsed.title ||
      source?.filename?.replace(/\.[^/.]+$/, '') ||
      selectedCard?.title ||
      job.format;

    const ttsScriptText =
      [parsed.summary, ...parsed.items.map((i) => i.text)]
        .filter(Boolean)
        .join('. ') || `Resumen del material ${displayTitle}`;

    const canOpenOriginal = Boolean(
      source?.fileId || job.source?.type === 'file',
    );

    return (
      <div className="via-transform-view">
        <div className="via-result-topbar">
          <button
            type="button"
            className="via-link-btn"
            onClick={handleBackToFormats}
          >
            <ArrowLeft size={16} />
            <span>Volver a elegir formato</span>
          </button>

          <div className="via-result-actions">
            <button
              type="button"
              className="via-btn via-btn-outline"
              onClick={() => void handleSaveDecision()}
            >
              <Bookmark size={15} />
              <span>
                {decisionStatus === 'aceptada' ||
                job.review_status === 'aceptada'
                  ? 'Guardado'
                  : 'Guardar'}
              </span>
            </button>

            <button
              type="button"
              className="via-btn via-btn-primary"
              disabled={isExporting}
              onClick={() => void handleExportLink('download')}
            >
              <Download size={15} />
              <span>{isExporting ? 'Exportando...' : 'Descargar'}</span>
            </button>

            <button
              type="button"
              className="via-btn via-btn-accent"
              disabled={isExporting}
              onClick={() => void handleExportLink('share')}
            >
              <Share2 size={15} />
              <span>Compartir</span>
            </button>
          </div>
        </div>

        <section className="via-result-header-block">
          <span className="via-eyebrow">RESULTADO GENERADO</span>
          <h1 className="via-page-title">
            Compará el original y la transformación
          </h1>
          <p className="via-page-subtitle">
            Revisá ambas versiones antes de guardar o descargar el resultado.
          </p>

          <div className="via-compare-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={compareTab === 'original'}
              className={`via-compare-tab ${
                compareTab === 'original' ? 'is-active' : ''
              }`}
              onClick={() => setCompareTab('original')}
            >
              <FileText size={15} />
              <span>Original</span>
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={compareTab === 'transformation'}
              className={`via-compare-tab ${
                compareTab === 'transformation' ? 'is-active' : ''
              }`}
              onClick={() => setCompareTab('transformation')}
            >
              {SelectedIcon && <SelectedIcon size={15} />}
              <span>Transformación</span>
            </button>
          </div>
        </section>

        {feedbackNotice && (
          <div className="via-notice-banner" role="status">
            {feedbackNotice}
          </div>
        )}

        <section className="via-result-card">
          <div className="via-result-card-top">
            <div>
              <span className="via-result-kicker">
                {compareTab === 'original'
                  ? 'MATERIAL ORIGINAL'
                  : 'RESULTADO TRANSFORMADO'}
              </span>
              <h2 className="via-result-card-title">
                {compareTab === 'original'
                  ? source?.filename || 'Documento original'
                  : selectedCard?.title || job.format}
              </h2>
            </div>

            <span className="via-badge-ready">
              <CheckCircle2 size={14} />
              <span>LISTO</span>
            </span>
          </div>

          {compareTab === 'original' ? (
            <div className="via-original-preview">
              <p>
                Archivo base: <strong>{source?.filename}</strong>
              </p>
              <p>
                Origen:{' '}
                <strong>
                  {job.source?.type === 'analysis'
                    ? 'Diagnóstico previo'
                    : 'Archivo subido'}
                </strong>
              </p>
              {canOpenOriginal && (
                <div className="via-alert-actions">
                  <button
                    type="button"
                    className="via-btn via-btn-outline"
                    disabled={isLoadingOriginalUrl}
                    onClick={() => void handleOpenOriginalFile()}
                  >
                    <ExternalLink size={14} />
                    <span>
                      {isLoadingOriginalUrl
                        ? 'Obteniendo enlace...'
                        : 'Ver / descargar archivo original'}
                    </span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className={`via-showcase is-${job.format}`}>
              <div className="via-showcase-hero">
                <div className="via-showcase-icon" aria-hidden="true">
                  {SelectedIcon && <SelectedIcon size={20} />}
                </div>

                <div className="via-showcase-kicker">
                  {job.format === 'audio' && 'VERSIÓN NARRADA'}
                  {job.format === 'infographic' && 'SÍNTESIS VISUAL'}
                  {job.format === 'mind_map' && 'MAPA DE CONCEPTOS'}
                  {job.format === 'no_images' && 'VERSIÓN TEXTUAL ACCESIBLE'}
                </div>

                <h3 className="via-showcase-title">{displayTitle}</h3>
                <p className="via-showcase-sub">
                  {parsed.subtitle ||
                    parsed.summary ||
                    selectedCard?.description ||
                    'Material adaptado listo para revisar.'}
                </p>

                <div className="via-showcase-surface">
                  {job.format === 'audio' && audioUrl && (
                    <div className="via-audio-box">
                      <div className="via-audio-meta">
                        <strong>{source?.filename || displayTitle}</strong>
                        <span>Narración accesible</span>
                      </div>
                      <audio
                        controls
                        src={audioUrl}
                        className="via-audio-player"
                      />
                    </div>
                  )}

                  {job.format === 'audio' && !audioUrl && (
                    <div className="via-audio-box">
                      <div className="via-audio-meta">
                        <strong>{source?.filename || displayTitle}</strong>
                        <span>Guion listo — audio pendiente o bajo demanda</span>
                      </div>
                      <p className="via-empty-result-note">
                        El backend devuelve primero el guion revisable. Podés
                        sintetizar un audio de prueba con TTS o reintentar el
                        archivo asociado.
                      </p>
                      <div className="via-alert-actions">
                        <button
                          type="button"
                          className="via-btn via-btn-primary"
                          disabled={isSynthesizingAudio}
                          onClick={() =>
                            void handleSynthesizeAudio(ttsScriptText)
                          }
                        >
                          <Volume2
                            size={14}
                            className={isSynthesizingAudio ? 'via-spin' : ''}
                          />
                          <span>
                            {isSynthesizingAudio
                              ? 'Generando audio...'
                              : 'Generar audio con TTS'}
                          </span>
                        </button>

                        <button
                          type="button"
                          className="via-btn via-btn-outline"
                          disabled={isRetryingFile}
                          onClick={() => void handleRetryFile()}
                        >
                          <RefreshCw
                            size={14}
                            className={isRetryingFile ? 'via-spin' : ''}
                          />
                          <span>
                            {isRetryingFile
                              ? 'Solicitando archivo...'
                              : 'Reintentar archivo'}
                          </span>
                        </button>
                      </div>
                    </div>
                  )}

                  {job.format !== 'audio' && anyUrl && (
                    <div className="via-preview-link-box">
                      <p>Vista previa disponible para este material.</p>
                      <a
                        href={anyUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="via-btn via-btn-outline"
                      >
                        Abrir vista previa
                      </a>
                    </div>
                  )}

                  {parsed.items.length > 0 && (
                    <div className="via-showcase-items">
                      {parsed.items.map((entry, idx) => (
                        <div
                          key={`${idx}-${entry.text.slice(0, 16)}`}
                          className="via-showcase-item"
                        >
                          <span className="via-showcase-item-num">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <p>
                            {entry.text}
                            {entry.highlight && (
                              <span className="via-showcase-highlight">
                                {entry.highlight}
                              </span>
                            )}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}

                  {parsed.closing && (
                    <p className="via-showcase-closing">{parsed.closing}</p>
                  )}

                  {job.format !== 'audio' &&
                    !anyUrl &&
                    parsed.items.length === 0 &&
                    !parsed.summary && (
                      <p className="via-empty-result-note">
                        La transformación finalizó correctamente.
                      </p>
                    )}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="via-transform-view">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.pptx,.txt,.md"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      {sensitiveAlertOpen && (
        <div className="via-alert-banner" role="alert">
          <div className="via-alert-content">
            <AlertTriangle size={18} />
            <div>
              <strong>Se detectaron datos personales</strong>
              <p>
                Por favor, revise el documento ya que detectamos datos
                personales. ¡Cuide de cargar información sensible de sus
                alumnos!
              </p>
              {sensitiveFindings.length > 0 && (
                <div className="via-alert-actions">
                  <button
                    type="button"
                    className="via-btn via-btn-secondary"
                    onClick={handleDismissFindingsAndRetry}
                  >
                    Marcar hallazgos como no sensibles y reintentar
                  </button>
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            className="via-icon-btn"
            aria-label="Cerrar aviso"
            onClick={() => setSensitiveAlertOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      <section className="via-hero-banner">
        <div>
          <span className="via-eyebrow">NUEVOS FORMATOS</span>
          <h1 className="via-page-title">Transformá tu material</h1>
          <p className="via-page-subtitle">
            Elegí una forma de adaptar el contenido según las necesidades de tus
            estudiantes. Podrás revisar el resultado antes de guardarlo.
          </p>
        </div>
        <div className="via-hero-badge" aria-hidden="true">
          <Sparkles size={22} />
        </div>
      </section>

      <nav className="via-stepper" aria-label="Pasos de transformación">
        <div
          className={`via-step ${step1Done ? 'is-completed' : 'is-current'}`}
        >
          <span className="via-step-index">
            {step1Done ? <Check size={14} /> : '1'}
          </span>
          <span>Cargar archivo</span>
        </div>

        <div
          className={`via-step ${
            step2Done
              ? 'is-completed'
              : step2Active
                ? 'is-current'
                : isStep2Locked
                  ? 'is-locked'
                  : ''
          }`}
        >
          <span className="via-step-index">
            {step2Done ? <Check size={14} /> : '2'}
          </span>
          <span>Seleccionar formato</span>
        </div>

        <div
          className={`via-step ${
            step3Active ? 'is-current' : isStep3Locked ? 'is-locked' : ''
          }`}
        >
          <span className="via-step-index">3</span>
          <span>Comenzar transformación</span>
        </div>
      </nav>

      <section className="via-step-block">
        <div className="via-step-header">
          <span className="via-step-tag">PASO 1</span>
          <h2>Cargá el archivo que querés transformar</h2>
          <p>
            Podés usar el mismo material que analizaste en el análisis integral.
          </p>
        </div>

        {hasFile ? (
          <div className="via-loaded-file-card">
            <div className="via-loaded-file-meta">
              <div className="via-file-icon-box" aria-hidden="true">
                <FileText size={20} />
              </div>
              <div>
                <div className="via-file-name">{source?.filename}</div>
                <div className="via-file-status is-ok">
                  <CheckCircle2 size={14} />
                  <span>
                    {isUploadingFile
                      ? `Subiendo archivo... ${uploadPercent ?? 0}%`
                      : 'Archivo cargado correctamente'}
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              className="via-btn via-btn-outline"
              disabled={isUploadingFile || isProcessingJob}
              onClick={() => fileInputRef.current?.click()}
            >
              <RefreshCw size={15} />
              <span>Cambiar archivo</span>
            </button>
          </div>
        ) : (
          <div
            className={`via-dropzone-card ${isDragging ? 'is-dragging' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => void handleDrop(e)}
          >
            <div className="via-dropzone-icon" aria-hidden="true">
              <Upload size={22} />
            </div>
            <div className="via-dropzone-title">
              Arrastrá y soltá tu archivo acá
            </div>
            <p className="via-dropzone-sub">
              También podés buscarlo en tu computadora o sacarle una foto.
            </p>

            <div className="via-dropzone-actions">
              <button
                type="button"
                className="via-btn via-btn-primary"
                disabled={isUploadingFile}
                onClick={() => fileInputRef.current?.click()}
              >
                <span>
                  {isUploadingFile
                    ? `Subiendo... ${uploadPercent ?? 0}%`
                    : '+ Seleccionar archivo'}
                </span>
              </button>

              <button
                type="button"
                className="via-btn via-btn-accent"
                disabled={isUploadingFile}
                onClick={() => cameraInputRef.current?.click()}
              >
                <Camera size={16} />
                <span>Sacar foto</span>
              </button>
            </div>

            <span className="via-dropzone-hint">
              Formatos permitidos: PDF, DOC, DOCX, PPT y PPTX
            </span>
          </div>
        )}
      </section>

      <section
        className={`via-step-block ${isStep2Locked ? 'is-locked' : 'is-unlocked'}`}
      >
        <div className="via-step-header-row">
          <div>
            <span className="via-step-tag">PASO 2</span>
            <h2>¿Cómo querés transformar el material?</h2>
            <p>
              {hasFile
                ? 'Seleccioná una opción para continuar:'
                : 'Bloqueado: cargá un archivo en el Paso 1 para habilitar los formatos.'}
            </p>
          </div>
          <span className="via-pill">4 formatos disponibles</span>
        </div>

        <div className="via-format-grid">
          {FORMAT_CARDS.map((card) => {
            const Icon = card.Icon;
            const isSelected = selectedFormat === card.id;

            return (
              <button
                key={card.id}
                type="button"
                disabled={isStep2Locked || isProcessingJob}
                aria-disabled={isStep2Locked}
                className={`via-format-card ${
                  isSelected ? 'is-selected' : ''
                } ${isStep2Locked ? 'is-locked' : 'is-unlocked'}`}
                aria-pressed={isSelected}
                onClick={() => {
                  if (isStep2Locked) return;
                  setSelectedFormat(card.id);
                  setErrorMessage(null);
                }}
              >
                <div className="via-format-card-top">
                  <span className="via-format-icon" aria-hidden="true">
                    <Icon size={20} />
                  </span>

                  {isSelected ? (
                    <span className="via-format-check" aria-hidden="true">
                      <Check size={14} />
                    </span>
                  ) : (
                    <span className="via-format-code">{card.code}</span>
                  )}
                </div>

                <h3 className="via-format-title">{card.title}</h3>
                <p className="via-format-desc">{card.description}</p>

                <span className="via-format-cta">
                  <span>{card.ctaLabel}</span>
                  <ArrowRight size={14} />
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {errorMessage && (
        <div className="via-error-box" role="alert">
          {errorMessage}
        </div>
      )}

      {job && job.status !== 'ready' && (
        <section className="via-job-status-card" aria-live="polite">
          <div className="via-job-status-header">
            <div className="via-job-status-title">
              <Loader2 size={18} className="via-spin" />
              <div>
                <strong>
                  {job.status === 'pending'
                    ? 'Preparando transformación'
                    : job.status === 'processing'
                      ? 'Generando material'
                      : 'Error en la transformación'}
                  {selectedCard ? ` — ${selectedCard.title}` : ''}
                </strong>
                <p className="via-job-status-sub">
                  {job.status === 'pending'
                    ? 'Tu solicitud está en cola y comenzará en unos segundos.'
                    : job.status === 'processing'
                      ? 'Estamos adaptando el contenido según el formato elegido.'
                      : 'No se pudo completar el proceso con este archivo.'}
                </p>
              </div>
            </div>

            {job.progress && job.progress.total > 0 && (
              <span className="via-pill">
                {job.progress.done} / {job.progress.total}
              </span>
            )}
          </div>
        </section>
      )}

      <div
        className={`via-bottom-bar ${isStep3Locked ? 'is-locked' : 'is-unlocked'}`}
      >
        <div className="via-bottom-info">
          <div className="via-bottom-leading">
            <span className="via-bottom-status-icon" aria-hidden="true">
              {selectedCard && SelectedIcon ? (
                <SelectedIcon size={18} />
              ) : (
                <MousePointerClick size={18} />
              )}
            </span>
            <div>
              <div className="via-bottom-label">
                {!hasFile
                  ? 'Cargá un archivo para comenzar'
                  : !selectedCard
                    ? 'Seleccioná un formato'
                    : selectedCard.title}
              </div>
              <div className="via-bottom-sub">
                {!hasFile
                  ? 'Bloqueado: completá la carga y elegí un formato para habilitar.'
                  : !selectedCard
                    ? 'Bloqueado: elegí una de las cuatro opciones para habilitar.'
                    : `${source?.filename} está listo para transformar.`}
              </div>
            </div>
          </div>
        </div>

        <button
          type="button"
          className="via-btn via-btn-primary"
          disabled={isStep3Locked || isProcessingJob}
          onClick={() => void startTransformation()}
        >
          {isProcessingJob ? (
            <>
              <Loader2 size={16} className="via-spin" />
              <span>Transformando...</span>
            </>
          ) : (
            <>
              <span>Comenzar transformación</span>
              <ArrowRight size={16} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}