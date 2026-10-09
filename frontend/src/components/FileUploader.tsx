import { useState } from 'react';

interface FileUploaderProps {
  onAnalyzePdf: (file: File, useMock: boolean) => void;
  onAnalyzeText: (text: string, useMock: boolean) => void;
  isLoading: boolean;
}

export function FileUploader(props: FileUploaderProps) {
  const [tab, setTab] = useState<'pdf' | 'text'>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState<string>('');
  const [useMock, setUseMock] = useState<boolean>(true);
  const [validationError, setValidationError] = useState<string | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setValidationError(null);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setValidationError(null);

    if (tab === 'pdf') {
      if (!file) {
        setValidationError('Por favor, selecciona un archivo PDF.');
        return;
      }
      props.onAnalyzePdf(file, useMock);
    } else {
      if (text.trim().length < 10) {
        setValidationError('El texto debe tener al menos 10 caracteres.');
        return;
      }
      props.onAnalyzeText(text, useMock);
    }
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">Logo goes here</div>
        <nav className="sidebar-nav">
          <button type="button" className="nav-item"> Inicio</button>
          <button type="button" className="nav-item active"> Nuevo análisis</button>
          <button type="button" className="nav-item"> Transformar material</button>
          <button type="button" className="nav-item"> Repositorio</button>
          <button type="button" className="nav-item"> Configuración</button>
        </nav>
      </aside>

      <main className="main-content">
        <small className="text-muted font-weight-bold">Nuevo análisis</small>
        <h1 className="h2 font-weight-bold mt-1">¿Listo para analizar?</h1>
        <p className="text-muted">Adaptá tu contenido educativo más accesible</p>

        <div className="d-flex align-items-center justify-content-between my-3">
          <div>
 <button type="button"  className={`btn btn-sm mr-2 ${tab === 'pdf' ? 'btn-secondary' : 'btn-outline-secondary'}`} onClick={() => setTab('pdf')}>
 Subir PDF
 </button>

 <button type="button"  className={`btn btn-sm ${tab === 'text' ? 'btn-secondary' : 'btn-outline-secondary'}`} onClick={() => setTab('text')}>
 Pegar Texto
 </button>
 </div>

 <label className="mb-0 small text-muted style-pointer">
 <input  type="checkbox"  checked={useMock}  onChange={() => setUseMock(!useMock)} 
className="mr-1" />
 Usar Modo Mock
 </label>
   </div>

 <form onSubmit={handleSubmit}>
  <div className="dropzone-container">
  <div className="dropzone-icon">📎</div>
{tab === 'pdf' ? (
 <>
<h3 className="h5 font-weight-bold">Arrastrá y soltá o selecciona un archivo de tu compu!</h3>
<p className="text-muted small">Subí tu documento para analizarlo.</p>
                
<label className="btn-purple mt-2 d-inline-block style-pointer">
   {file ? file.name : 'Seleccionar archivo'}
  <input type="file"  accept=".pdf"   onChange={handleFileChange}  style={{ display: 'none' }}/>
  </label>
 <p className="text-muted small mt-3 mb-0">Formatos permitidos: PDF, DOC, DOCX, PPTX</p>
   </>
   ) : (
 <>
<h3 className="h5 font-weight-bold">Pegá el texto a analizar</h3>
<textarea className="form-control mt-3 mb-2" rows={5} placeholder="Ingresá o pegá el texto aquí..." value={text} onChange={(e) => setText(e.target.value)}/>
  </>
 )}

 {validationError && ( <p className="text-danger small mt-2">⚠️ {validationError}</p>
 )}

<div className="mt-4">
<button type="submit" className="btn btn-primary"disabled={props.isLoading}>
{props.isLoading ? 'Analizando...' : 'Escanear Accesibilidad'}
   </button>
  </div>
   </div>
  </form>

<section className="mt-5">
          <h3 className="h5 font-weight-bold">¿Que analiza la herramienta?</h3>
          <p className="text-muted small">Revisamos diferentes aspectos del documento para detectar barreras y oportunidades de mejora sin que tengas que hacer nada.</p>

<div className="analysis-features-grid">
 <div className="feature-card">
 <h4>Accesibilidad visual</h4>
 <ul>
  <li>✓ Contraste y legibilidad</li>
   <li>✓ Imágenes y gráficos</li>
    <li>✓ Texto alternativo</li>
   </ul>
 </div>

<div className="feature-card">
 <h4>Accesibilidad auditiva</h4>
  <ul>
  <li>✓ Contenido alternativo</li>
  <li>✓ Información en formato de audio</li>
  <li>✓ Texto con alternativo</li>
   </ul>
</div>

<div className="feature-card">
  <h4>Comprensión del contenido</h4>
<ul>
<li>✓ Lenguaje claro</li>
<li>✓ Oraciones y párrafos simples</li>
 <li>✓ Consignas e instrucciones clara</li>
 </ul>
 </div>

<div className="feature-card">
              <h4>Estructura y navegación</h4>
              <ul>
                <li>✓ Títulos y subtítulos</li>
                <li>✓ Información organizada jerárquicamente</li>
                <li>✓ Navegación lógica</li>
              </ul>
            </div>
          </div>
        </section>
      </main>

<aside className="right-panel">
        <div className="text-center mb-4">
          <span style={{ fontSize: '2.5rem' }}>🧍</span>
          <h3 className="h5 font-weight-bold mt-2">Analisis integral</h3>
          <p className="text-muted small">
            Analiza tu material en busca de posibles barreras de accesibilidad y te recomienda mejoras para hacerlo más accesible
          </p>
        </div>

        <div className="checklist-container">
          <div className="checklist-item text-success">
            <span>🟢</span> Accesibilidad visual
          </div>
          <div className="checklist-item text-success">
            <span>🟢</span> Accesibilidad auditiva
          </div>
          <div className="checklist-item text-success">
            <span>🟢</span> Comprensión del contenido
          </div>
          <div className="checklist-item text-success">
            <span>🟢</span> Estructura y navegación
          </div>
        </div>
      </aside>
    </div>
  );
}