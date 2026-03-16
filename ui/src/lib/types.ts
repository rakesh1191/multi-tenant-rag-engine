export interface User {
  id: string
  email: string
  role: 'admin' | 'member'
  tenant_id: string
  is_active: boolean
  created_at: string
}

export interface Tenant {
  id: string
  name: string
  slug: string
  max_documents: number
  created_at: string
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface Document {
  id: string
  tenant_id: string
  uploaded_by: string
  filename: string
  content_type: string
  file_size_bytes: number
  status: DocumentStatus
  chunk_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentListResponse {
  items: Document[]
  total: number
  page: number
  page_size: number
}

export interface SourceChunk {
  document_id: string
  filename: string
  chunk_index: number
  similarity: number
}

export interface QueryResponse {
  query_id: string
  answer: string
  sources: SourceChunk[]
  token_usage: Record<string, number>
  cache_hit: boolean
  latency_ms: number
}

export interface QueryHistoryItem {
  id: string
  query_text: string
  response_text: string | null
  latency_ms: number | null
  token_usage: Record<string, number>
  cache_hit: boolean
  created_at: string
}

export interface QueryHistoryResponse {
  items: QueryHistoryItem[]
  total: number
  page: number
  page_size: number
}

// Matches backend TenantStats schema
export interface AdminStats {
  tenant_id: string
  tenant_name: string
  document_count: number
  chunk_count: number
  total_storage_bytes: number
  user_count: number
  query_count: number
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// Backend /register returns { user, tenant, tokens }
export interface RegisterResponse {
  user: User
  tenant: Tenant
  tokens: TokenResponse
}

// Backend /login returns TokenResponse directly
export type LoginResponse = TokenResponse

export interface TokenPayload {
  sub: string
  tenant_id: string
  role: 'admin' | 'member'
  type: string
  exp: number
  iat: number
}
