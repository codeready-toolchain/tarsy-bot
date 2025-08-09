// Basic alert session types for Phase 1
export interface Session {
  session_id: string;
  alert_id: string;
  alert_type: string;
  agent_type: string;
  status: 'completed' | 'failed' | 'in_progress' | 'pending';
  started_at_us: number; // Unix timestamp (microseconds since epoch)
  completed_at_us: number | null; // Unix timestamp (microseconds since epoch)
  duration_ms: number | null;
  summary?: string | object; // Backend may return string or empty object
  error_message: string | null;
  llm_interaction_count?: number;
  mcp_communication_count?: number;
}

// Phase 3: Detailed session data for session detail page
export interface DetailedSession extends Session {
  alert_data: AlertData;
  final_analysis: string | null;
  chronological_timeline: TimelineItem[];
}

// Flexible alert data structure supporting any fields
export interface AlertData {
  [key: string]: any; // Can contain any fields
}

// Phase 3: Timeline item structure
export interface TimelineItem {
  id: string;
  event_id: string;
  type: 'llm' | 'mcp' | 'system';
  timestamp_us: number; // Unix timestamp (microseconds since epoch)
  step_description: string;
  duration_ms: number | null;
  details?: LLMInteraction | MCPInteraction | SystemEvent;
}

// Phase 3: LLM interaction details
export interface LLMInteraction {
  // New JSON-first shape coming from backend
  request_json?: {
    model?: string;
    messages?: Array<{ role: string; content: any }>;
    temperature?: number;
    [key: string]: any;
  };
  response_json?: {
    choices?: any[];
    usage?: any;
    [key: string]: any;
  };

  // Normalized metadata
  model_name: string;
  tokens_used?: number;
  temperature?: number;
}

// Phase 3: MCP interaction details
export interface MCPInteraction {
  tool_name: string;
  parameters: Record<string, any>;
  result: any;
  server_name: string;
  execution_time_ms: number;
}

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

// WebSocket message types (Phase 2)
export interface WebSocketMessage {
  type: 'session_update' | 'session_completed' | 'session_failed' | 'ping' | 'pong' | 'connection_established' | 'subscription_response' | 'dashboard_update' | 'message_batch' | 'session_status_change' | 'batched_session_updates';
  data?: SessionUpdate | any; // Allow any data type for dashboard_update messages
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

// Phase 5: Enhanced timeline and interaction components
export interface TimelineVisualizationProps {
  timelineItems: TimelineItem[];
  isActive?: boolean;
}

export interface InteractionDetailsProps {
  type: 'llm' | 'mcp' | 'system';
  details: LLMInteraction | MCPInteraction | SystemEvent;
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