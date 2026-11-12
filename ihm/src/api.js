// Appels vers l'orchestrateur, via le seul point d'entrée public (/api sur le port 8080).

const TIMEOUT_MS = 30_000
export const MAX_IMAGE_BYTES = 5_000_000

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.code = code
    this.status = status
  }
}

function messageForStatus(status) {
  if (status === 413) return 'Image trop volumineuse (5 Mo maximum).'
  if (status === 429) return 'Trop de requêtes. Patientez quelques secondes puis réessayez.'
  if (status >= 500) return 'Le service est momentanément indisponible. Réessayez dans un instant.'
  return 'La requête a échoué.'
}

async function request(path, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  let response
  try {
    response = await fetch(path, { ...options, signal: controller.signal })
  } catch {
    throw new ApiError('Impossible de joindre le serveur. Vérifiez la connexion puis réessayez.', 'network', 0)
  } finally {
    clearTimeout(timer)
  }

  let body = null
  try {
    body = await response.json()
  } catch {
    // Réponse non JSON (par exemple une erreur du serveur web) : message générique ci-dessous.
  }

  if (!response.ok) {
    throw new ApiError(body?.error ?? messageForStatus(response.status), body?.code ?? 'http', response.status)
  }
  return body
}

export function scanCode(code) {
  return request('/api/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
}

export function scanImage(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/api/scan/image', { method: 'POST', body: form })
}

export function searchProducts(q) {
  return request(`/api/products/search?${new URLSearchParams({ q, limit: '12' })}`)
}

export function cacheStats() {
  return request('/api/cache/stats')
}
