/**
 * TypeScript types generated from FastAPI backend
 *
 * These types match the Pydantic models in ignition_toolkit/api/app.py
 */

export interface ParameterInfo {
  name: string;
  type: string;
  required: boolean;
  default: string | null;
  description: string;
}

export interface StepInfo {
  id: string;
  name: string;
  type: string;
  timeout: number;
  retry_count: number;
}

export interface PlaybookInfo {
  name: string;
  path: string;
  version: string;
  description: string;
  parameter_count: number;
  step_count: number;
  parameters: ParameterInfo[];
  steps: StepInfo[];
  // Metadata fields
  domain: string | null;  // Playbook domain (gateway, designer, perspective)
  group: string | null;  // Playbook group for UI organization (e.g., "Gateway (Base Playbooks)")
  revision: number;
  verified: boolean;
  enabled: boolean;
  last_modified: string | null;
  verified_at: string | null;
  last_committed_at: string | null;
  // PORTABILITY v4: Origin tracking
  origin: string;  // built-in, user-created, duplicated, unknown
  duplicated_from: string | null;  // Source playbook path if duplicated
  created_at: string | null;  // When playbook was created/added
  relevant_timeouts: string[];  // Timeout categories applicable to this playbook
}

export interface TimeoutOverrides {
  gateway_restart?: number;   // seconds (default: 120)
  module_install?: number;    // seconds (default: 300)
  browser_operation?: number; // milliseconds (default: 30000)
  designer_launch?: number;   // seconds (default: 60)
}

export interface ExecutionRequest {
  playbook_path: string;
  parameters: Record<string, string | number | boolean>;
  gateway_url?: string;
  credential_name?: string;
  debug_mode?: boolean;
  timeout_overrides?: TimeoutOverrides;
}

export interface ExecutionResponse {
  execution_id: string;
  status: string;
  message: string;
}

export interface ExecutionStatusResponse {
  execution_id: string;
  playbook_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  current_step_index: number | null;
  total_steps: number;
  error: string | null;
  debug_mode?: boolean;
  step_results?: StepResult[] | null;
  domain?: string | null;  // Playbook domain (gateway, designer, perspective)
}

export interface CredentialInfo {
  name: string;
  username: string;
  gateway_url?: string;
  description?: string;
}

export interface CredentialCreate {
  name: string;
  username: string;
  password: string;
  gateway_url?: string;
  description?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

// WebSocket message types
export interface NestedStepResult {
  step_id: string;
  step_name: string;
  status: string;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  output?: Record<string, unknown>;
  nested_steps?: NestedStepResult[];
}

export interface StepResult {
  step_id: string;
  step_name: string;
  status: string;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  output?: {
    _output?: string;
    [key: string]: unknown;
  };
  nested_steps?: NestedStepResult[];
}

export interface ExecutionUpdate {
  execution_id: string;
  playbook_name: string;
  status: string;
  current_step_index: number | null;
  total_steps: number;
  error: string | null;
  debug_mode?: boolean;
  started_at: string | null;
  completed_at: string | null;
  step_results: StepResult[];
  domain?: string | null;  // Playbook domain (gateway, designer, perspective)
}

export interface ScreenshotFrame {
  executionId: string;
  screenshot: string; // base64 encoded JPEG
  timestamp: string;
}

export interface WebSocketMessage {
  type: 'execution_update' | 'screenshot_frame' | 'pong' | 'keepalive' | 'error' | 'batch';
  data?: ExecutionUpdate | ScreenshotFrame;
  error?: string;
  // Batch message fields (for high-frequency updates like screenshots)
  messages?: WebSocketMessage[];
  count?: number;
}

// Enums
export type ExecutionStatus =
  | 'pending'
  | 'started'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped';

export type ParameterType =
  | 'string'
  | 'integer'
  | 'float'
  | 'boolean'
  | 'file'
  | 'credential'
  | 'list'
  | 'dict'
  | 'selector';

// CloudDesigner types
export interface DockerStatus {
  installed: boolean;
  running: boolean;
  version?: string;
  docker_path?: string;
}

export interface CloudDesignerStatus {
  status: 'running' | 'exited' | 'paused' | 'restarting' | 'created' | 'not_created' | 'unknown';
  port?: number;
  error?: string;
}

export interface CloudDesignerStartResponse {
  success: boolean;
  output?: string;
  error?: string;
}

export interface CloudDesignerStopResponse {
  success: boolean;
  output?: string;
  error?: string;
}

export interface CloudDesignerConfig {
  compose_dir: string;
  compose_dir_exists: boolean;
  container_name: string;
  default_port: number;
}

// Health and Diagnostics types
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

export interface ComponentHealth {
  status: HealthStatus;
  message: string;
  last_checked: string;
  error?: string;
}

export interface DetailedHealthResponse {
  status: HealthStatus;
  ready: boolean;
  startup_time: string;
  uptime_seconds: number;
  errors: string[];
  warnings: string[];
  components: {
    database: ComponentHealth;
    vault: ComponentHealth;
    playbooks: ComponentHealth;
    browser: ComponentHealth;
    frontend: ComponentHealth;
    scheduler: ComponentHealth;
  };
}

export interface DatabaseStats {
  db_file: string;
  db_size_bytes: number;
  db_size_readable: string;
  execution_count: number;
  step_result_count: number;
  oldest_execution: string | null;
  newest_execution: string | null;
  status_counts: Record<string, number>;
}

export interface StorageStats {
  screenshots_directory: string;
  total_size_bytes: number;
  total_size_readable: string;
  file_count: number;
  oldest_screenshot: string | null;
  newest_screenshot: string | null;
}

export interface CleanupResult {
  dry_run: boolean;
  older_than_days: number;
  executions_deleted: number;
  screenshots_deleted: number;
  space_freed_bytes: number;
  space_freed_readable: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  execution_id: string | null;
}

export interface LogStats {
  total_captured: number;
  max_entries: number;
  level_counts: Record<string, number>;
  oldest_entry: string | null;
  newest_entry: string | null;
}

// Step Type metadata for form-based playbook editor
export interface StepTypeParameter {
  name: string;
  type: string;  // string, integer, float, boolean, credential, file, list, dict, selector
  required: boolean;
  default: string | number | boolean | null;
  description: string;
  options?: string[];  // For enum-like parameters
}

export interface StepTypeInfo {
  type: string;
  domain: string;
  description: string;
  parameters: StepTypeParameter[];
}

export interface StepTypesResponse {
  step_types: StepTypeInfo[];
  domains: string[];
}

// Exchange scraper types
export interface ExchangeItem {
  id: string;
  url: string;
  title: string;
  contributor: string;
  category: string;
  download_count: number;
  version: string;
  updated_date: string;
  tagline: string;
  scraped_at: string;
}

export interface ExchangeStatus {
  status: string;
  is_running: boolean;
  last_run: string | null;
  last_error: string | null;
  item_count: number;
  progress_current: number;
  progress_total: number;
}

export interface ExchangeChanges {
  new: ExchangeItem[];
  updated: ExchangeItem[];
  removed: ExchangeItem[];
}

export interface ExchangeHistoryEntry {
  timestamp: string;
  success: boolean;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  items_scraped: number;
  changes: { new: number; updated: number; removed: number };
  error: string | null;
}

export interface ExchangeConfig {
  headless: boolean;
  max_resources: number;
  schedule: { enabled: boolean; cron: string };
}
