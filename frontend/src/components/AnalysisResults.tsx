import { useState } from 'react';
import type { AnalysisResponse, Barrier, Dimension } from '../types/analysis';

interface AnalysisResultsProps {
data: AnalysisResponse | null;
}

export function AnalysisResults(props: AnalysisResultsProps) {
const [decisions, setDecisions] = useState<Record<string, 'accepted' | 'rejected'>>({});

if (!props.data) {
return null;
 }

  const { estimated_score, summary, dimensions, strengths, barriers, warnings } = props.data;

  function handleDecision(barrierId: string, decision: 'accepted' | 'rejected') {
    setDecisions((prev) => ({
      ...prev,
      [barrierId]: decision,
    }));
  }

  return (
    <div>
      <h2>Resultado del Análisis</h2>
      <div>
        <h3>Puntuación Estimada</h3>
        <p><strong>{estimated_score}</strong> / 100</p>
      </div>

      {summary && (
        <div>
          <h3>Resumen</h3>
          <p>{summary}</p>
        </div>
      )}


      {dimensions && dimensions.length > 0 && (
        <div>
          <h3>Dimensiones</h3>
          <ul>
            {dimensions.map((dim: Dimension, index: number) => (
              <li key={index}>
                <p><strong>Categoría:</strong> {dim.category} | <strong>Estado:</strong> {dim.status}</p>
                <p>{dim.comment}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

{strengths && strengths.length > 0 && (
<div>
<h3>Puntos Fuertes</h3>
<ul>
{strengths.map((strength: string, index: number) => ( <li key={index}>{strength}</li>
))}
</ul>
</div>
)}

{barriers && barriers.length > 0 && (
<div>
<h3>Barreras Detectadas ({barriers.length})</h3>
<ul>
{barriers.map((barrier: Barrier) => { const currentDecision = decisions[barrier.id];

return (
<li key={barrier.id} style={{ marginBottom: '1.5rem' }}><p>
<strong>Categoría:</strong> {barrier.category} | 
<strong> Severidad:</strong> {barrier.severity}</p>
<p><strong>Problema:</strong> {barrier.issue}</p>
<p>{barrier.explanation}</p>
<p><strong>Recomendación:</strong> {barrier.recommendation}</p>
{barrier.suggested_rewrite && (
<p><em>Sugerencia de redacción: {barrier.suggested_rewrite}</em></p>
)}

<div>
<button type="button" onClick={() => handleDecision(barrier.id, 'accepted')}
style={{ marginRight: '0.5rem' }}>
{currentDecision === 'accepted' ? '✓ Aceptado' : 'Aceptar Cambio'}
</button>

<button type="button" onClick={() => handleDecision(barrier.id, 'rejected')}>
{currentDecision === 'rejected' ? '✕ Rechazado' : 'Rechazar Cambio'}
</button>
</div>
</li>
);
})}
</ul>
</div>
)}

      {warnings && warnings.length > 0 && (
        <div>
          <h3>Advertencias</h3>
          <ul>
            {warnings.map((warning: string, index: number) => (
              <li key={index}>⚠️ {warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}