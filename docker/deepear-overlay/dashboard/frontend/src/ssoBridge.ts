import { useDashboardStore } from './store'

type SsoBridgeUser = {
  id: number
  username: string
}

type SsoBridgeMessage = {
  type: 'DSA_DEEPEAR_SSO'
  token: string
  user: SsoBridgeUser
}

let installed = false

function getConfiguredOrigins(): string[] {
  const configured = (import.meta.env.VITE_ALLOWED_PARENT_ORIGINS || '').trim()
  if (!configured) {
    return []
  }
  return configured
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function getReferrerOrigin(): string | null {
  if (!document.referrer) {
    return null
  }
  try {
    return new URL(document.referrer).origin
  } catch {
    return null
  }
}

function isAllowedOrigin(origin: string): boolean {
  const configuredOrigins = getConfiguredOrigins()
  if (configuredOrigins.length > 0) {
    return configuredOrigins.includes(origin)
  }
  const referrerOrigin = getReferrerOrigin()
  return Boolean(referrerOrigin && referrerOrigin === origin)
}

function isValidMessage(data: unknown): data is SsoBridgeMessage {
  if (!data || typeof data !== 'object') {
    return false
  }
  const candidate = data as Partial<SsoBridgeMessage>
  return (
    candidate.type === 'DSA_DEEPEAR_SSO' &&
    typeof candidate.token === 'string' &&
    candidate.token.trim().length > 0 &&
    !!candidate.user &&
    typeof candidate.user.id === 'number' &&
    typeof candidate.user.username === 'string' &&
    candidate.user.username.trim().length > 0
  )
}

function handleSsoMessage(event: MessageEvent): void {
  if (!isAllowedOrigin(event.origin) || !isValidMessage(event.data)) {
    return
  }

  const payload = event.data
  useDashboardStore.getState().login(payload.user, payload.token)

  if (window.location.pathname === '/login' || window.location.pathname === '/register') {
    window.location.replace('/')
  }
}

export function installSsoBridge(): void {
  if (installed || typeof window === 'undefined') {
    return
  }
  installed = true
  window.addEventListener('message', handleSsoMessage)
}
