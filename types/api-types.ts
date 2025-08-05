// Auto-generated TypeScript types from Python Pydantic models
// DO NOT EDIT - Run `poetry run python scripts/export_schemas.py` to regenerate

// Enum types
export enum SearchMode {
  SEMANTIC = 'semantic',
  GRAPH_AWARE = 'graph_aware',
  PREREQUISITE_PATH = 'prereq_path'
}

// Interface types
export interface CourseInfo {
  id: string;
  subject: string;
  catalog_nbr: string;
  title: string;
  description?: any;
  credits?: any;
  similarity_score?: any;
  graph_relevance?: any;
}

export interface PrerequisiteEdge {
  from_course_id: string;
  to_course_id: string;
  type: string;
  confidence: number;
}

export interface GraphContext {
  nodes: any[];
  edges: any[];
  centrality_scores?: any;
}

export interface RAGRequest {
  query: string;
  mode?: SearchMode;
  top_k?: number;
  include_graph_context?: boolean;
  max_prerequisite_depth?: number;
}

export interface PrerequisitePathRequest {
  course_id: string;
  include_recommendations?: boolean;
  max_depth?: number;
}

export interface ErrorDetail {
  code: string;
  message: string;
  details?: any;
}

export interface RAGResponse {
  success: boolean;
  answer?: any;
  courses?: any[];
  graph_context?: any;
  query_metadata?: object;
  error?: any;
}

export interface PrerequisitePathResponse {
  success: boolean;
  course?: any;
  prerequisite_path?: any;
  missing_prerequisites?: string[];
  recommendations?: any[];
  path_metadata?: object;
  error?: any;
}

export interface HealthResponse {
  status: string;
  services?: object;
  version?: string;
  timestamp: string;
}

export interface CentralityRequest {
  top_n?: number;
  damping_factor?: number;
  min_betweenness?: number;
  min_in_degree?: number;
}

export interface CentralityResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}

export interface CommunityRequest {
  algorithm?: string;
}

export interface CommunityResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}

export interface ShortestPathRequest {
  target_course: string;
  completed_courses?: string[];
}

export interface ShortestPathResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}

export interface CourseRecommendationRequest {
  course_code: string;
  num_recommendations?: number;
}

export interface CourseRecommendationResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}

export interface AlternativePathsRequest {
  target_course: string;
  completed_courses?: string[];
  num_alternatives?: number;
}

export interface AlternativePathsResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}

export interface GraphSubgraphRequest {
  max_nodes?: number;
  max_edges?: number;
  include_centrality?: boolean;
  include_communities?: boolean;
  filter_by_subject?: any;
}

export interface GraphSubgraphResponse {
  success: boolean;
  data?: any;
  computation_time_ms?: any;
  error?: any;
}
