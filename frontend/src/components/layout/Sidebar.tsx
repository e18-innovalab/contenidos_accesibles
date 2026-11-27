import { useEffect } from 'react';
import {
  Home,
  FileText,
  Sparkles,
  Folder,
  BarChart3,
  Settings,
  X,
} from 'lucide-react';
import viaLogo from '../../assets/BA.png';

export type NavSectionId =
  | 'inicio'
  | 'analisis'
  | 'transformar'
  | 'materiales'
  | 'metricas'
  | 'configuracion';

export interface SidebarProps {
  activeSection: NavSectionId;
  onSelectSection: (section: NavSectionId) => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
}

interface NavItemConfig {
  id: NavSectionId;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
}

const NAV_ITEMS: NavItemConfig[] = [
  { id: 'inicio', label: 'Inicio', icon: Home },
  { id: 'analisis', label: 'Análisis integral', icon: FileText },
  { id: 'transformar', label: 'Transformar material', icon: Sparkles },
  { id: 'materiales', label: 'Mis materiales', icon: Folder },
  { id: 'metricas', label: 'Métricas', icon: BarChart3 },
  { id: 'configuracion', label: 'Configuración', icon: Settings },
];

export function Sidebar({
  activeSection,
  onSelectSection,
  isOpenMobile,
  onCloseMobile,
}: SidebarProps) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpenMobile) {
        onCloseMobile();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpenMobile, onCloseMobile]);

  function handleItemClick(id: NavSectionId) {
    onSelectSection(id);
    onCloseMobile();
  }

  return (
    <>
      {isOpenMobile && (
        <div
          className="via-sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        id="via-sidebar"
        className={`via-sidebar ${isOpenMobile ? 'is-open' : ''}`}
        aria-label="Menú lateral de VIA"
      >
        <div className="via-sidebar-header">
          <div className="via-brand">
            <img className="via-brand-logo" src={viaLogo} alt="VIA" />
            <div className="via-brand-text">
              <span className="via-brand-subtitle">
                Visualización, inclusión y accesibilidad
              </span>
            </div>
          </div>

          <button
            type="button"
            className="via-sidebar-close-btn"
            onClick={onCloseMobile}
            aria-label="Cerrar menú lateral"
          >
            <X size={20} />
          </button>
        </div>

        <nav className="via-sidebar-nav" aria-label="Navegación principal">
          <ul className="via-sidebar-list">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <li key={item.id} className="via-sidebar-list-item">
                  <button
                    type="button"
                    className={`via-nav-item ${isActive ? 'active' : ''}`}
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => handleItemClick(item.id)}
                  >
                    <Icon
                      size={19}
                      strokeWidth={isActive ? 2.2 : 1.9}
                      className="via-nav-icon"
                    />
                    <span className="via-nav-label">{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
    </>
  );
}
