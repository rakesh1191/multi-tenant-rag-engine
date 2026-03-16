import { getAccessToken, clearTokens } from './auth'
import type {
  RegisterResponse,
  LoginResponse,
  DocumentListResponse,
  Document,
  QueryResponse,
  QueryHistoryResponse,
  AdminStats,
} from './types'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function redirectToLogin(): void {
  clearTokens()
  if (typeof window !== 'undefined') {
    window.location.href = '/login'
  }
}

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken()
  const headers: HeadersInit = {
    ...(init.headers as Record<string, string> ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const resp = await fetch(`${API}${path}`, { ...init, headers })
  if (resp.status === 401) {
    redirectToLogin()
  }
  return resp
}

async function authJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await authFetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string> ?? {}),
    },
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ message: resp.statusText }))
    // FastAPI validation errors return { detail: [ { msg, loc } ] }
    const detail = (body as { detail?: unknown }).detail
    let message: string
    if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string; loc?: string[] }) =>
        `${d.loc?.slice(1).join('.')} — ${d.msg}`
      ).join(', ')
    } else {
      message = (body as { message?: string; detail?: string }).message
        ?? (typeof detail === 'string' ? detail : undefined)
        ?? resp.statusText
    }
    throw new Error(message)
  }
  return resp.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function register(payload: {
  tenant_name: string
  tenant_slug: string
  email: string
  password: string
}): Promise<RegisterResponse> {
  const resp = await fetch(`${API}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ message: resp.statusText }))
    const detail = (body as { detail?: unknown }).detail
    let message: string
    if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string; loc?: string[] }) =>
        `${d.loc?.slice(1).join('.')} — ${d.msg}`
      ).join(', ')
    } else {
      message = (body as { message?: string }).message
        ?? (typeof detail === 'string' ? detail : undefined)
        ?? resp.statusText
    }
    throw new Error(message)
  }
  return resp.json() as Promise<RegisterResponse>
}

// Backend /login expects JSON { email, password } and returns { access_token, refresh_token, token_type }
export async function login(email: string, password: string): Promise<LoginResponse> {
  const resp = await fetch(`${API}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ message: resp.statusText }))
    const detail = (body as { detail?: unknown }).detail
    let message: string
    if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string; loc?: string[] }) =>
        `${d.loc?.slice(1).join('.')} — ${d.msg}`
      ).join(', ')
    } else {
      message = (body as { message?: string }).message
        ?? (typeof detail === 'string' ? detail : undefined)
        ?? resp.statusText
    }
    throw new Error(message)
  }
  return resp.json() as Promise<LoginResponse>
}

export async function refreshToken(refresh_token: string): Promise<LoginResponse> {
  return authJson<LoginResponse>('/api/v1/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token }),
  })
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(page = 1, page_size = 20): Promise<DocumentListResponse> {
  return authJson<DocumentListResponse>(
    `/api/v1/documents?page=${page}&page_size=${page_size}`
  )
}

export async function getDocument(id: string): Promise<Document> {
  return authJson<Document>(`/api/v1/documents/${id}`)
}

export async function uploadDocument(
  file: File,
  onProgress?: (pct: number) => void
): Promise<Document> {
  const token = getAccessToken()
  return new Promise<Document>((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API}/api/v1/documents/upload`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status === 401) {
        redirectToLogin()
        return
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Document)
      } else {
        try {
          const body = JSON.parse(xhr.responseText) as { message?: string; detail?: unknown }
          const detail = body.detail
          let message: string
          if (Array.isArray(detail)) {
            message = (detail as { msg?: string }[]).map(d => d.msg ?? '').join(', ')
          } else {
            message = body.message ?? (typeof detail === 'string' ? detail : xhr.statusText)
          }
          reject(new Error(message))
        } catch {
          reject(new Error(xhr.statusText))
        }
      }
    }
    xhr.onerror = () => reject(new Error('Network error'))
    xhr.send(formData)
  })
}

export async function deleteDocument(id: string): Promise<void> {
  const resp = await authFetch(`/api/v1/documents/${id}`, { method: 'DELETE' })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ message: resp.statusText }))
    throw new Error((body as { message?: string }).message ?? resp.statusText)
  }
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

export async function querySync(query: string, top_k = 5): Promise<QueryResponse> {
  return authJson<QueryResponse>('/api/v1/query/sync', {
    method: 'POST',
    body: JSON.stringify({ query, top_k }),
  })
}

export async function queryStream(query: string): Promise<Response> {
  const token = getAccessToken()
  const resp = await fetch(`${API}/api/v1/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query }),
  })
  if (resp.status === 401) {
    redirectToLogin()
  }
  return resp
}

export async function getHistory(page = 1, page_size = 20): Promise<QueryHistoryResponse> {
  return authJson<QueryHistoryResponse>(
    `/api/v1/query/history?page=${page}&page_size=${page_size}`
  )
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function getStats(): Promise<AdminStats> {
  return authJson<AdminStats>('/api/v1/admin/stats')
}
