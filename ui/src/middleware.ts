import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PROTECTED_PATHS = ['/documents', '/chat', '/history', '/admin']
const PUBLIC_PATHS = ['/login', '/register']

function hasValidToken(request: NextRequest): boolean {
  // We can only check cookies in middleware; localStorage is client-side only.
  // The actual redirect logic for localStorage tokens is handled client-side in DashboardLayout.
  // Middleware handles cookie-based tokens if set.
  const token = request.cookies.get('rag_access_token')?.value
  return Boolean(token)
}

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl

  const isProtected = PROTECTED_PATHS.some((p) => pathname.startsWith(p))
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  // If protected path and no cookie token, redirect to login
  // (localStorage check happens client-side in DashboardLayout)
  if (isProtected && !hasValidToken(request)) {
    // Allow through — client-side DashboardLayout will handle the redirect
    return NextResponse.next()
  }

  if (isPublic && hasValidToken(request)) {
    return NextResponse.redirect(new URL('/documents', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
