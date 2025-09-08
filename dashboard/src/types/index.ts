// Updated session types for EP-0010 (SessionOverview model)
export interface Session {
  session_id: string;
  alert_id: string;
  alert_type: string | null;
  agent_type: string;
  status: 'completed' | 'failed' | 'in_progress' | 'pending';
  started_at_us: number; // Unix timestamp (microseconds since epoch)
  completed_at_us: number | null; // Unix timestamp (microseconds since epoch)
  duration_ms: number | null; // Computed property from backend
  error_message: string | null;
  
  // Interaction counts (now always present)
  llm_interaction_count: number;
  mcp_communication_count: number;
  total_interactions: number;
  
  // Chain information (now always present since all sessions are chains)
  chain_id: string;
  total_stages: number | null;
  completed_stages: number | null;
  failed_stages: number;
  current_stage_index: number | null;
  
  // NEW: Session-level token aggregations (EP-0009)
  session_input_tokens: number | null;
  session_output_tokens: number | null;  
  session_total_tokens: number | null;
}

// Phase 5: Interaction summary for stages
export interface InteractionSummary {
  llm_count: number;
  mcp_count: number;
  total_count: number;
  duration_ms: number | null;
}

// Updated stage execution for EP-0010 (DetailedStage model)
export interface StageExecution {
  execution_id: string;
  session_id: string;
  stage_id: string;
  stage_index: number;
  stage_name: string;
  agent: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  started_at_us: number | null;
  completed_at_us: number | null;
  duration_ms: number | null;
  stage_output: any | null;
  error_message: string | null;
  
  // Direct interaction arrays (EP-0010 structure)
  llm_interactions: LLMInteractionDetail[];
  mcp_communications: MCPInteractionDetail[];
  
  // Summary counts
  llm_interaction_count: number;
  mcp_communication_count: number;
  total_interactions: number;
  
  // Computed properties (available from backend)
  stage_interactions_duration_ms: number | null;
  chronological_interactions: InteractionDetail[];
  
  // NEW: Stage-level token aggregations (EP-0009)
  stage_input_tokens?: number | null;
  stage_output_tokens?: number | null;
  stage_total_tokens?: number | null;
}

// Updated detailed session for EP-0010 (DetailedSession model)
export interface DetailedSession extends Session {
  // Full session details
  alert_data: AlertData;
  final_analysis: string | null;
  session_metadata: { [key: string]: any } | null;
  
  // Chain execution details (moved to top level)
  chain_definition: any;
  current_stage_id: string | null;
  
  // Explicit chain properties (inherited from Session but made explicit for clarity)
  // These are already in Session interface but listed here for explicit typing
  chain_id: string;
  current_stage_index: number | null;
  
  // Stage executions with all their interactions (EP-0010 improvement)
  stages: StageExecution[];
}

// Flexible alert data structure supporting any fields
export interface AlertData {
  [key: string]: any; // Can contain any fields
}

// EP-0010: Updated interaction structures matching backend models

// Base interaction fields (shared by LLM and MCP)
export interface BaseInteraction {
  id: string;                    // Same as event_id (legacy field)
  event_id: string;
  timestamp_us: number;
  step_description: string;
  duration_ms: number | null;
  stage_execution_id?: string | null;
}

// LLM message structure (from backend) - EP-0014 enhanced
export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

// LLM conversation structure (EP-0014)
export interface LLMConversation {
  messages: LLMMessage[];
}

// LLM event details (EP-0014 structure with conversation field)
export interface LLMEventDetails {
  // EP-0014: New conversation field replaces messages array
  conversation?: LLMConversation;
  // Legacy messages field for backward compatibility during transition
  messages?: LLMMessage[];
  
  model_name: string;
  temperature: number | null;
  success: boolean;
  error_message: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  tool_calls: any | null;
  tool_results: any | null;
}

// MCP event details (EP-0010 structure)  
export interface MCPEventDetails {
  tool_name?: string | null;
  server_name: string;
  communication_type: string;
  parameters?: Record<string, any> | null;
  result?: Record<string, any> | null;
  available_tools?: Record<string, any> | null;
  success: boolean;
}

// Complete interaction types (EP-0010)
export interface LLMInteractionDetail extends BaseInteraction {
  type: 'llm';
  details: LLMEventDetails;
}

export interface MCPInteractionDetail extends BaseInteraction {
  type: 'mcp';
  details: MCPEventDetails;
}

// Union type for all interactions
export type InteractionDetail = LLMInteractionDetail | MCPInteractionDetail;

// Legacy timeline item for backward compatibility
export interface TimelineItem {
  event_id: string;
  type: 'llm' | 'mcp' | 'system';
  timestamp_us: number;
  step_description: string;
  duration_ms: number | null;
  details?: LLMEventDetails | MCPEventDetails | SystemEvent;
}

// Legacy interaction types for backward compatibility (aliased to new types)
export type LLMInteraction = LLMEventDetails;
export type MCPInteraction = MCPEventDetails;

// Phase 3: System event details
export interface SystemEvent {
  event_type: string;
  description: string;
  metadata?: Record<string, any>;
}

// Pagination information from backend
export interface Pagination {
  page: number;
  page_size: number;
  total_pages: number;
  total_items: number;
}

// Filters applied (for future phases)
export interface FiltersApplied {
  [key: string]: any;
}

// Sessions endpoint response (actual backend format)
export interface SessionsResponse {
  sessions: Session[];
  pagination: Pagination;
  filters_applied: FiltersApplied;
}

// WebSocket message types (Phase 2 + Phase 5)
export interface WebSocketMessage {
  type: 'session_update' | 'session_completed' | 'session_failed' | 'ping' | 'pong' | 'connection_established' | 'subscription_response' | 'dashboard_update' | 'message_batch' | 'session_status_change' | 'batched_session_updates' | 'chain_progress' | 'stage_progress';
  data?: SessionUpdate | ChainProgressUpdate | StageProgressUpdate | any; // Allow any data type for dashboard_update messages
  timestamp_us?: number; // Unix timestamp (microseconds since epoch)
  channel?: string; // Dashboard updates include channel info
  messages?: WebSocketMessage[]; // For message_batch type
  count?: number; // For message_batch type
  timestamp?: string; // Alternative timestamp format for batches
}

export interface SessionUpdate {
  session_id: string;
  status: Session['status'];
  progress?: number; // 0-100 for in_progress sessions
  duration_ms?: number;
  error_message?: string | null;
  completed_at_us?: number | null; // Unix timestamp (microseconds since epoch)
  data?: any; // Additional update data containing interaction_type, etc.
}

// Phase 5: Chain progress update from WebSocket
export interface ChainProgressUpdate {
  session_id: string;
  chain_id: string;
  current_stage?: string | null;
  current_stage_index?: number | null;
  total_stages?: number | null;
  completed_stages?: number | null;
  failed_stages?: number | null;
  overall_status: 'pending' | 'processing' | 'completed' | 'failed' | 'partial';
  stage_details?: any | null;
  timestamp_us: number;
}

// Phase 5: Stage progress update from WebSocket
export interface StageProgressUpdate {
  session_id: string;
  chain_id: string;
  stage_execution_id: string;
  stage_id: string; // Logical stage identifier (e.g., 'initial-analysis')
  stage_name: string;
  stage_index: number;
  agent: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  started_at_us?: number | null;
  completed_at_us?: number | null;
  duration_ms?: number | null;
  error_message?: string | null;
  iteration_strategy?: string | null;
  timestamp_us: number;
}

// API response wrapper format (for other endpoints)
export interface APIResponse<T> {
  data: T;
  error?: string;
  timestamp_us?: number; // Unix timestamp (microseconds since epoch)
}

// Status badge props
export interface StatusBadgeProps {
  status: Session['status'];
  size?: 'small' | 'medium';
}

// Alert list component props (Phase 1)
export interface AlertListProps {
  loading?: boolean;
  error?: string | null;
  sessions?: Session[];
  onRefresh?: () => void;
}

// Individual alert list item props (Phase 1, enhanced for Phase 4)
export interface AlertListItemProps {
  session: Session;
  onClick?: (sessionId: string) => void;
  // Phase 4: Search highlighting
  searchTerm?: string;
}

// Active alerts panel props (Phase 2)
export interface ActiveAlertsPanelProps {
  sessions?: Session[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  onSessionClick?: (sessionId: string) => void;
}

// Active alert card props (Phase 2)
export interface ActiveAlertCardProps {
  session: Session;
  progress?: number;
  onClick?: (sessionId: string) => void;
}

// Historical alerts list props (Phase 2, enhanced for Phase 4)
export interface HistoricalAlertsListProps {
  sessions?: Session[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  onSessionClick?: (sessionId: string) => void;
  // Phase 4: Filter-related props
  filters?: SessionFilter;
  filteredCount?: number;
}

// Dashboard layout props (Phase 2, enhanced for Phase 6)
export interface DashboardLayoutProps {
  activeAlerts: Session[];
  historicalAlerts: Session[];
  activeLoading?: boolean;
  historicalLoading?: boolean;
  activeError?: string | null;
  historicalError?: string | null;
  onRefreshActive?: () => void;
  onRefreshHistorical?: () => void;
  onSessionClick?: (sessionId: string) => void;
  // Phase 4: Filter-related props
  filters?: SessionFilter;
  filteredCount?: number;
  // Phase 6: Sorting and pagination props
  sortState?: SortState;
  onSortChange?: (field: string) => void;
  pagination?: PaginationState;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
}

// Phase 3: Session detail page props
export interface SessionDetailPageProps {
  sessionId: string;
}

// Phase 3: Session header props
export interface SessionHeaderProps {
  session: DetailedSession;
  onRefresh?: () => void;
}

// Phase 3: Original alert card props
export interface OriginalAlertCardProps {
  alertData: AlertData;
}

// Phase 3: Final analysis card props
export interface FinalAnalysisCardProps {
  analysis: string | null;
  sessionStatus: Session['status'];
  errorMessage?: string | null;
}

// Phase 3: Timeline props
export interface SimpleTimelineProps {
  timelineItems: TimelineItem[];
}

// Phase 3: Back button props
export interface BackButtonProps {
  onClick: () => void;
}

// Phase 4: Search and filtering types
export interface SessionFilter {
  search?: string; // Text search across alert types and error messages
  status?: ('completed' | 'failed' | 'in_progress' | 'pending')[]; // Status filter (multiple selection)
  agent_type?: string[]; // Agent type filter (backend expects single value, but UI can select multiple - first is used) 
  alert_type?: string[]; // Alert type filter (backend expects single value, but UI can select multiple - first is used)
  start_date?: string | null; // Start date filter (ISO string)
  end_date?: string | null; // End date filter (ISO string)
  time_range_preset?: string | null; // Preset time range (e.g., '1h', '1d', '7d')
}

// Phase 4: Filter options from backend
export interface FilterOptions {
  agent_types: string[]; // Available agent types
  alert_types: string[]; // Available alert types
  status_options: ('completed' | 'failed' | 'in_progress' | 'pending')[]; // Available status options
}

// Phase 4: Search results with highlighting
export interface SearchResult {
  sessions: Session[];
  total_count: number;
  search_term?: string;
  highlighted_results?: Record<string, string>; // session_id -> highlighted content
}

// Phase 4Component props for filtering
export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch: (searchTerm: string) => void;
  placeholder?: string;
  debounceMs?: number;
}

export interface StatusFilterProps {
  value: string[];
  onChange: (statuses: string[]) => void;
  options?: string[];
}

export interface FilterBarProps {
  filters: SessionFilter;
  onFiltersChange: (filters: SessionFilter) => void;
  onClearFilters: () => void;
  loading?: boolean;
}

// Phase 4: Enhanced historical alerts list with filtering
export interface EnhancedHistoricalAlertsListProps extends HistoricalAlertsListProps {
  filters?: SessionFilter;
  filteredCount?: number;
  searchTerm?: string;
  // Phase 6: Sorting and pagination
  sortState?: SortState;
  onSortChange?: (field: string) => void;
  pagination?: PaginationState;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
}

// Updated interaction details props for EP-0010
export interface InteractionDetailsProps {
  type: 'llm' | 'mcp' | 'system';
  details: LLMEventDetails | MCPEventDetails | SystemEvent;
  expanded?: boolean;
}

export interface ProgressIndicatorProps {
  status: 'completed' | 'failed' | 'in_progress' | 'pending';
  startedAt?: number; // Unix timestamp in microseconds
  duration?: number | null; // Duration in milliseconds
  variant?: 'linear' | 'circular';
  showDuration?: boolean;
  size?: 'small' | 'medium' | 'large';
}

export interface CopyButtonProps {
  text: string;
  variant?: 'button' | 'icon';
  size?: 'small' | 'medium' | 'large';
  label?: string;
  tooltip?: string;
}

// Phase 6: Advanced filtering and pagination types
export interface PaginationState {
  page: number; // Current page (1-based)
  pageSize: number; // Items per page
  totalPages: number; // Total number of pages
  totalItems: number; // Total number of items
}

export interface SortState {
  field: string; // Field to sort by
  direction: 'asc' | 'desc'; // Sort direction
}

export interface FilterPanelProps {
  filters: SessionFilter;
  onFiltersChange: (filters: SessionFilter) => void;
  onClearFilters: () => void;
  filterOptions?: FilterOptions;
  loading?: boolean;
  showAdvanced?: boolean;
  onToggleAdvanced?: (show: boolean) => void;
}

export interface DateRangePickerProps {
  startDate?: Date | null;
  endDate?: Date | null;
  onStartDateChange: (date: Date | null) => void;
  onEndDateChange: (date: Date | null) => void;
  label?: string;
  disabled?: boolean;
}

export interface PaginationControlsProps {
  pagination: PaginationState;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  disabled?: boolean;
}

export interface MultiSelectFilterProps {
  options: string[];
  value: string[];
  onChange: (values: string[]) => void;
  label: string;
  placeholder?: string;
  disabled?: boolean;
}

export interface FilterChipProps {
  label: string;
  onDelete: () => void;
  color?: 'default' | 'primary' | 'secondary' | 'success' | 'error' | 'info' | 'warning';
  variant?: 'filled' | 'outlined';
}

// Phase 5: Chain visualization component props
export interface ChainProgressCardProps {
  session: Session;
  chainProgress?: ChainProgressUpdate;
  stageProgress?: StageProgressUpdate[];
  onClick?: (sessionId: string) => void;
  compact?: boolean;
}

export interface StageProgressBarProps {
  stages: StageExecution[];
  currentStageIndex?: number | null;
  showLabels?: boolean;
  size?: 'small' | 'medium' | 'large';
}

// Legacy ChainExecution interface for backward compatibility
export interface ChainExecution {
  chain_id: string;
  chain_definition: any;
  current_stage_index: number | null;
  current_stage_id: string | null;
  stages: StageExecution[];
}

export interface ChainTimelineProps {
  chainExecution: ChainExecution;
  expandedStages?: string[];
  onStageToggle?: (stageId: string) => void;
}

export interface StageCardProps {
  stage: StageExecution;
  expanded?: boolean;
  onToggle?: () => void;
}

// EP-0018: Manual Alert Submission types
export interface AlertSubmissionResponse {
  alert_id: string;
  status: string;
  message: string;
}

export interface ProcessingStatus {
  alert_id: string;
  status: 'queued' | 'processing' | 'completed' | 'error';
  progress: number;
  current_step: string;
  result?: string;
  error?: string;
  timestamp: string;
}

export interface AlertSubmissionWebSocketMessage {
  type: 'status_update' | 'error' | 'connected';
  data?: ProcessingStatus;
  message?: string;
}

export interface KeyValuePair {
  id: string;
  key: string;
  value: string;
}

export interface ManualAlertFormProps {
  onAlertSubmitted: (alertResponse: AlertSubmissionResponse) => void;
}

export interface ProcessingStatusProps {
  alertId: string;
  onComplete?: () => void;
}