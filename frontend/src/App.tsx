import { useState, useEffect, useRef } from 'react';
import { useAuth, AuthenticateWithRedirectCallback } from '@clerk/clerk-react';
import {
  FileUploader,
  type UploadAnalysisProgress,
} from './components/FileUploader';
import { AnalysisProgressView } from './components/AnalysisProgressView';
import { AnalysisResults } from './components/AnalysisResults';
import { AdaptedVersionView } from './components/AdaptedVersionView';
import { TransformMaterialView } from './components/views/TransformMaterialView';
import { AppLayout } from './components/layout/AppLayout';
import type { NavSectionId } from './components/layout/Sidebar';
import type { AnalysisStage } from './components/layout/Topbar';
import { SectionPlaceholder } from './components/views/SectionPlaceholders';
import { HomeView } from './components/HomeView';
import { LoginView } from './components/views/LoginView';
import { MetricsView } from './components/views/MetricsView';
import {
  ApiError,
  analyzeFileById,
  analyzeSample,
  uploadFile,
  setAuthTokenProvider,
} from './services/api';
import type {
  AccessibilityAnalysisResponse,
  AdaptationProposal,
} from './types/analysis';
import { getFileCacheKey } from './utils/fileValidation';

const VALID_SECTIONS: NavSectionId[] = [
  'inicio',
  'analisis',
  'transformar',
  'materiales',
  'metricas',
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
  filename: string;
  expiresAt: string;
}

export function App() {
  if (window.location.pathname.includes('/sso-callback')) {
    return <AuthenticateWithRedirectCallback />;
  }

  const { getToken, isSignedIn, isLoaded } = useAuth();

  useEffect(() => {
    if (isSignedIn) {
      setAuthTokenProvider(() => getToken());
    }
  }, [isSignedIn, getToken]);

  const [activeSection, setActiveSection] = useState<NavSectionId>(getSectionFromHash);
  const [currentStage, setCurrentStage] = useState<AnalysisStage>('upload');
  const [loading, setLoading] = useState<boolean>(false);
  const [showAnalysisProgress, setShowAnalysisProgress] = useState<boolean>(false);
  const [progress, setProgress] = useState<UploadAnalysisProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<AccessibilityAnalysisResponse | null>(null);
  const [originalSourceText, setOriginalSourceText] = useState<string>('');
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sensitiveUploadAlert, setSensitiveUploadAlert] = useState<boolean>(false);
  const [adaptedProposals, setAdaptedProposals] = useState<Record<string, AdaptationProposal>>({});
  const [hasAdaptedVersion, setHasAdaptedVersion] = useState<boolean>(false);

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
      filename: fileInfo.filename || file.name,
      expiresAt: fileInfo.expires_at,
    };
    return fileInfo.file_id;
  }

  async function handleAnalyzeFile(file: File, useMock: boolean) {
    setSourceFile(file);
    setSensitiveUploadAlert(false);
    setLoading(true);
    setShowAnalysisProgress(true);
    setError(null);
    setOriginalSourceText('');
    setHasAdaptedVersion(false);
    setAdaptedProposals({});
    setProgress({ step: 'requesting_url' });
    try {
      const fileId = await ensureFileUploaded(file);
      setProgress({ step: 'analyzing' });
      const data = await analyzeFileById(fileId, { mock: useMock });
      setResults(data);
      setCurrentStage('results');
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.code === 'sensitive_data_detected' || (err.findings?.length ?? 0) > 0)
      ) {
        setSensitiveUploadAlert(true);
        setError(null);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'Error al subir o analizar el documento.',
        );
      }
    } finally {
      setLoading(false);
      setShowAnalysisProgress(false);
      setProgress(null);
    }
  }

  async function handleAnalyzeText(text: string, useMock: boolean) {
    setSourceFile(null);
    setSensitiveUploadAlert(false);
    setLoading(true);
    setShowAnalysisProgress(false);
    setError(null);
    setOriginalSourceText(text);
    setHasAdaptedVersion(false);
    setAdaptedProposals({});
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

  function handleOpenAdaptedVersion(proposals: Record<string, AdaptationProposal>) {
    setAdaptedProposals(proposals);
    setHasAdaptedVersion(true);
    setCurrentStage('adapted');
  }

  function handleResetAnalysis() {
    setResults(null);
    setOriginalSourceText('');
    setSourceFile(null);
    setSensitiveUploadAlert(false);
    setAdaptedProposals({});
    setHasAdaptedVersion(false);
    setError(null);
    setProgress(null);
    setCurrentStage('upload');
  }

  if (!isLoaded) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontFamily: 'sans-serif' }}>
        <p>Cargando sesión...</p>
      </div>
    );
  }

  if (!isSignedIn) {
    return <LoginView />;
  }

  const transformInitialSource = results?.analysis_id
    ? {
        analysisId: results.analysis_id,
        fileId: uploadedCacheRef.current?.fileId ?? null,
        filename:
          results.metadata?.filename ||
          uploadedCacheRef.current?.filename ||
          'Material analizado',
        isUploaded: true,
      }
    : uploadedCacheRef.current &&
        new Date(uploadedCacheRef.current.expiresAt).getTime() > Date.now()
      ? {
          fileId: uploadedCacheRef.current.fileId,
          analysisId: null,
          filename: uploadedCacheRef.current.filename,
          isUploaded: true,
        }
      : null;

  return (
    <AppLayout
      activeSection={activeSection}
      onSelectSection={handleSelectSection}
      currentStage={currentStage}
      onSelectStage={setCurrentStage}
      hasResults={Boolean(results)}
      hasAdaptedVersion={hasAdaptedVersion}
      showSensitiveAlert={sensitiveUploadAlert}
      onDismissSensitiveAlert={() => setSensitiveUploadAlert(false)}
    >
      {activeSection === 'inicio' ? (
        <HomeView
          onGoToAnalysis={() => handleSelectSection('analisis')}
          onSelectSection={(section: NavSectionId) => handleSelectSection(section)}
        />
      ) : activeSection === 'transformar' ? (
        <TransformMaterialView
          initialSource={transformInitialSource}
          onSourceChange={(nextSource) => {
            if (nextSource?.fileId && nextSource?.filename) {
              uploadedCacheRef.current = {
                key: `manual-${nextSource.fileId}`,
                fileId: nextSource.fileId,
                filename: nextSource.filename,
                expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
              };
            }
          }}
        />
      ) : activeSection === 'metricas' ? (
        <MetricsView />
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

          {loading && showAnalysisProgress ? (
            <AnalysisProgressView />
          ) : currentStage === 'upload' || !results ? (
            <FileUploader
              onAnalyzeFile={handleAnalyzeFile}
              onAnalyzeText={handleAnalyzeText}
              onGoToTransform={() => handleSelectSection('transformar')}
              initialFile={sourceFile}
              onClearSensitiveAlert={() => setSensitiveUploadAlert(false)}
              isLoading={loading}
              progress={progress}
            />
          ) : currentStage === 'adapted' ? (
            <AdaptedVersionView
              analysis={results}
              proposalsByBarrier={adaptedProposals}
              originalSourceText={originalSourceText}
              onBackToAnalysis={() => setCurrentStage('results')}
            />
          ) : (
            <div className="via-results-wrapper">
              <AnalysisResults
                data={results}
                sourceFile={sourceFile}
                originalSourceText={originalSourceText}
                onViewAdapted={handleOpenAdaptedVersion}
                onResetAnalysis={handleResetAnalysis}
              />
            </div>
          )}
        </>
      )}
    </AppLayout>
  );
}

export default App;