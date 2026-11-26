import { useState, useRef, useEffect } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  GraduationCap,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { useUser, useClerk } from '@clerk/clerk-react';

export type AnalysisStage = 'upload' | 'results' | 'adapted';

export interface UserProfileInfo {
  name: string;
  role: string;
  avatarUrl?: string;
}

export interface TopbarProps {
  currentStage: AnalysisStage;
  onSelectStage?: (stage: AnalysisStage) => void;
  hasResults?: boolean;
  hasAdaptedVersion?: boolean;
  showStages?: boolean;
  sectionTitle?: string;
  user?: UserProfileInfo;
  showSensitiveAlert?: boolean;
  onDismissSensitiveAlert?: () => void;
  isSidebarOpen: boolean;
  onToggleSidebar: () => void;
}

interface StageItem {
  id: AnalysisStage;
  label: string;
}

const STAGES: StageItem[] = [
  { id: 'upload', label: 'INICIAR ANÁLISIS' },
  { id: 'results', label: 'ANÁLISIS ORIENTATIVO' },
  { id: 'adapted', label: 'VERSIÓN ADAPTADA' },
];

export function Topbar({
  currentStage,
  onSelectStage,
  hasResults = false,
  hasAdaptedVersion = false,
  showStages = true,
  sectionTitle,
  user,
  showSensitiveAlert = false,
  onDismissSensitiveAlert,
  isSidebarOpen,
  onToggleSidebar,
}: TopbarProps) {
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const [menuOpen, setMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Toma los datos reales de Clerk (o usa los recibidos por props como respaldo)
  const displayName =
    clerkUser?.fullName ||
    clerkUser?.firstName ||
    clerkUser?.primaryEmailAddress?.emailAddress ||
    user?.name ||
    'Docente';
  const displayRole = user?.role || 'Docente';
  const displayAvatar = clerkUser?.imageUrl || user?.avatarUrl;

  // Cerrar el desplegable al hacer clic afuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function isStageEnabled(stageId: AnalysisStage): boolean {
    if (stageId === 'upload') return true;
    if (stageId === 'results')
      return hasResults || currentStage === 'results' || currentStage === 'adapted';
    if (stageId === 'adapted')
      return hasAdaptedVersion || currentStage === 'adapted';
    return false;
  }

  async function handleSignOut() {
    setMenuOpen(false);
    // Limpia el hash para volver limpio al inicio y cierra sesión en Clerk
    window.location.hash = '';
    await signOut();
  }

  return (
    <header className="via-topbar">
      {showSensitiveAlert && (
        <aside className="via-sensitive-alert-toast" role="alert">
          <div className="via-sensitive-alert-content">
            <AlertTriangle size={18} aria-hidden="true" />
            <div>
              <strong>Se detectaron datos personales</strong>
              <p>
                Por favor, revise el documento ya que detectamos datos
                personales. ¡Cuide de cargar información sensible de sus
                alumnos!
              </p>
            </div>
          </div>
          <button
            type="button"
            className="via-icon-btn"
            aria-label="Cerrar aviso de datos personales"
            onClick={onDismissSensitiveAlert}
          >
            <X size={16} />
          </button>
        </aside>
      )}
      <div className="via-topbar-left">
        <button
          type="button"
          className="via-mobile-menu-btn"
          onClick={onToggleSidebar}
          aria-expanded={isSidebarOpen}
          aria-controls="via-sidebar"
          aria-label="Abrir menú de navegación"
        >
          <Menu size={22} />
        </button>

        {showStages ? (
          <nav className="via-stage-nav" aria-label="Etapas del análisis">
            <ol className="via-stage-list">
              {STAGES.map((stage) => {
                const isActive = currentStage === stage.id;
                const enabled = isStageEnabled(stage.id);

                return (
                  <li key={stage.id} className="via-stage-item">
                    <button
                      type="button"
                      className={`via-stage-tab ${isActive ? 'active' : ''} ${
                        !enabled ? 'disabled' : ''
                      }`}
                      aria-current={isActive ? 'step' : undefined}
                      disabled={!enabled}
                      onClick={() => {
                        if (enabled && onSelectStage) {
                          onSelectStage(stage.id);
                        }
                      }}
                    >
                      {stage.label}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        ) : (
          <div className="via-topbar-section-title">
            <span>{sectionTitle}</span>
          </div>
        )}
      </div>

      <div className="via-topbar-right" ref={dropdownRef} style={{ position: 'relative' }}>
        <button
          type="button"
          className="via-user-profile"
          onClick={() => setMenuOpen((prev) => !prev)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={`Perfil de ${displayName}, rol ${displayRole}`}
        >
          <div className="via-user-avatar" aria-hidden="true">
            {displayAvatar ? (
              <img src={displayAvatar} alt={displayName} />
            ) : (
              <GraduationCap size={20} strokeWidth={2.2} />
            )}
          </div>
          <div className="via-user-info">
            <span className="via-user-name">{displayName}</span>
            <span className="via-user-role">{displayRole}</span>
          </div>
          <ChevronDown
            size={15}
            className="via-user-chevron"
            aria-hidden="true"
            style={{
              transform: menuOpen ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease',
            }}
          />
        </button>

        {menuOpen && (
          <div className="via-user-dropdown" role="menu">
            <div className="via-user-dropdown-header">
              <span className="via-user-dropdown-name">{displayName}</span>
              {clerkUser?.primaryEmailAddress?.emailAddress && (
                <span className="via-user-dropdown-email">
                  {clerkUser.primaryEmailAddress.emailAddress}
                </span>
              )}
            </div>
            <button
              type="button"
              role="menuitem"
              className="via-user-dropdown-item via-logout-btn"
              onClick={handleSignOut}
            >
              <LogOut size={16} />
              <span>Cerrar sesión</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
}