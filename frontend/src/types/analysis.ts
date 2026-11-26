// ============================================================================
// Contratos TypeScript de la API (/api/v1/openapi.json) — Issue #144
// ============================================================================

export type Category = 'comprension' | 'estructura' | 'accesibilidad_visual';
export type DimensionStatus = 'correcta' | 'para_revisar' | 'barrera_detectada';
export type Severity = 'para_revisar' | 'barrera_detectada';
export type BarrierSource = 'ai' | 'rules';
export type SourceType = 'pdf' | 'text' | 'docx' | 'pptx';

export type AdaptationType =
  | 'lenguaje_claro'
  | 'consigna_en_pasos'
  | 'reorganizar'
  | 'mejorar_estructura';

export type ProposalStatus = 'pendiente' | 'aceptada' | 'editada' | 'descartada';
export type DecisionType = 'aceptada' | 'editada' | 'descartada';
export type DecisionAction = 'decision' | 'deshacer';
export type BarrierResolutionStatus = 'aceptada' | 'editada' | 'descartada' | 'pendiente';

export type ExportContentFormat = 'docx' | 'pdf' | 'md' | 'txt';
export type ExportReportFormat = 'pdf' | 'md' | 'txt';
export type ExportDelivery = 'file' | 'link';

// ----------------------------------------------------------------------------
// 1. Diagnóstico de Accesibilidad (backend/app/schemas/analysis.py)
// ----------------------------------------------------------------------------

export interface DimensionAssessment {
  category: Category | string;
  status: DimensionStatus;
  comment: string;
}

/** Alias retrocompatible para componentes existentes */
export type Dimension = DimensionAssessment;

export interface BarrierReport {
  id: string;
  category: Category | string;
  severity: Severity;
  issue: string;
  original_text?: string;
  explanation: string;
  recommendation: string;
  suggested_rewrite?: string | null;
  fragment_found: boolean | null;
  source: BarrierSource;
}

/** Alias retrocompatible para componentes existentes */
export type Barrier = BarrierReport;

export interface AltTextProposal {
  image_index: number;
  page_number: number;
  location_description: string;
  suggested_alt_text: string;
  pedagogical_purpose?: string | null;
  context_used: string;
}

export interface RulesMetrics {
  analyzed_word_count: number;
  sentence_count: number;
  long_sentences: number;
  severe_long_sentences: number;
  max_sentence_words: number;
  paragraph_count: number;
  long_paragraphs: number;
  severe_long_paragraphs: number;
  heading_count: number;
  hierarchy_levels: number;
  list_items_count: number;
  multi_action_prompts: number;
  readability_score_szigriszt?: number | null;
  visual_only_references: number;
  body_font_size_pt?: number | null;
  small_text_passages: number;
  low_contrast_passages: number;
}

export interface ScorePenalty {
  rule: string;
  category: Category | string;
  count: number;
  points: number;
}

export interface ScoreBreakdown {
  ai_score: number | null;
  rules_score: number;
  ai_weight: number;
  rules_weight: number;
  penalties: ScorePenalty[];
  cap?: number | null;
  cap_reason?: string | null;
  final_score: number;
}

export interface AnalysisMetadata {
  provider: string;
  model: string;
  connection: string;
  latency_ms: number;
  source_type: SourceType;
  filename?: string | null;
  page_count: number;
  image_count: number;
  prompt_tokens?: number | null;
  output_tokens?: number | null;
  thinking_tokens?: number | null;
  total_tokens?: number | null;
  analyzed_word_count: number;
  is_truncated: boolean;
  unverified_fragments: number;
  rules_metrics?: RulesMetrics | null;
}

/** Alias retrocompatible para componentes existentes */
export type Metadata = AnalysisMetadata;

export interface AccessibilityAnalysisResponse {
  analysis_id: string | null;
  expires_at: string | null;
  estimated_score: number;
  summary: string;
  dimensions: DimensionAssessment[];
  strengths: string[];
  barriers: BarrierReport[];
  alt_text_proposals: AltTextProposal[];
  warnings: string[];
  score_breakdown: ScoreBreakdown | null;
  metadata: AnalysisMetadata;
}

/** Alias retrocompatible para componentes existentes */
export type AnalysisResponse = AccessibilityAnalysisResponse;

// ----------------------------------------------------------------------------
// 2. Adaptaciones, Decisiones, Versión Final e Informe (backend/app/schemas/adaptation.py)
// ----------------------------------------------------------------------------

export interface AdaptationRequest {
  analysis_id: string;
  barrier_id: string;
  adaptation_type: AdaptationType;
  fragment?: string | null;
}

export interface AdaptationMetadata {
  provider: string;
  model: string;
  connection: string;
  latency_ms: number;
  prompt_tokens?: number | null;
  output_tokens?: number | null;
  thinking_tokens?: number | null;
  total_tokens?: number | null;
}

export interface AdaptationProposal {
  proposal_id: string;
  analysis_id: string;
  barrier_id: string;
  adaptation_type: AdaptationType;
  status: ProposalStatus;
  original_text: string;
  fragment_source: 'barrier' | 'request';
  proposed_text: string;
  explanation: string;
  preserved_objective: string;
  edited_text?: string | null;
  final_text?: string | null;
  decided_at?: string | null;
  warnings: string[];
  created_at: string;
  expires_at: string;
  metadata: AdaptationMetadata;
}

export interface DecisionRequest {
  decision: DecisionType;
  edited_text?: string | null;
}

export interface DecisionLogEntry {
  proposal_id: string;
  barrier_id: string;
  adaptation_type: AdaptationType;
  action: DecisionAction;
  from_status: ProposalStatus;
  to_status: ProposalStatus;
  edited_text?: string | null;
  created_at: string;
}

export interface AdaptedDocumentResponse {
  analysis_id: string;
  original_text: string;
  adapted_text: string;
  total_proposals: number;
  applied_count: number;
  discarded_count: number;
  pending_count: number;
  applied_proposals: string[];
  warnings: string[];
}

export interface BarrierResolutionDetail {
  barrier_id: string;
  category: Category | string;
  severity: Severity | string;
  issue: string;
  original_text: string;
  resolution_status: BarrierResolutionStatus;
  final_text?: string | null;
  proposal_id?: string | null;
}

export interface FinalReportResponse {
  analysis_id: string;
  generated_at: string;
  score_before: number;
  score_after: number;
  score_delta: number;
  score_breakdown_before?: ScoreBreakdown | null;
  score_breakdown_after?: ScoreBreakdown | null;
  disclaimer: string;
  executive_summary: string[];
  total_barriers: number;
  resolved_count: number;
  discarded_count: number;
  pending_count: number;
  total_proposals: number;
  barriers_detail: BarrierResolutionDetail[];
  warnings: string[];
}

// ----------------------------------------------------------------------------
// 3. Archivos y Enlaces Compartidos (backend/app/schemas/file.py)
// ----------------------------------------------------------------------------

export type FileKind = 'upload' | 'export';
export type FileUploadStatus = 'pending' | 'uploaded';

export interface FileUploadRequest {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface PresignedRequest {
  url: string;
  method: 'PUT' | 'GET';
  headers: Record<string, string>;
  expires_in_seconds: number;
}

export interface FileInfo {
  file_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  kind: FileKind;
  status: FileUploadStatus;
  created_at: string;
  uploaded_at: string | null;
  expires_at: string;
}

export interface FileUploadResponse {
  file: FileInfo;
  upload: PresignedRequest;
}

export interface FileDownloadResponse {
  file: FileInfo;
  download: PresignedRequest;
}

export interface ShareCreateRequest {
  expires_in_hours?: number | null;
}

export interface ShareInfo {
  share_id: string;
  created_at: string;
  expires_at: string;
  access_count: number;
  last_access_at: string | null;
}

export interface ShareCreated extends ShareInfo {
  url: string;
}

// ----------------------------------------------------------------------------
// 4. Manejo Uniforme de Errores y Datos Sensibles (Issues #42 y #66)
// ----------------------------------------------------------------------------

export type SensitiveFindingType = 'dni' | 'cuil' | 'nombre_rotulado' | 'calificacion';

export interface SensitiveFinding {
  id: string;
  type: SensitiveFindingType | string;
  label: string;
  masked: string;
  line: number;
}

export interface ValidationErrorItem {
  type?: string;
  loc: ReadonlyArray<string | number>;
  msg: string;
  input?: unknown;
}

export interface ErrorDetailObject {
  code?: string;
  message?: string;
  detail?: string;
  findings?: SensitiveFinding[];
  total?: number;
  proposal_id?: string | null;
  [key: string]: unknown;
}

export type ErrorDetail =
  | string
  | ErrorDetailObject
  | ValidationErrorItem[]
  | null
  | undefined;

export interface ErrorResponse {
  code: string;
  message: string;
  detail?: ErrorDetail;
  findings?: SensitiveFinding[];
  total?: number;
  proposal_id?: string | null;
}

// ----------------------------------------------------------------------------
// 5. Transformar Material (backend/app/schemas/transformation.py — Issue #116)
// ----------------------------------------------------------------------------

export type TransformationFormat = 'no_images' | 'mind_map' | 'infographic' | 'audio';
export type TransformationJobStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type TransformationReviewStatus = 'pendiente' | 'aceptada' | 'editada' | 'descartada';
export type TransformationDecisionType = 'aceptada' | 'editada' | 'descartada';

export interface TransformationRequest {
  format: TransformationFormat;
  analysis_id?: string | null;
  file_id?: string | null;
}

export interface TransformationSource {
  type: 'analysis' | 'file';
  id: string;
}

export interface TransformationErrorInfo {
  code: string;
  message: string;
}

export interface GeneratedFileInfo {
  filename: string;
  content_type: string;
  size_bytes: number;
  preview_url?: string | null;
  expires_in_seconds?: number | null;
  file_id?: string | null;
}

export interface TransformationProgressInfo {
  done: number;
  total: number;
}

export interface TransformationResponse {
  transformation_id: string;
  format: TransformationFormat;
  source: TransformationSource;
  status: TransformationJobStatus;
  review_status: TransformationReviewStatus;
  result?: Record<string, unknown> | null;
  edited_result?: Record<string, unknown> | null;
  final_result?: Record<string, unknown> | null;
  file?: GeneratedFileInfo | null;
  extra_files: GeneratedFileInfo[];
  progress?: TransformationProgressInfo | null;
  views?: Record<string, string> | null;
  error?: TransformationErrorInfo | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
  decided_at?: string | null;
  expires_at: string;
  metadata?: AdaptationMetadata | null;
}

export interface TransformationDecisionRequest {
  decision: TransformationDecisionType;
  edited_result?: Record<string, unknown> | null;
}

export interface CreateTransformationOptions {
  mock?: boolean;
  dismissed?: string[];
}
