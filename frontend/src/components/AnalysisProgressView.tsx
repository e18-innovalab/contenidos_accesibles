import { useState, useEffect } from 'react';
import { Sparkles, CheckCircle2, Clock, Loader2 } from 'lucide-react';

interface AnalysisProgressViewProps {
  onComplete: () => void; // Función que se ejecuta cuando termina el último paso
}

export function AnalysisProgressView({ onComplete }: AnalysisProgressViewProps) {
  // Estado para controlar en qué paso vamos (de 1 a 4)
  const [currentStep, setCurrentStep] = useState<number>(1);

  useEffect(() => {
    // Definimos los tiempos de transición para simular el escaneo
    const timer1 = setTimeout(() => setCurrentStep(2), 1500); // Pasa al paso 2 a los 1.5s
    const timer2 = setTimeout(() => setCurrentStep(3), 3000); // Pasa al paso 3 a los 3s
    const timer3 = setTimeout(() => setCurrentStep(4), 4500); // Pasa al paso 4 a los 4.5s
    
    // Al finalizar el último paso, esperamos un poco y llamamos a onComplete para mostrar los resultados
    const timer4 = setTimeout(() => {
      onComplete();
    }, 6000);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
    };
  }, [onComplete]);

  // Lista de pasos de escaneo
  const steps = [
    { id: 1, title: 'Leyendo el contenido', desc: 'Identificamos títulos, párrafos, imágenes y recursos.' },
    { id: 2, title: 'Revisando la estructura', desc: 'Comprobamos el orden y la jerarquía de la información.' },
    { id: 3, title: 'Evaluando la accesibilidad', desc: 'Analizamos contraste, legibilidad y alternativas visuales.' },
    { id: 4, title: 'Preparando recomendaciones', desc: 'La IA está sugiriendo oportunidades de mejora.' },
  ];

  return (
    <div className="via-processing-card-wrapper">
      <div className="via-processing-card">
        {/* Ícono superior animado */}
        <div className="via-processing-icon-container">
          <Sparkles size={32} className="via-pulse-icon" />
        </div>

        <div className="via-processing-header">
          <span className="via-section-tag">ESCANER INTELIGENTE</span>
          <h2 className="via-processing-title">Estamos escaneando tu material</h2>
          <p className="via-processing-subtitle">Esto puede tomar unos segundos. No cierres esta ventana.</p>
        </div>

        {/* Lista de pasos dinámicos */}
        <div className="via-steps-list">
          {steps.map((step) => {
            const isCompleted = currentStep > step.id;
            const isCurrent = currentStep === step.id;
            const isPending = currentStep < step.id;

            return (
              <div 
                key={step.id} 
                className={`via-step-item ${isCurrent ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
              >
                <div className="via-step-indicator">
                  {isCompleted && <CheckCircle2 size={20} className="text-success" />}
                  {isCurrent && <Loader2 size={20} className="via-spinner text-primary" />}
                  {isPending && <Clock size={20} className="text-muted" />}
                </div>

                <div className="via-step-content">
                  <h4>{step.title}</h4>
                  <p>{step.desc}</p>
                </div>

                {isCurrent && (
                  <div className="via-step-dots">
                    <span>.</span><span>.</span><span>.</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Barra de progreso inferior */}
        <div className="via-progress-bar-container">
          <div 
            className="via-progress-bar-fill" 
            style={{ width: `${(currentStep / steps.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}