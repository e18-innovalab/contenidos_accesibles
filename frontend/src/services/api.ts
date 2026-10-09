import type { AnalysisResponse } from '../types/analysis';
const BASE_URL = `${import.meta.env.VITE_API_URL || 'https://innovalab-educacion-e18-test.up.railway.app'}/api/v1`;

export async function analyzeText(text: string, useMock: boolean = true): Promise<AnalysisResponse> {
  const response = await fetch(`${BASE_URL}/analysis/sample?mock=${useMock}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.trim() }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Error del servidor (${response.status})`);
  }

  return response.json();
}

export async function analyzePdf(file: File, useMock: boolean = true): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file); // El backend exige la clave 'file'

  const response = await fetch(`${BASE_URL}/analysis/pdf?mock=${useMock}`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Error del servidor (${response.status})`);
  }

  return response.json();
}