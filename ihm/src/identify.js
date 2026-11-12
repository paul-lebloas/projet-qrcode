// Même règle que l'orchestrateur : 13 chiffres (espaces et tirets tolérés) = EAN-13, sinon QR Code.
import { isValidEan13 } from './ean13.js'

export const MAX_QR_LENGTH = 2048

export function identifyCode(raw) {
  const text = (raw ?? '').trim()
  if (!text) return { kind: 'empty' }

  const compact = text.replace(/[\s-]/g, '')
  if (/^\d{13}$/.test(compact)) {
    return isValidEan13(compact) ? { kind: 'ean13', value: compact } : { kind: 'invalid-ean13' }
  }
  if (text.length > MAX_QR_LENGTH) return { kind: 'too-long' }
  return { kind: 'qr', value: text }
}

export function describeIdentification(id) {
  switch (id.kind) {
    case 'ean13':
      return { ok: true, text: 'EAN-13 valide' }
    case 'qr':
      return { ok: true, text: 'Contenu de QR Code' }
    case 'invalid-ean13':
      return { ok: false, text: 'EAN-13 invalide : la clé de contrôle ne correspond pas.' }
    case 'too-long':
      return { ok: false, text: `Le contenu est trop long (${MAX_QR_LENGTH} caractères maximum).` }
    default:
      return { ok: null, text: '' }
  }
}
