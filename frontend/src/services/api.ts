import type {
  AccessibilityAnalysisResponse,
  AdaptationProposal,
  AdaptationRequest,
  AdaptedDocumentResponse,
  CreateTransformationOptions,
  DecisionLogEntry,
  DecisionRequest,
  ErrorDetail,
  ErrorDetailObject,
  ErrorResponse,
  ExportContentFormat,
  ExportDelivery,
  ExportReportFormat,
  FileDownloadResponse,
  FileInfo,
  FileUploadRequest,
  FileUploadResponse,
  FinalReportResponse,
  PresignedRequest,
  SensitiveFinding,
  ShareCreated,
  ShareCreateRequest,
  ShareInfo,
  TransformationDecisionRequest,
  TransformationRequest,
  TransformationResponse,
  ValidationErrorItem,
} from '../types/analysis';


const RAW_BASE_URL =
  import.meta.env?.VITE_API_URL || 'https://innovalab-educacion-e18-test.up.railway.app';

export const BASE_URL = `${RAW_BASE_URL.replace(/\/+$/, '').replace(/\/api\/v1$/, '')}/api/v1`;

// ============================================================================
// 1. Esquema uniforme de errores HTTP (Issue #42)
// ============================================================================

const STATUS_TO_ERROR_CODE: Record<number, string> = {
  0: 'network_error',
  400: 'bad_request',
  401: 'unauthorized',
  403: 'forbidden',
  404: 'not_found',
  405: 'method_not_allowed',
  408: 'request_timeout',
  409: 'conflict',
  413: 'payload_too_large',
  415: 'unsupported_media_type',
  422: 'unprocessable_entity',
  429: 'rate_limit_exceeded',
  500: 'internal_server_error',
  502: 'bad_gateway',
  503: 'service_unavailable',
  504: 'gateway_timeout',
};

const DEFAULT_STATUS_MESSAGES: Record<number, string> = {
  0: 'No se pudo conectar con el servidor. Verificá tu conexión a internet e intentá nuevamente.',
  400: 'Solicitud inválida. Revisá los datos enviados.',
  401: 'No autorizado. Iniciá sesión para continuar.',
  403: 'Acceso denegado. No tenés permisos para realizar esta acción.',
  404: 'El recurso solicitado no fue encontrado o ha expirado.',
  405: 'Método HTTP no permitido para este recurso.',
  408: 'Tiempo de espera de la solicitud agotado.',
  409: 'Conflicto con el estado actual del recurso.',
  413: 'El archivo supera el tamaño máximo permitido de 10 MB.',
  415: 'Formato o tipo de archivo no compatible.',
  422: 'La solicitud contiene datos no procesables o inválidos.',
  429: 'Demasiadas solicitudes. Esperá unos segundos antes de volver a intentar.',
  500: 'Error interno en el servidor.',
  502: 'Falla de comunicación con un servicio externo.',
  503: 'Servicio no disponible temporalmente. Intentá de nuevo en unos minutos.',
  504: 'Tiempo de respuesta del servicio externo agotado.',
};

export interface ApiErrorInit {
  status: number;
  code: string;
  message: string;
  detail?: ErrorDetail;
  findings?: SensitiveFinding[];
  total?: number;
  proposal_id?: string | null;
  retryAfterSeconds?: number | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: ErrorDetail;
  readonly findings?: SensitiveFinding[];
  readonly total?: number;
  readonly proposal_id?: string | null;
  readonly retryAfterSeconds?: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.detail = init.detail ?? null;
    this.findings = init.findings;
    this.total = init.total;
    this.proposal_id = init.proposal_id;
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isValidationErrorArray(value: unknown): value is ValidationErrorItem[] {
  return (
    Array.isArray(value) &&
    value.every((item) => isRecord(item) && typeof item.msg === 'string')
  );
}

function isSensitiveFindingsArray(value: unknown): value is SensitiveFinding[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        isRecord(item) &&
        typeof item.id === 'string' &&
        typeof item.label === 'string' &&
        typeof item.masked === 'string',
    )
  );
}

function formatValidationErrors(items: ValidationErrorItem[]): string {
  const messages = items
    .map((item) => item.msg.trim())
    .filter((msg) => msg.length > 0);
  return messages.length > 0
    ? `Error de validación: ${messages.join(' ')}`
    : 'Error de validación en los datos enviados.';
}

export function parseApiError(
  status: number,
  rawBody: unknown,
  retryAfterHeader?: string | null,
): ApiError {
  const defaultCode =
    STATUS_TO_ERROR_CODE[status] || (status >= 500 ? 'internal_server_error' : 'error');
  const defaultMessage =
    DEFAULT_STATUS_MESSAGES[status] ||
    (status >= 500
      ? 'Error interno en el servidor. Intentá nuevamente en unos instantes.'
      : `Ha ocurrido un error al procesar la solicitud (${status}).`);

  const parsedRetry =
    retryAfterHeader && !Number.isNaN(Number(retryAfterHeader))
      ? Number(retryAfterHeader)
      : null;

  if (isRecord(rawBody)) {
    const rawDetail = rawBody.detail;
    const detailObj: ErrorDetailObject | null = isRecord(rawDetail)
      ? (rawDetail as ErrorDetailObject)
      : null;

    let code = defaultCode;
    if (typeof rawBody.code === 'string' && rawBody.code.trim()) {
      code = rawBody.code.trim();
    } else if (detailObj && typeof detailObj.code === 'string' && detailObj.code.trim()) {
      code = detailObj.code.trim();
    } else if (isValidationErrorArray(rawDetail)) {
      code = 'validation_error';
    }

    let message = defaultMessage;
    if (typeof rawBody.message === 'string' && rawBody.message.trim()) {
      message = rawBody.message.trim();
    } else if (detailObj && typeof detailObj.message === 'string' && detailObj.message.trim()) {
      message = detailObj.message.trim();
    } else if (typeof rawDetail === 'string' && rawDetail.trim()) {
      message = rawDetail.trim();
    } else if (isValidationErrorArray(rawDetail)) {
      message = formatValidationErrors(rawDetail);
    }

    const findingsCandidate = rawBody.findings ?? detailObj?.findings;
    const findings = isSensitiveFindingsArray(findingsCandidate)
      ? findingsCandidate
      : undefined;

    const totalCandidate = rawBody.total ?? detailObj?.total;
    const total = typeof totalCandidate === 'number' ? totalCandidate : undefined;

    const proposalCandidate = rawBody.proposal_id ?? detailObj?.proposal_id;
    const proposal_id =
      typeof proposalCandidate === 'string' || proposalCandidate === null
        ? proposalCandidate
        : undefined;

    const normalizedDetail: ErrorDetail =
      typeof rawDetail === 'string' ||
      isValidationErrorArray(rawDetail) ||
      detailObj !== null
        ? (rawDetail as ErrorDetail)
        : (rawBody as ErrorDetailObject);

    return new ApiError({
      status,
      code,
      message,
      detail: normalizedDetail,
      findings,
      total,
      proposal_id,
      retryAfterSeconds: parsedRetry,
    });
  }

  if (typeof rawBody === 'string' && rawBody.trim()) {
    const trimmed = rawBody.trim();
    // Si el servidor devolvió una página HTML (p. ej. 502/504 de proxy), usar el mensaje en español
    const isHtml = trimmed.startsWith('<') && trimmed.endsWith('>');
    const message = isHtml ? defaultMessage : trimmed;
    return new ApiError({
      status,
      code: defaultCode,
      message,
      detail: trimmed,
      retryAfterSeconds: parsedRetry,
    });
  }

  return new ApiError({
    status,
    code: defaultCode,
    message: defaultMessage,
    detail: null,
    retryAfterSeconds: parsedRetry,
  });
}

// ============================================================================
// 2. Inyección de Token de Sesión (Clerk — Issue #101)
// ============================================================================

export type AuthTokenProvider = () =>
  | Promise<string | null | undefined>
  | string
  | null
  | undefined;

let authTokenProvider: AuthTokenProvider | null = null;

/**
- Configura el proveedor dinámico de token de sesión (por ejemplo, `() => getToken()` de Clerk).
- Se invoca automáticamente antes de cada request a la API.
 */
export function setAuthTokenProvider(provider: AuthTokenProvider | null): void {
  authTokenProvider = provider;
}

/**
- Configura un token de sesión estático (o lo limpia pasando `null`).
 */
export function setAuthToken(token: string | null): void {
  authTokenProvider = token ? () => token : null;
}

async function resolveAuthToken(explicitToken?: string | null): Promise<string | null> {
  if (explicitToken !== undefined) {
    return explicitToken && explicitToken.trim() ? explicitToken.trim() : null;
  }
  if (!authTokenProvider) {
    return null;
  }
  const token = await authTokenProvider();
  return token && token.trim() ? token.trim() : null;
}

// ============================================================================
// 3. Cliente HTTP Central
// ============================================================================

type QueryParamPrimitive = string | number | boolean | null | undefined;
type QueryParamValue = QueryParamPrimitive | ReadonlyArray<string | number | boolean>;
export type QueryParams = Record<string, QueryParamValue>;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  query?: QueryParams;
  body?: unknown;
  headers?: Record<string, string>;
  token?: string | null;
  signal?: AbortSignal;
  responseType?: 'json' | 'blob' | 'void';
}

export function buildApiUrl(path: string, query?: QueryParams): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${BASE_URL}${normalizedPath}`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item !== undefined && item !== null) {
            url.searchParams.append(key, String(item));
          }
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }

  return url.toString();
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  const retryAfter = response.headers.get('Retry-After');
  const text = await response.text().catch(() => '');
  let parsed: unknown = text;
  if (text) {
    try {
      parsed = JSON.parse(text) as ErrorResponse | Record<string, unknown>;
    } catch {
      parsed = text;
    }
  } else {
    parsed = null;
  }
  return parseApiError(response.status, parsed, retryAfter);
}

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    query,
    body,
    headers: customHeaders = {},
    token: explicitToken,
    signal,
    responseType = 'json',
  } = options;

  const url = buildApiUrl(path, query);
  const headers: Record<string, string> = {
    Accept: responseType === 'blob' ? '*/*' : 'application/json',
    ...customHeaders,
  };

  const bearerToken = await resolveAuthToken(explicitToken);
  if (bearerToken) {
    headers.Authorization = `Bearer ${bearerToken}`;
  }

  let requestBody: BodyInit | undefined;
  if (body instanceof FormData || body instanceof Blob || typeof body === 'string') {
    requestBody = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    requestBody = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: requestBody,
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError({
        status: 408,
        code: 'request_timeout',
        message: DEFAULT_STATUS_MESSAGES[408],
      });
    }
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: DEFAULT_STATUS_MESSAGES[0],
    });
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  if (responseType === 'void' || response.status === 204) {
    return undefined as T;
  }

  if (responseType === 'blob') {
    return (await response.blob()) as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError({
      status: response.status,
      code: 'invalid_response',
      message: 'El servidor devolvió una respuesta con formato inválido.',
      detail: text,
    });
  }
}

// ============================================================================
// 4. Módulo de Archivos (files) — Issues #62, #64 y #65
// ============================================================================

const EXTENSION_MIME_MAP: Record<string, string> = {
  '.pdf': 'application/pdf',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
};

function resolveFileContentType(file: File): string {
  const dotIdx = file.name.lastIndexOf('.');
  const ext = dotIdx !== -1 ? file.name.slice(dotIdx).toLowerCase() : '';
  if (EXTENSION_MIME_MAP[ext]) {
    return EXTENSION_MIME_MAP[ext];
  }
  if (file.type && file.type.trim()) {
    return file.type.trim().toLowerCase();
  }
  return 'application/octet-stream';
}

export type UploadFileStage = 'requesting_url' | 'uploading' | 'completing';

export interface UploadFileOptions {
  onStage?: (stage: UploadFileStage) => void;
  onProgress?: (percent: number) => void;
}

/**
- Solicita una URL firmada `PUT` para subir un archivo directo al almacenamiento (R2 o local).
 */
export async function requestUploadUrl(
  payload: FileUploadRequest,
): Promise<FileUploadResponse> {
  return apiRequest<FileUploadResponse>('/files/upload-url', {
    method: 'POST',
    body: payload,
  });
}

function putWithXhrProgress(
  url: string,
  method: string,
  headers: Record<string, string>,
  file: Blob | File,
  onProgress: (percent: number) => void,
): Promise<{ status: number; responseText: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    for (const [k, v] of Object.entries(headers)) {
      xhr.setRequestHeader(k, v);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      onProgress(100);
      resolve({ status: xhr.status, responseText: xhr.responseText || '' });
    };
    xhr.onerror = () => reject(new Error('network_error'));
    xhr.ontimeout = () => reject(new Error('timeout'));
    xhr.send(file);
  });
}

/**
- Sube los bytes del archivo directamente a la URL firmada devuelta por `requestUploadUrl`.
- Envía únicamente los headers firmados requeridos por el almacenamiento (sin Authorization Bearer).
 */
export async function uploadToPresignedUrl(
  upload: PresignedRequest | string,
  file: Blob | File,
  headers?: Record<string, string>,
  onProgress?: (percent: number) => void,
): Promise<void> {
  const targetUrl = typeof upload === 'string' ? upload : upload.url;
  const method = typeof upload === 'string' ? 'PUT' : upload.method;
  const signedHeaders =
    typeof upload === 'string' ? (headers ?? {}) : upload.headers;

  if (onProgress && typeof XMLHttpRequest !== 'undefined') {
    onProgress(0);
    let result: { status: number; responseText: string };
    try {
      result = await putWithXhrProgress(
        targetUrl,
        method,
        signedHeaders,
        file,
        onProgress,
      );
    } catch {
      throw new ApiError({
        status: 0,
        code: 'storage_upload_network_error',
        message:
          'No se pudo subir el archivo al almacenamiento. Verificá tu conexión e intentá nuevamente.',
      });
    }

    if (result.status < 200 || result.status >= 300) {
      let parsedBody: unknown = result.responseText;
      if (result.responseText) {
        try {
          parsedBody = JSON.parse(result.responseText) as unknown;
        } catch {
          parsedBody = result.responseText;
        }
      } else {
        parsedBody = null;
      }
      throw parseApiError(result.status, parsedBody);
    }
    return;
  }

  let response: Response;
  try {
    response = await fetch(targetUrl, {
      method,
      headers: signedHeaders,
      body: file,
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: 'storage_upload_network_error',
      message:
        'No se pudo subir el archivo al almacenamiento. Verificá tu conexión e intentá nuevamente.',
    });
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }
  onProgress?.(100);
}

/**
- Confirma en el backend que el archivo terminó de subirse y verifica su firma binaria y tamaño.
 */
export async function completeUpload(fileId: string): Promise<FileInfo> {
  return apiRequest<FileInfo>(`/files/${encodeURIComponent(fileId)}/complete`, {
    method: 'POST',
  });
}

/**
- Flujo completo de subida directa en 3 pasos:
- 1) `POST /files/upload-url` → 2) `PUT <presignedUrl>` → 3) `POST /files/{file_id}/complete`.
 */
export async function uploadFile(
  file: File,
  options?: UploadFileOptions,
): Promise<FileInfo> {
  options?.onStage?.('requesting_url');
  const ticket = await requestUploadUrl({
    filename: file.name,
    content_type: resolveFileContentType(file),
    size_bytes: file.size,
  });
  options?.onStage?.('uploading');
  await uploadToPresignedUrl(
    ticket.upload,
    file,
    undefined,
    options?.onProgress,
  );
  options?.onStage?.('completing');
  return completeUpload(ticket.file.file_id);
}

/**
- Consulta los metadatos y estado de un archivo por su `file_id`.
 */
export async function getFile(fileId: string): Promise<FileInfo> {
  return apiRequest<FileInfo>(`/files/${encodeURIComponent(fileId)}`);
}

/**
- Lista los archivos vigentes del usuario autenticado.
 */
export async function listFiles(): Promise<FileInfo[]> {
  return apiRequest<FileInfo[]>('/files');
}

/**
- Obtiene una URL firmada `GET` temporal para descargar el archivo con su nombre original.
 */
export async function getDownloadUrl(fileId: string): Promise<FileDownloadResponse> {
  return apiRequest<FileDownloadResponse>(
    `/files/${encodeURIComponent(fileId)}/download-url`,
  );
}

/**
- Elimina un archivo del usuario y revoca sus enlaces compartidos.
 */
export async function deleteFile(fileId: string): Promise<void> {
  return apiRequest<void>(`/files/${encodeURIComponent(fileId)}`, {
    method: 'DELETE',
    responseType: 'void',
  });
}

/**
- Crea un enlace corto revocable (`/s/{token}`) para compartir un archivo subido o exportado.
 */
export async function createShareLink(
  fileId: string,
  options?: ShareCreateRequest,
): Promise<ShareCreated> {
  return apiRequest<ShareCreated>(
    `/files/${encodeURIComponent(fileId)}/shares`,
    {
      method: 'POST',
      body: options && options.expires_in_hours != null ? options : undefined,
    },
  );
}

/**
- Lista los enlaces compartidos activos de un archivo junto con su contador de aperturas.
 */
export async function listShareLinks(fileId: string): Promise<ShareInfo[]> {
  return apiRequest<ShareInfo[]>(
    `/files/${encodeURIComponent(fileId)}/shares`,
  );
}

/**
- Revoca de inmediato un enlace compartido existente.
 */
export async function revokeShareLink(
  fileId: string,
  shareId: string,
): Promise<void> {
  return apiRequest<void>(
    `/files/${encodeURIComponent(fileId)}/shares/${encodeURIComponent(shareId)}`,
    {
      method: 'DELETE',
      responseType: 'void',
    },
  );
}

// ============================================================================
// 5. Módulo de Análisis de Accesibilidad (analysis)
// ============================================================================

export interface AnalysisQueryOptions {
  mock?: boolean;
  dismissed?: string[];
  confirm_images_without_personal_data?: boolean;
}

function normalizeAnalysisQuery(
  options?: AnalysisQueryOptions | boolean,
  includeConfirmImages: boolean = false,
): QueryParams {
  if (typeof options === 'boolean') {
    return { mock: options };
  }
  const mock = options?.mock ?? false;
  const query: QueryParams = { mock };

  if (options?.dismissed && options.dismissed.length > 0) {
    query.dismissed = options.dismissed;
  }
  if (
    includeConfirmImages &&
    options?.confirm_images_without_personal_data !== undefined
  ) {
    query.confirm_images_without_personal_data =
      options.confirm_images_without_personal_data;
  }
  return query;
}

/**
- Diagnóstico de accesibilidad de un texto educativo pegado (`POST /analysis/sample`).
 */
export async function analyzeSample(
  text: string,
  options: AnalysisQueryOptions | boolean = false,
): Promise<AccessibilityAnalysisResponse> {
  return apiRequest<AccessibilityAnalysisResponse>('/analysis/sample', {
    method: 'POST',
    query: normalizeAnalysisQuery(options, false),
    body: { text: text.trim() },
  });
}

/**
- Diagnóstico de accesibilidad de un archivo ya subido al almacenamiento por su `file_id` (`POST /analysis/files/{file_id}`).
 */
export async function analyzeFileById(
  fileId: string,
  options: AnalysisQueryOptions | boolean = false,
): Promise<AccessibilityAnalysisResponse> {
  return apiRequest<AccessibilityAnalysisResponse>(
    `/analysis/files/${encodeURIComponent(fileId)}`,
    {
      method: 'POST',
      query: normalizeAnalysisQuery(options, true),
    },
  );
}

/**
- Diagnóstico de accesibilidad enviando un archivo `.pdf`, `.docx` o `.pptx` por multipart (`POST /analysis/file`).
 */
export async function analyzeMultipartFile(
  file: File,
  options: AnalysisQueryOptions | boolean = false,
): Promise<AccessibilityAnalysisResponse> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<AccessibilityAnalysisResponse>('/analysis/file', {
    method: 'POST',
    query: normalizeAnalysisQuery(options, true),
    body: formData,
  });
}

/**
- Recupera un diagnóstico generado previamente por su `analysis_id` (`GET /analysis/{analysis_id}`).
 */
export async function getAnalysisById(
  analysisId: string,
): Promise<AccessibilityAnalysisResponse> {
  return apiRequest<AccessibilityAnalysisResponse>(
    `/analysis/${encodeURIComponent(analysisId)}`,
  );
}

/**
- Alias retrocompatible de `analyzeSample` (por defecto `useMock = true` para no alterar llamadas existentes).
 */
export async function analyzeText(
  text: string,
  useMock: boolean = true,
  dismissed?: string[],
): Promise<AccessibilityAnalysisResponse> {
  return analyzeSample(text, { mock: useMock, dismissed });
}

/**
- Alias retrocompatible que delega en `analyzeMultipartFile` (soporta `.pdf`, `.docx` y `.pptx`).
 */
export async function analyzePdf(
  file: File,
  useMock: boolean = true,
  options?: Omit<AnalysisQueryOptions, 'mock'>,
): Promise<AccessibilityAnalysisResponse> {
  return analyzeMultipartFile(file, {
    mock: useMock,
    dismissed: options?.dismissed,
    confirm_images_without_personal_data:
      options?.confirm_images_without_personal_data,
  });
}

// ============================================================================
// 6. Módulo de Adaptaciones con IA y Revisión Docente (adaptations)
// ============================================================================

export interface CreateAdaptationOptions {
  mock?: boolean;
  dismissed?: string[];
}

/**
- Genera una propuesta de adaptación con IA para una barrera del diagnóstico (`POST /adaptations`).
 */
export async function createAdaptationProposal(
  payload: AdaptationRequest,
  options: CreateAdaptationOptions | boolean = false,
): Promise<AdaptationProposal> {
  const query: QueryParams =
    typeof options === 'boolean'
      ? { mock: options }
      : {
          mock: options.mock ?? false,
          dismissed:
            options.dismissed && options.dismissed.length > 0
              ? options.dismissed
              : undefined,
        };

  return apiRequest<AdaptationProposal>('/adaptations', {
    method: 'POST',
    query,
    body: payload,
  });
}

/**
- Lista todas las propuestas de adaptación generadas para un diagnóstico (`GET /adaptations`).
 */
export async function listAdaptations(
  analysisId: string,
): Promise<AdaptationProposal[]> {
  return apiRequest<AdaptationProposal[]>('/adaptations', {
    query: { analysis_id: analysisId },
  });
}

/**
- Recupera una propuesta de adaptación puntual por su `proposal_id` (`GET /adaptations/{proposal_id}`).
 */
export async function getAdaptationProposal(
  proposalId: string,
): Promise<AdaptationProposal> {
  return apiRequest<AdaptationProposal>(
    `/adaptations/${encodeURIComponent(proposalId)}`,
  );
}

/**
- Registra la decisión docente (`aceptada`, `editada` o `descartada`) sobre una propuesta pendiente (`POST /adaptations/{proposal_id}/decision`).
 */
export async function decideAdaptation(
  proposalId: string,
  payload: DecisionRequest,
): Promise<AdaptationProposal> {
  return apiRequest<AdaptationProposal>(
    `/adaptations/${encodeURIComponent(proposalId)}/decision`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

/**
- Deshace la decisión vigente sobre una propuesta, devolviéndola a estado `pendiente` (`POST /adaptations/{proposal_id}/undo`).
 */
export async function undoAdaptation(
  proposalId: string,
): Promise<AdaptationProposal> {
  return apiRequest<AdaptationProposal>(
    `/adaptations/${encodeURIComponent(proposalId)}/undo`,
    {
      method: 'POST',
    },
  );
}

/**
- Obtiene el historial cronológico de decisiones y deshaceres de un diagnóstico (`GET /adaptations/decisions`).
 */
export async function listDecisions(
  analysisId: string,
): Promise<DecisionLogEntry[]> {
  return apiRequest<DecisionLogEntry[]>('/adaptations/decisions', {
    query: { analysis_id: analysisId },
  });
}

/**
- Construye la versión final del documento aplicando solo las propuestas aceptadas o editadas (`GET /adaptations/final-version`).
 */
export async function getAdaptedDocument(
  analysisId: string,
): Promise<AdaptedDocumentResponse> {
  return apiRequest<AdaptedDocumentResponse>('/adaptations/final-version', {
    query: { analysis_id: analysisId },
  });
}

/**
- Genera el informe ejecutivo de cierre con el puntaje antes/después y el detalle por barrera (`GET /adaptations/report`).
 */
export async function getFinalReport(
  analysisId: string,
): Promise<FinalReportResponse> {
  return apiRequest<FinalReportResponse>('/adaptations/report', {
    query: { analysis_id: analysisId },
  });
}

// ============================================================================
// 7. Módulo de Exportación (export) — Issues #40 y #62
// ============================================================================

/**
- Exporta el material adaptado en formato `docx`, `pdf`, `md` o `txt`.
- Por defecto usa `delivery = 'link'`, que guarda el archivo en almacenamiento y devuelve su URL firmada de descarga.
 */
export async function exportAdaptedContent(
  analysisId: string,
  format?: ExportContentFormat,
  delivery?: 'link',
): Promise<FileDownloadResponse>;
export async function exportAdaptedContent(
  analysisId: string,
  format: ExportContentFormat,
  delivery: 'file',
): Promise<Blob>;
export async function exportAdaptedContent(
  analysisId: string,
  format: ExportContentFormat = 'docx',
  delivery: ExportDelivery = 'link',
): Promise<FileDownloadResponse | Blob> {
  if (delivery === 'file') {
    return apiRequest<Blob>('/export/content', {
      query: { analysis_id: analysisId, format, delivery: 'file' },
      responseType: 'blob',
    });
  }
  return apiRequest<FileDownloadResponse>('/export/content', {
    query: { analysis_id: analysisId, format, delivery: 'link' },
  });
}

/**
- Exporta el informe ejecutivo de accesibilidad en formato `pdf`, `md` o `txt`.
- Por defecto usa `delivery = 'link'`, que guarda el archivo en almacenamiento y devuelve su URL firmada de descarga.
 */
export async function exportAccessibilityReport(
  analysisId: string,
  format?: ExportReportFormat,
  delivery?: 'link',
): Promise<FileDownloadResponse>;
export async function exportAccessibilityReport(
  analysisId: string,
  format: ExportReportFormat,
  delivery: 'file',
): Promise<Blob>;
export async function exportAccessibilityReport(
  analysisId: string,
  format: ExportReportFormat = 'pdf',
  delivery: ExportDelivery = 'link',
): Promise<FileDownloadResponse | Blob> {
  if (delivery === 'file') {
    return apiRequest<Blob>('/export/report', {
      query: { analysis_id: analysisId, format, delivery: 'file' },
      responseType: 'blob',
    });
  }
  return apiRequest<FileDownloadResponse>('/export/report', {
    query: { analysis_id: analysisId, format, delivery: 'link' },
  });
}

// ============================================================================
// 8. Módulo de Transformación de Material (transformations) — Issue #116
// ============================================================================

export async function createTransformation(
  payload: TransformationRequest,
  options: CreateTransformationOptions = {},
): Promise<TransformationResponse> {
  const query: QueryParams = {
    mock: options.mock ?? false,
  };
  if (options.dismissed && options.dismissed.length > 0) {
    query.dismissed = options.dismissed;
  }

  return apiRequest<TransformationResponse>('/transformations', {
    method: 'POST',
    query,
    body: payload,
  });
}

export async function listTransformations(): Promise<TransformationResponse[]> {
  return apiRequest<TransformationResponse[]>('/transformations');
}

export async function getTransformation(
  transformationId: string,
): Promise<TransformationResponse> {
  return apiRequest<TransformationResponse>(
    `/transformations/${encodeURIComponent(transformationId)}`,
  );
}

export async function decideTransformation(
  transformationId: string,
  payload: TransformationDecisionRequest,
): Promise<TransformationResponse> {
  return apiRequest<TransformationResponse>(
    `/transformations/${encodeURIComponent(transformationId)}/decision`,
    {
      method: 'POST',
      body: payload,
    },
  );
}

export async function retryTransformationFile(
  transformationId: string,
): Promise<TransformationResponse> {
  return apiRequest<TransformationResponse>(
    `/transformations/${encodeURIComponent(transformationId)}/file`,
    {
      method: 'POST',
    },
  );
}

export async function exportTransformation(
  transformationId: string,
  format: string,
  delivery: 'link',
): Promise<FileDownloadResponse>;
export async function exportTransformation(
  transformationId: string,
  format: string,
  delivery?: 'file',
): Promise<Blob>;
export async function exportTransformation(
  transformationId: string,
  format: string,
  delivery: 'file' | 'link' = 'file',
): Promise<FileDownloadResponse | Blob> {
  if (delivery === 'link') {
    return apiRequest<FileDownloadResponse>(
      `/transformations/${encodeURIComponent(transformationId)}/export`,
      {
        query: { format, delivery: 'link' },
      },
    );
  }
  return apiRequest<Blob>(
    `/transformations/${encodeURIComponent(transformationId)}/export`,
    {
      query: { format, delivery: 'file' },
      responseType: 'blob',
    },
  );
}

// ============================================================================
// 9. Texto a Voz de Prueba (AI TTS) — Issue #121
// ============================================================================

export interface TestTtsOptions {
  mock?: boolean;
}

export interface TestTtsResult {
  blob: Blob;
  audioUrl: string;
  durationSeconds?: string | null;
  chunks?: string | null;
  model?: string | null;
}

/**
- Convierte un texto corto (1..1000 caracteres) en audio MP3 (`POST /api/v1/ai/test-tts`).
 */
export async function synthesizeTestAudio(
  text: string,
  options: TestTtsOptions = {},
): Promise<TestTtsResult> {
  const cleanText = text.trim().slice(0, 1000);
  if (!cleanText) {
    throw new ApiError({
      status: 400,
      code: 'empty_tts_text',
      message: 'No hay texto disponible para generar el audio.',
    });
  }

  const url = buildApiUrl('/ai/test-tts', {
    mock: options.mock ?? false,
  });

  const headers: Record<string, string> = {
    Accept: 'audio/mpeg, */*',
    'Content-Type': 'application/json',
  };

  const bearerToken = await resolveAuthToken();
  if (bearerToken) {
    headers.Authorization = `Bearer ${bearerToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text: cleanText }),
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: DEFAULT_STATUS_MESSAGES[0],
    });
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  const blob = await response.blob();
  const audioUrl = URL.createObjectURL(blob);

  return {
    blob,
    audioUrl,
    durationSeconds: response.headers.get('X-Audio-Duration'),
    chunks: response.headers.get('X-Audio-Chunks'),
    model: response.headers.get('X-TTS-Model'),
  };
}