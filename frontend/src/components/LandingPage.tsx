import {
  ArrowRight,
  AudioLines,
  BookOpen,
  CheckCircle2,
  FileSearch,
  FileText,
  Lightbulb,
  FileUp,
  Network,
  Play,
  Sparkles,
  SlidersHorizontal,
  Wand2,
} from 'lucide-react';
import viaLogo from '../assets/BA.png';

interface LandingPageProps {
  onLogin: () => void;
  onRegister: () => void;
}

const BENEFITS = [
  {
    icon: FileSearch,
    title: 'Detectá barreras',
    description:
      'Encontrá dificultades de comprensión, estructura y presentación visual en tus materiales.',
    label: 'Diagnóstico claro',
    tone: 'blue',
  },
  {
    icon: Lightbulb,
    title: 'Recibí orientación',
    description:
      'Obtené recomendaciones prácticas para mejorar el acceso al contenido de cada estudiante.',
    label: 'Sugerencias útiles',
    tone: 'teal',
  },
  {
    icon: Wand2,
    title: 'Creá alternativas',
    description:
      'Transformá tus materiales en experiencias más accesibles, sin perder su objetivo pedagógico.',
    label: 'A tu manera',
    tone: 'yellow',
  },
];

const STEPS = [
  {
    number: '01',
    icon: FileUp,
    title: 'Subí tu material',
    description: 'Cargá el PDF o documento que utilizás en clase.',
    label: 'PDF O DOCUMENTO',
    tone: 'yellow',
  },
  {
    number: '02',
    icon: SlidersHorizontal,
    title: 'Elegí qué hacer',
    description: 'Analizalo para mejorar barreras o transformalo en otro formato.',
    label: 'ANALIZAR O TRANSFORMAR',
    tone: 'aqua',
  },
  {
    number: '03',
    icon: CheckCircle2,
    title: 'Revisá el resultado',
    description: 'Ajustá las sugerencias y guardá la versión que necesitás.',
    label: 'LISTO PARA COMPARTIR',
    tone: 'white',
  },
];

const EXAMPLES = [
  {
    subject: 'Ciencias naturales',
    title: 'De texto extenso a infografía',
    input: 'Procesamiento de la información',
    output: 'Resumen visual',
    type: 'infographic',
  },
  {
    subject: 'Historia',
    title: 'Del apunte a una narración',
    input: 'Captura de texto',
    output: 'Audio accesible',
    type: 'audio',
  },
  {
    subject: 'Lengua',
    title: 'De conceptos a mapa mental',
    input: 'Unidad temática',
    output: 'Relaciones visuales',
    type: 'mindmap',
  },
];

export function LandingPage({ onLogin, onRegister }: LandingPageProps) {
  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  }

  return (
    <main id="landing-top" className="via-landing">
      <header className="via-landing-header">
        <a className="via-landing-brand" href="#landing-top" aria-label="VIA, inicio">
          <img src={viaLogo} alt="VIA" />
          <span>Accesibilidad docente</span>
        </a>

        <nav className="via-landing-nav" aria-label="Navegación de la página">
          <a href="#landing-about">Qué es VIA</a>
          <a href="#landing-benefits">Beneficios</a>
          <a href="#landing-how">Cómo funciona</a>
          <a href="#landing-examples">Ejemplos</a>
        </nav>

        <div className="via-landing-auth">
          <button type="button" className="via-landing-login" onClick={onLogin}>
            Iniciar sesión
          </button>
          <button type="button" className="via-landing-register" onClick={onRegister}>
            Registrarse
          </button>
        </div>
      </header>

      <section id="landing-about" className="via-landing-hero">
        <div className="via-landing-hero-inner">
          <div className="via-landing-copy">
            <div className="via-landing-kicker">
              <Sparkles size={13} aria-hidden="true" />
              <span>Tecnología para una educación más accesible</span>
            </div>

            <h1>
              Transformá tus materiales en experiencias que{' '}
              <span>incluyen a todos</span>
            </h1>

            <p>
              VIA acompaña a docentes para detectar barreras de accesibilidad,
              mejorar contenidos y crear formatos alternativos con asistencia
              inteligente.
            </p>

            <div className="via-landing-actions">
              <button
                type="button"
                className="via-landing-primary"
                onClick={onLogin}
              >
                Explorá la herramienta
                <ArrowRight size={16} />
              </button>
              <button
                type="button"
                className="via-landing-secondary"
                onClick={() => scrollTo('landing-how')}
              >
                Ver cómo funciona
                <ArrowRight size={15} />
              </button>
            </div>

            <ul className="via-landing-trust-list" aria-label="Características">
              <li>
                <CheckCircle2 size={13} />
                Asistencia inteligente
              </li>
              <li>
                <CheckCircle2 size={13} />
                Recomendaciones claras
              </li>
              <li>
                <CheckCircle2 size={13} />
                Diseñada para docentes
              </li>
            </ul>
          </div>

          <div className="via-landing-visual">
            <span className="via-landing-shape via-landing-shape-loop" />
            <span className="via-landing-shape via-landing-shape-yellow" />
            <span className="via-landing-shape via-landing-shape-blue" />

            <div className="via-landing-demo-card">
              <div className="via-landing-demo-topbar">
                <div className="via-landing-demo-brand">
                  <span className="via-landing-demo-mark">
                    <AccessibilityMark />
                  </span>
                  <span>
                    <strong>VIA</strong>
                    <small>Accesibilidad docente</small>
                  </span>
                </div>
                <span className="via-landing-demo-status">
                  <span />
                  Material analizado
                </span>
              </div>

              <div className="via-landing-demo-content">
                <div className="via-landing-demo-document">
                  <div className="via-landing-demo-paper-icon">
                    <FileText size={22} />
                  </div>
                  <strong>Material de clase</strong>
                  <span className="via-demo-line long" />
                  <span className="via-demo-line" />
                  <span className="via-demo-line medium" />
                  <span className="via-demo-highlight">
                    <span />
                    <span />
                  </span>
                  <span className="via-demo-line long" />
                  <span className="via-demo-line short" />
                </div>

                <div className="via-landing-demo-connector" aria-hidden="true">
                  <span />
                  <ArrowRight size={18} />
                </div>

                <div className="via-landing-demo-results">
                  <div className="via-landing-demo-result-icon">
                    <Sparkles size={18} />
                  </div>
                  <strong>Más formas de aprender</strong>
                  <div className="via-demo-result-row">
                    <span><BookOpen size={13} /></span>
                    <span>Texto claro</span>
                    <CheckCircle2 size={13} />
                  </div>
                  <div className="via-demo-result-row">
                    <span><AudioLines size={13} /></span>
                    <span>Audio</span>
                    <CheckCircle2 size={13} />
                  </div>
                  <div className="via-demo-result-row">
                    <span><Wand2 size={13} /></span>
                    <span>Alternativa accesible</span>
                    <CheckCircle2 size={13} />
                  </div>
                </div>
              </div>

              <div className="via-landing-demo-footer">
                <span className="via-landing-demo-footer-icon">
                  <Sparkles size={13} />
                </span>
                Materiales, múltiples formas de aprender
              </div>
            </div>

            <div className="via-landing-floating-note">
              <CheckCircle2 size={15} />
              <span>Accesibilidad para todos</span>
            </div>
          </div>
        </div>
      </section>

      <section id="landing-benefits" className="via-landing-benefits">
        <div className="via-landing-section-heading">
          <span>Beneficios</span>
          <h2>Más tiempo para enseñar, más formas de aprender</h2>
          <p>
            Una herramienta pensada para integrar la accesibilidad al trabajo
            docente cotidiano.
          </p>
        </div>

        <div className="via-landing-benefit-grid">
          {BENEFITS.map((benefit) => {
            const Icon = benefit.icon;
            return (
              <article
                key={benefit.title}
                className={`via-landing-benefit-card is-${benefit.tone}`}
              >
                <div className="via-landing-benefit-top">
                  <span className="via-landing-benefit-icon">
                    <Icon size={19} />
                  </span>
                  <ArrowRight size={15} className="via-landing-benefit-arrow" />
                </div>
                <h3>{benefit.title}</h3>
                <p>{benefit.description}</p>
                <span className="via-landing-benefit-tag">
                  <CheckCircle2 size={12} />
                  {benefit.label}
                </span>
              </article>
            );
          })}
        </div>
      </section>

      <section id="landing-how" className="via-landing-how">
        <div className="via-landing-how-inner">
          <div className="via-landing-how-heading">
            <span>Cómo funciona</span>
            <h2>Del material original a una versión más accesible</h2>
            <p>
              Un recorrido simple que integra la accesibilidad sin sumar
              complejidad a tu planificación.
            </p>
          </div>
          <div className="via-landing-step-grid">
            {STEPS.map((step) => {
              const Icon = step.icon;
              return (
                <article
                  key={step.number}
                  className={`via-landing-step is-${step.tone}`}
                >
                  <div className="via-landing-step-visual">
                    <span className="via-landing-step-count">{step.number}</span>
                    <span className="via-landing-step-icon">
                      <Icon size={20} aria-hidden="true" />
                    </span>
                  </div>
                  <div className="via-landing-step-card">
                    <h3>{step.title}</h3>
                    <p>{step.description}</p>
                    <span className="via-landing-step-label">{step.label}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section id="landing-examples" className="via-landing-examples">
        <div className="via-landing-examples-inner">
          <div className="via-landing-examples-heading">
            <div>
              <span>Ejemplos</span>
              <h2>Distintas formas de presentar un contenido</h2>
              <p>
                Estos casos son ficticios y funcionan como espacios de muestra
                para reemplazar más adelante por proyectos reales.
              </p>
            </div>
            <div className="via-landing-example-stamp" aria-hidden="true">
              <span />
              <small>Contenido de ejemplo</small>
            </div>
          </div>

          <div className="via-landing-examples-grid">
            {EXAMPLES.map((example) => (
              <article
                key={example.type}
                className={`via-landing-example-card is-${example.type}`}
              >
                <ExamplePreview type={example.type} />
                <div className="via-landing-example-copy">
                  <span className="via-landing-example-subject">
                    {example.subject}
                  </span>
                  <h3>{example.title}</h3>
                  <div className="via-landing-example-tags">
                    <span>{example.input}</span>
                    <ArrowRight size={11} aria-hidden="true" />
                    <span>{example.output}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>

          <div className="via-landing-example-cta">
            <div>
              <h2>Empezá a crear materiales más accesibles</h2>
              <p>Explorá el prototipo y conocé todas las posibilidades de VIA.</p>
            </div>
            <button type="button" onClick={onLogin}>
              Probar VIA
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </section>

      <footer className="via-landing-footer">
        <a href="#landing-top" aria-label="Volver al inicio">
          <img src={viaLogo} alt="VIA" />
        </a>
        <span>Accesibilidad docente · Visualización, Inclusión y Accesibilidad</span>
      </footer>
    </main>
  );
}

function ExamplePreview({ type }: { type: string }) {
  if (type === 'infographic') {
    return (
      <div className="via-landing-example-preview" aria-hidden="true">
        <div className="via-example-infographic">
          <div className="via-example-info-heading">
            <span />
            <i />
          </div>
          <div className="via-example-info-content">
            <div className="via-example-info-bulb">
              <Lightbulb size={14} />
              <i />
              <i />
            </div>
            <div className="via-example-info-lines">
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (type === 'audio') {
    return (
      <div className="via-landing-example-preview" aria-hidden="true">
        <div className="via-example-audio">
          <div className="via-example-audio-heading">
            <span />
            <i />
          </div>
          <div className="via-example-wave">
            <span className="is-play"><Play size={9} fill="currentColor" /></span>
            {[8, 13, 7, 17, 11, 20, 12, 16, 8, 14, 6].map((height, index) => (
              <i key={index} style={{ height }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="via-landing-example-preview" aria-hidden="true">
      <div className="via-example-mindmap">
        <span className="via-example-map-line is-one" />
        <span className="via-example-map-line is-two" />
        <span className="via-example-map-line is-three" />
        <span className="via-example-map-node is-left">Tema</span>
        <span className="via-example-map-node is-center">
          <Network size={11} />
          Idea central
        </span>
        <span className="via-example-map-node is-right">Concepto</span>
        <span className="via-example-map-node is-bottom">Ejemplo</span>
      </div>
    </div>
  );
}

function AccessibilityMark() {
  return (
    <span className="via-landing-accessibility-mark" aria-hidden="true">
      VIA
    </span>
  );
}
