export type Severity = 'para_revisar' | 'barrera_detectada';
export type DimensionStatus = 'correcta' | 'para_revisar' | 'barrera_detectada';
export type BarrierSource = 'ai' | 'rules';

export interface Barrier {
  id: string;
  category: string;
  severity: Severity;
  issue: string;
  original_text?: string;
  explanation: string;
  recommendation: string;
  suggested_rewrite?: string;
  source: BarrierSource;
  fragment_found: boolean;
}

export interface Dimension {
  category: 'comprension' | 'estructura' | 'accesibilidad_visual' | string;
  status: DimensionStatus;
  comment: string;
}

export interface ScoreBreakdown {
  [key: string]: unknown;
}

export interface Metadata {
  provider?: string;
  model?: string;
  latency_ms?: number;
  page_count?: number;
  image_count?: number;
  tokens_used?: number;
  is_truncated?: boolean;
  is_scanned_pdf?: boolean;
  rules_metrics?: {
    sentences_count?: number;
    paragraphs_count?: number;
    headings_count?: number;
    hierarchy_levels?: number;
    list_items_count?: number;
  };
}

export interface AnalysisResponse {
  estimated_score: number;
  summary: string;
  dimensions: Dimension[];
  strengths: string[];
  barriers: Barrier[];
  warnings: string[];
  score_breakdown: ScoreBreakdown;
  metadata: Metadata;
}