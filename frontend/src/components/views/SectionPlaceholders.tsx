import { Home, Sparkles, Folder, Settings, ArrowRight } from 'lucide-react';
import type { NavSectionId } from '../layout/Sidebar';

interface SectionPlaceholderProps {
section: Exclude<NavSectionId, 'analisis' | 'inicio'>;
  onGoToAnalysis: () => void;
}

const SECTION_CONFIG: Record<
  Exclude<NavSectionId, 'analisis' | 'inicio'>,
  {
    icon: React.ComponentType<{ size?: number }>;
    title: string;
    subtitle: string;
    showCta?: boolean;
  }
> = {
  transformar: {
    icon: Sparkles,
    title: 'Transformar material',
    subtitle:
      'Convertí un contenido en distintos formatos pedagógicos accesibles (resumen en lectura fácil, glosario o secuencia de diapositivas).',
  },
  materiales: {
    icon: Folder,
    title: 'Mis materiales',
    subtitle:
      'Consultá tus documentos analizados, descargá versiones adaptadas y gestioná tus enlaces compartidos.',
  },
  configuracion: {
    icon: Settings,
    title: 'Configuración',
    subtitle:
      'Preferencias de cuenta docente, privacidad y opciones de visualización.',
  },
};

export function SectionPlaceholder({
  section,
  onGoToAnalysis,
}: SectionPlaceholderProps) {
  const config = SECTION_CONFIG[section];
  const Icon = config.icon;

  return (
    <div className="via-placeholder-card">
      <div className="via-placeholder-icon" aria-hidden="true">
        <Icon size={28} />
      </div>
      <h1 className="via-page-title">{config.title}</h1>
      <p className="via-page-subtitle">{config.subtitle}</p>
      {config.showCta && (
        <div className="via-placeholder-actions">
          <button
            type="button"
            className="via-btn via-btn-primary"
            onClick={onGoToAnalysis}
          >
            <span>Ir a Análisis integral</span>
            <ArrowRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
