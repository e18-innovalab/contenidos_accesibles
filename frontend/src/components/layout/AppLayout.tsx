import { useState } from 'react';
import { Sidebar, type NavSectionId } from './Sidebar';
import { Topbar, type AnalysisStage, type UserProfileInfo } from './Topbar';

export interface AppLayoutProps {
  activeSection: NavSectionId;
  onSelectSection: (section: NavSectionId) => void;
  currentStage: AnalysisStage;
  onSelectStage?: (stage: AnalysisStage) => void;
  hasResults?: boolean;
  hasAdaptedVersion?: boolean;
  showSensitiveAlert?: boolean;
  onDismissSensitiveAlert?: () => void;
  user?: UserProfileInfo;
  children: React.ReactNode;
}

const SECTION_TITLES: Record<NavSectionId, string> = {
  inicio: 'INICIO',
  analisis: 'ANÁLISIS INTEGRAL',
  transformar: 'TRANSFORMAR MATERIAL',
  materiales: 'MIS MATERIALES',
  metricas: 'MÉTRICAS',
  configuracion: 'CONFIGURACIÓN',
};

export function AppLayout({
  activeSection,
  onSelectSection,
  currentStage,
  onSelectStage,
  hasResults = false,
  hasAdaptedVersion = false,
  showSensitiveAlert = false,
  onDismissSensitiveAlert,
  user,
  children,
}: AppLayoutProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className="via-app-shell">
      <a href="#main-content" className="via-skip-link">
        Saltar al contenido principal
      </a>

      <Sidebar
        activeSection={activeSection}
        onSelectSection={onSelectSection}
        isOpenMobile={isSidebarOpen}
        onCloseMobile={() => setIsSidebarOpen(false)}
      />

      <div className="via-content-column">
        <Topbar
          currentStage={currentStage}
          onSelectStage={onSelectStage}
          hasResults={hasResults}
          hasAdaptedVersion={hasAdaptedVersion}
          showStages={activeSection === 'analisis'}
          sectionTitle={SECTION_TITLES[activeSection]}
          user={user}
          showSensitiveAlert={showSensitiveAlert}
          onDismissSensitiveAlert={onDismissSensitiveAlert}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        />

        <main id="main-content" className="via-main-content" tabIndex={-1}>
          <div className="via-main-container">{children}</div>
        </main>
      </div>
    </div>
  );
}
