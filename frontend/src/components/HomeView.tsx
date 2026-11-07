import { 
  CheckCircle2, 
  ArrowRight, 
  Sparkles, 
  PersonStanding,
  FileSearch, 
  FileText 
} from 'lucide-react';
import type { NavSectionId } from './layout/Sidebar';

interface HomeViewProps {
  onGoToAnalysis: () => void;
  onSelectSection: (section: NavSectionId) => void;
}

export function HomeView({ onGoToAnalysis, onSelectSection }: HomeViewProps) {
  return (
    <div className="via-home-container">
      {/* 1. HERO BANNER PRINCIPAL */}
      <section className="via-home-hero">
        <div className="via-hero-content">
          <div className="via-badge-hero">
            <PersonStanding size={14} />
            <span>ACCESIBILIDAD DOCENTE</span>
          </div>

          <h1 className="via-hero-title">
            Materiales más claros, accesibles y fáciles de aprender
          </h1>

          <p className="via-hero-subtitle">
            VIA te ayuda a revisar barreras de accesibilidad y a crear nuevas versiones de tus contenidos educativos, sin perder su intención pedagógica.
          </p>

          <div className="via-hero-actions">
            <button 
              type="button" 
              className="via-btn via-btn-yellow"
              onClick={onGoToAnalysis}
            >
              <span>Iniciar análisis</span>
              <ArrowRight size={16} />
            </button>

            <button 
              type="button" 
              className="via-btn via-btn-hero-outline"
              onClick={() => onSelectSection('transformar')}
            >
              <Sparkles size={16} />
              <span>Transformar material</span>
            </button>
          </div>
        </div>

        {/* 🎨 SECCIÓN DE LOS 3 DISEÑOS FLOTANTES (Lado derecho) */}
        <div className="via-hero-illustration">
          {/* Círculos concéntricos decorativos de fondo */}
          <div className="via-circle-wave via-wave-1"></div>
          <div className="via-circle-wave via-wave-2"></div>

          {/* 1. Tarjeta blanca superior izquierda (Documento) */}
          <div className="via-floating-card via-card-white">
            <FileText size={22} className="via-text-blue" />
          </div>

          {/* 2. Tarjeta central principal (Celeste con ícono de accesibilidad) */}
          <div className="via-floating-card via-card-main-teal">
            <PersonStanding size={48} className="via-text-dark" />
          </div>

          {/* 3. Tarjeta amarilla inferior derecha (Destellos) */}
          <div className="via-floating-card via-card-yellow">
            <Sparkles size={20} className="via-text-dark" />
          </div>
        </div>
      </section>

      {/* 2. ACCESOS RÁPIDOS */}
      <section className="via-home-section">
        <div className="via-section-header">
          <span className="via-section-tag">ACCESOS RÁPIDOS</span>
          <h2 className="via-section-title">¿Qué necesitás hacer hoy?</h2>
          <p className="via-section-subtitle">
            Podés evaluar un material existente o convertirlo en un formato diferente según las necesidades de tus estudiantes.
          </p>
        </div>

        <div className="via-home-cards-grid">
          {/* TARJETA 1: ANÁLISIS INTEGRAL */}
          <div className="via-home-card via-card-blue-accent">
            <div className="via-card-top">
              <div className="via-card-icon-wrapper via-icon-blue">
                <FileSearch size={22} />
              </div>
              <span className="via-badge via-badge-blue">REVISAR</span>
            </div>

            <h3 className="via-card-title">Análisis integral</h3>
            <p className="via-card-desc">
              Detectá barreras de comprensión, estructura y accesibilidad visual. Recibí recomendaciones y corregí cada hallazgo.
            </p>

            <ul className="via-card-features">
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Obtené un diagnóstico del material</span>
              </li>
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Revisá hallazgos uno por uno</span>
              </li>
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Aplicá mejoras con asistencia de IA</span>
              </li>
            </ul>

            <button
              type="button"
              className="via-btn via-btn-primary via-btn-full"
              onClick={onGoToAnalysis}
            >
              <span>Ir a Análisis integral</span>
              <ArrowRight size={16} />
            </button>
          </div>

          {/* TARJETA 2: TRANSFORMAR MATERIAL */}
          <div className="via-home-card via-card-teal-accent">
            <div className="via-card-top">
              <div className="via-card-icon-wrapper via-icon-teal">
                <Sparkles size={22} />
              </div>
              <span className="via-badge via-badge-teal">CREAR</span>
            </div>

            <h3 className="via-card-title">Transformar material</h3>
            <p className="via-card-desc">
              Creá una nueva versión del contenido como infografía, audio, mapa mental o material sin imágenes.
            </p>

            <ul className="via-card-features">
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Elegí entre cuatro formatos accesibles</span>
              </li>
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Conservá las ideas principales</span>
              </li>
              <li>
                <CheckCircle2 size={18} className="via-check-icon" />
                <span>Revisá la nueva versión antes de guardarla</span>
              </li>
            </ul>

            <button
              type="button"
              className="via-btn via-btn-teal via-btn-full"
              onClick={() => onSelectSection('transformar')}
            >
              <span>Ir a Transformar material</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </section>

      {/* 3. SECCIÓN LA DIFERENCIA */}
      <section className="via-home-footer-section">
        <div className="via-footer-grid">
          <div className="via-footer-info">
            <span className="via-section-tag">LA DIFERENCIA</span>
            <h2 className="via-footer-title">Dos caminos, según tu objetivo</h2>
          </div>

          <div className="via-footer-boxes">
            <div className="via-mini-card">
              <h4>Analizar es diagnosticar</h4>
              <p>Usalo cuando quieras identificar qué barreras tiene el material actual y mejorarlo sin cambiar su formato.</p>
            </div>

            <div className="via-mini-card">
              <h4>Transformar es crear</h4>
              <p>Usalo cuando necesites presentar el mismo contenido de otra manera o eliminar la dependencia de las imágenes.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}