import { useState, useRef } from 'react';
import {
  Sparkles,
  FileUp,
  Upload,
  BookOpen,
  ListTree,
  Eye,
  CheckCircle2,
  FileText,
  FileSpreadsheet,
  Presentation,
  Trash2,
  RefreshCw,
  ArrowRight,
  Wand2,
} from 'lucide-react';
import {
  ACCEPT_ATTRIBUTE,
  MAX_TEXT_CHARS,
  MIN_TEXT_CHARS,
  formatBytes,
  validateFile,
  validateText,
  type SupportedExtension,
} from '../utils/fileValidation';

export type UploadAnalysisStep =
  | 'requesting_url'
  | 'uploading'
  | 'completing'
  | 'analyzing';

export interface UploadAnalysisProgress {
  step: UploadAnalysisStep;
  percent?: number;
}

export interface FileUploaderProps {
  onAnalyzeFile: (file: File, useMock: boolean) => void;
  onAnalyzeText: (text: string, useMock: boolean) => void;
  onGoToTransform?: () => void;
  isLoading: boolean;
  progress?: UploadAnalysisProgress | null;
}

interface SelectedFileMeta {
  file: File;
  extension: SupportedExtension;
  label: string;
}

const STEP_LABELS: Record<UploadAnalysisStep, string> = {
  requesting_url: 'Solicitando enlace seguro de subida…',
  uploading: 'Subiendo documento de forma segura…',
  completing: 'Verificando integridad del archivo…',
  analyzing: 'Analizando accesibilidad del material…',
};

function renderFormatIcon(extension: SupportedExtension) {
  if (extension === '.pptx') {
    return <Presentation size={26} strokeWidth={2} />;
  }
  if (extension === '.docx') {
    return <FileSpreadsheet size={26} strokeWidth={2} />;
  }
  return <FileText size={26} strokeWidth={2} />;
}

export function FileUploader({
  onAnalyzeFile,
  onAnalyzeText,
  onGoToTransform,
  isLoading,
  progress = null,
}: FileUploaderProps) {
  const [tab, setTab] = useState<'file' | 'text'>('file');
  const [selected, setSelected] = useState<SelectedFileMeta | null>(null);
  const [text, setText] = useState<string>('');
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef<number>(0);

  function applyCandidateFile(candidate: File) {
    const check = validateFile(candidate);
    if (!check.ok) {
      setSelected(null);
      setValidationError(check.message);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    setSelected({
      file: candidate,
      extension: check.extension,
      label: check.label,
    });
    setValidationError(null);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0];
    if (chosen) {
      applyCandidateFile(chosen);
    }
  }

  function handleRemoveFile() {
    setSelected(null);
    setValidationError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function handleOpenFileDialog() {
    if (!isLoading) {
      fileInputRef.current?.click();
    }
  }

  function handleDragEnter(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (isLoading) return;
    dragDepthRef.current += 1;
    if (!isDragging) {
      setIsDragging(true);
    }
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (!isLoading && !isDragging) {
      setIsDragging(true);
    }
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragging(false);
    if (isLoading) return;

    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles && droppedFiles.length > 0) {
      setTab('file');
      applyCandidateFile(droppedFiles[0]);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isLoading) return;
    setValidationError(null);

    if (tab === 'file') {
      if (!selected) {
        setValidationError(
          'Seleccioná o arrastrá un archivo PDF, Word (.docx) o PowerPoint (.pptx) para analizar.',
        );
        return;
      }
      const check = validateFile(selected.file);
      if (!check.ok) {
        setValidationError(check.message);
        return;
      }
      onAnalyzeFile(selected.file, false);
    } else {
      const textError = validateText(text);
      if (textError) {
        setValidationError(textError);
        return;
      }
      onAnalyzeText(text, false);
    }
  }

  const trimmedLength = text.trim().length;
  const isTextCountInvalid =
    text.length > 0 && (trimmedLength < MIN_TEXT_CHARS || text.length > MAX_TEXT_CHARS);
  const canSubmit =
    tab === 'file' ? Boolean(selected) : trimmedLength >= MIN_TEXT_CHARS;

  const progressLabel = progress
    ? progress.step === 'uploading' && typeof progress.percent === 'number'
      ? `${STEP_LABELS.uploading} ${progress.percent}%`
      : STEP_LABELS[progress.step]
    : 'Analizando material…';

  return (
    <div className="via-upload-view">
      <div className="via-page-heading">
        <h1 className="via-page-title">¿Listo para escanear?</h1>
        <p className="via-page-subtitle">
          Adaptá tu contenido educativo para que sea más accesible.
        </p>
      </div>

      <div className="via-welcome-card" role="region" aria-label="Bienvenida">
        <div className="via-welcome-icon" aria-hidden="true">
          <Sparkles size={20} />
        </div>
        <div className="via-welcome-text">
          <h2 className="via-welcome-title">
            Te damos la bienvenida al análisis integral con escáner inteligente
          </h2>
          <p className="via-welcome-desc">
            Subí tu material y la herramienta te hará un escaneo inteligente. Te guiaremos paso a paso con recomendaciones claras para que sea fácil de entender, navegar y usar.
          </p>
        </div>
      </div>

      <div className="via-upload-toolbar">
        <div className="via-mode-tabs" role="tablist" aria-label="Modo de entrada">
          <button
            id="via-tab-file"
            type="button"
            role="tab"
            aria-selected={tab === 'file'}
            aria-controls="via-panel-input"
            className={`via-mode-tab ${tab === 'file' ? 'active' : ''}`}
            disabled={isLoading}
            onClick={() => {
              setTab('file');
              setValidationError(null);
            }}
          >
            <FileUp size={16} />
            <span>Subir documento</span>
          </button>
          <button
            id="via-tab-text"
            type="button"
            role="tab"
            aria-selected={tab === 'text'}
            aria-controls="via-panel-input"
            className={`via-mode-tab ${tab === 'text' ? 'active' : ''}`}
            disabled={isLoading}
            onClick={() => {
              setTab('text');
              setValidationError(null);
            }}
          >
            <FileText size={16} />
            <span>Pegar texto</span>
          </button>
        </div>

        {onGoToTransform && (
          <button
            type="button"
            className="via-btn via-btn-outline via-btn-sm"
            disabled={isLoading}
            onClick={onGoToTransform}
          >
            <Wand2 size={15} />
            <span>Ir a transformar material</span>
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <div
          id="via-panel-input"
          role="tabpanel"
          aria-labelledby={tab === 'file' ? 'via-tab-file' : 'via-tab-text'}
          className={`via-dropzone ${isDragging ? 'dragging' : ''} ${
            selected && tab === 'file' ? 'has-file' : ''
          }`}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_ATTRIBUTE}
            onChange={handleFileChange}
            disabled={isLoading}
            style={{ display: 'none' }}
            aria-label="Seleccionar archivo PDF, Word (.docx) o PowerPoint (.pptx)"
          />

          {tab === 'file' ? (
            !selected ? (
              <>
                <div className="via-dropzone-icon-box" aria-hidden="true">
                  <FileUp size={30} strokeWidth={2} />
                </div>

                <h3 className="via-dropzone-title">
                  Arrastrá y soltá tu archivo acá
                </h3>
                <p className="via-dropzone-subtitle">
                  También podés buscarlo en tu computadora.
                </p>

                <div className="via-dropzone-actions">
                  <button
                    type="button"
                    className="via-btn via-btn-primary"
                    disabled={isLoading}
                    onClick={handleOpenFileDialog}
                  >
                    <Upload size={16} />
                    <span>Seleccionar archivo</span>
                  </button>
                </div>

                <p className="via-dropzone-formats">
                  Formatos permitidos: PDF (.pdf), Word (.docx) y PowerPoint (.pptx) · Máximo 10 MB
                </p>
              </>
            ) : (
              <div className="via-selected-file-card" role="group" aria-label="Archivo seleccionado">
                <div className="via-selected-file-info">
                  <div className="via-selected-file-icon" aria-hidden="true">
                    {renderFormatIcon(selected.extension)}
                  </div>
                  <div className="via-selected-file-details">
                    <span className="via-selected-file-name" title={selected.file.name}>
                      {selected.file.name}
                    </span>
                    <div className="via-selected-file-meta">
                      <span className="via-selected-file-badge">{selected.label}</span>
                      <span>{formatBytes(selected.file.size)}</span>
                    </div>
                  </div>
                </div>

                <div className="via-selected-file-actions">
                  <button
                    type="button"
                    className="via-btn via-btn-outline via-btn-sm"
                    disabled={isLoading}
                    onClick={handleOpenFileDialog}
                  >
                    <RefreshCw size={15} />
                    <span>Cambiar archivo</span>
                  </button>
                  <button
                    type="button"
                    className="via-btn via-btn-outline-danger via-btn-sm"
                    disabled={isLoading}
                    onClick={handleRemoveFile}
                    aria-label={`Quitar archivo ${selected.file.name}`}
                  >
                    <Trash2 size={15} />
                    <span>Quitar</span>
                  </button>
                </div>
              </div>
            )
          ) : (
            <div className="via-text-input-container">
              <h3 className="via-dropzone-title">Pegá el texto a analizar</h3>
              <p className="via-dropzone-subtitle">
                Ingresá el fragmento o actividad educativa que querés evaluar (entre {MIN_TEXT_CHARS} y{' '}
                {MAX_TEXT_CHARS.toLocaleString('es-AR')} caracteres).
              </p>
              <textarea
                className="via-textarea"
                rows={6}
                placeholder="Ingresá o pegá el texto educativo acá..."
                value={text}
                disabled={isLoading}
                onChange={(e) => {
                  setText(e.target.value);
                  if (validationError) setValidationError(null);
                }}
              />
              <div className="via-text-counter-row">
                <span className={`via-text-counter ${isTextCountInvalid ? 'invalid' : ''}`}>
                  {text.length.toLocaleString('es-AR')} / {MAX_TEXT_CHARS.toLocaleString('es-AR')} caracteres
                </span>
              </div>
            </div>
          )}

          {validationError && (
            <p className="via-validation-error" role="alert">
              ⚠️ {validationError}
            </p>
          )}

          {isLoading && (
            <div className="via-upload-progress" role="status" aria-live="polite">
              <p className="via-upload-progress-label">{progressLabel}</p>
              {progress?.step === 'uploading' && typeof progress.percent === 'number' && (
                <progress
                  className="via-upload-progress-bar"
                  max={100}
                  value={progress.percent}
                  aria-label="Progreso de subida del archivo"
                />
              )}
            </div>
          )}

          {canSubmit && (
            <div className="via-submit-row">
              <button
                type="submit"
                className="via-btn via-btn-primary via-btn-lg"
                disabled={isLoading}
              >
                <span>{isLoading ? progressLabel : 'Iniciar análisis'}</span>
                {!isLoading && <ArrowRight size={16} />}
              </button>
            </div>
          )}
        </div>
      </form>

      <section className="via-dimensions-section" aria-labelledby="dimensions-heading">
        <h2 id="dimensions-heading" className="via-section-title">
          ¿Qué analiza la herramienta?
        </h2>
        <p className="via-section-subtitle">
          Revisamos tres dimensiones para detectar barreras y oportunidades de
          mejora.
        </p>

        <div className="via-dimensions-grid">
          <article className="via-dimension-card">
            <div className="via-dimension-icon" aria-hidden="true">
              <BookOpen size={20} />
            </div>
            <h3 className="via-dimension-name">Comprensión</h3>
            <p className="via-dimension-tags">
              Lenguaje · oraciones · consignas
            </p>
            <div className="via-dimension-status">
              <CheckCircle2 size={15} />
              <span>Incluida en el análisis</span>
            </div>
          </article>

          <article className="via-dimension-card">
            <div className="via-dimension-icon" aria-hidden="true">
              <ListTree size={20} />
            </div>
            <h3 className="via-dimension-name">Estructura</h3>
            <p className="via-dimension-tags">Títulos · secciones · orden</p>
            <div className="via-dimension-status">
              <CheckCircle2 size={15} />
              <span>Incluida en el análisis</span>
            </div>
          </article>

          <article className="via-dimension-card">
            <div className="via-dimension-icon" aria-hidden="true">
              <Eye size={20} />
            </div>
            <h3 className="via-dimension-name">Accesibilidad visual</h3>
            <p className="via-dimension-tags">
              Imágenes · contraste · legibilidad
            </p>
            <div className="via-dimension-status">
              <CheckCircle2 size={15} />
              <span>Incluida en el análisis</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}