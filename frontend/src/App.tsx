import { useState, useEffect, useRef } from 'react';
import { RotateCcw } from 'lucide-react';
import {
  FileUploader,
  type UploadAnalysisProgress,
} from './components/FileUploader';
import { AnalysisResults } from './components/AnalysisResults';
import { AppLayout } from './components/layout/AppLayout';
import type { NavSectionId } from './components/layout/Sidebar';
import type { AnalysisStage } from './components/layout/Topbar';
import { SectionPlaceholder } from './components/views/SectionPlaceholders';
import { HomeView } from './components/HomeView';
// 1. IMPORTAR TU VISTA DE LOGIN NUEVA
import { LoginView } from './components/views/LoginView'; 
import {
  analyzeFileById,
  analyzeSample,
  uploadFile,
} from './services/api';
import type { AccessibilityAnalysisResponse } from './types/analysis';
import { getFileCacheKey } from './utils/fileValidation';

const VALID_SECTIONS: NavSectionId[] = [
  'inicio',
  'analisis',
  'transformar',
  'materiales',
  'configuracion',
];

function getSectionFromHash(): NavSectionId {
  const raw = window.location.hash.replace(/^#\/?/, '').split('/')[0];
  return VALID_SECTIONS.includes(raw as NavSectionId)
    ? (raw as NavSectionId)
    : 'inicio';
}

interface UploadedFileCache {
  key: string;
  fileId: string;
  expiresAt: string;
}

export function App() {
  // 2. ESTADO DE AUTENTICACIÓN (Ponelo en true si querés saltarte el login temporalmente mientras probás)
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  const [activeSection, setActiveSection] = useState<NavSectionId>(getSectionFromHash);
  const [currentStage, setCurrentStage] = useState<AnalysisStage>('upload');
  const [loading, setLoading] = useState<boolean>(false);
  const [progress, setProgress] = useState<UploadAnalysisProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<AccessibilityAnalysisResponse | null>(null);

  const uploadedCacheRef = useRef<UploadedFileCache | null>(null);

  useEffect(() => {
    const onHashChange = () => setActiveSection(getSectionFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  function handleSelectSection(section: NavSectionId) {
    setActiveSection(section);
    window.location.hash = `#/${section}`;
  }

  async function ensureFileUploaded(file: File): Promise<string> {
    const cacheKey = getFileCacheKey(file);
    const cached = uploadedCacheRef.current;
    if (
      cached &&
      cached.key === cacheKey &&
      new Date(cached.expiresAt).getTime() > Date.now()
    ) {
      return cached.fileId;
    }

    const fileInfo = await uploadFile(file, {
      onStage: (stage) => {
        setProgress({
          step: stage,
          percent: stage === 'uploading' ? 0 : undefined,
        });
      },
      onProgress: (percent) => {
        setProgress({ step: 'uploading', percent });
      },
    });

    uploadedCacheRef.current = {
      key: cacheKey,
      fileId: fileInfo.file_id,
      expiresAt: fileInfo.expires_at,
    };
    return fileInfo.file_id;
  }

  async function handleAnalyzeFile(file: File, useMock: boolean) {
    setLoading(true);
    setError(null);
    setProgress({ step: 'requesting_url' });
    try {
      const fileId = await ensureFileUploaded(file);
      setProgress({ step: 'analyzing' });
      const data = await analyzeFileById(fileId, { mock: useMock });
      setResults(data);
      setCurrentStage('results');
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Error al subir o analizar el documento.',
      );
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  async function handleAnalyzeText(text: string, useMock: boolean) {
    setLoading(true);
    setError(null);
    setProgress({ step: 'analyzing' });
    try {
      const data = await analyzeSample(text, { mock: useMock });
      setResults(data);
      setCurrentStage('results');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Error al procesar el texto.',
      );
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  function handleResetAnalysis() {
    setResults(null);
    setError(null);
    setProgress(null);
    setCurrentStage('upload');
  }

  // 3. SI NO ESTÁ AUTENTICADO, MOSTRAMOS ÚNICAMENTE EL LOGIN
  // Le pasamos una función por prop para que al loguearse cambie el estado a true y entre a la app.
  if (!isAuthenticated) {
    return <LoginView onLoginSuccess={() => setIsAuthenticated(true)} />;
  }

  // 4. SI ESTÁ AUTENTICADO, SE RENDERIZA TODO TU CÓDIGO ORIGINAL EXACTAMENTE IGUAL
  return (
    <AppLayout
      activeSection={activeSection}
      onSelectSection={handleSelectSection}
      currentStage={currentStage}
      onSelectStage={setCurrentStage}
      hasResults={Boolean(results)}
      hasAdaptedVersion={false}
    >
      {activeSection === 'inicio' ? (
        <HomeView
          onGoToAnalysis={() => handleSelectSection('analisis')}
          onSelectSection={(section: NavSectionId) => handleSelectSection(section)}
        />
      ) : activeSection !== 'analisis' ? (
        <SectionPlaceholder
          section={activeSection}
          onGoToAnalysis={() => handleSelectSection('analisis')}
        />
      ) : (
        <>
          {error && (
            <div className="via-alert via-alert-danger" role="alert">
              <span>🚨 {error}</span>
              <button
                type="button"
                className="via-alert-close"
                onClick={() => setError(null)}
                aria-label="Cerrar mensaje de error"
              >
                ✕
              </button>
            </div>
          )}

          {currentStage === 'upload' || !results ? (
            <FileUploader
              onAnalyzeFile={handleAnalyzeFile}
              onAnalyzeText={handleAnalyzeText}
              isLoading={loading}
              progress={progress}
            />
          ) : (
            <div className="via-results-wrapper">
              <div className="via-results-toolbar">
                <button
                  type="button"
                  className="via-btn via-btn-outline"
                  onClick={handleResetAnalysis}
                >
                  <RotateCcw size={16} />
                  <span>Nuevo análisis</span>
                </button>
              </div>
              <AnalysisResults data={results} />
            </div>
          )}
        </>
      )}
    </AppLayout>
  );
}

export default App;