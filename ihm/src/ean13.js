// EAN-13 : clé de contrôle et motif des barres (95 modules).

const L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011']
const G = ['0100111', '0110011', '0011011', '0100001', '0011101', '0111001', '0000101', '0010001', '0001001', '0010111']
const R = ['1110010', '1100110', '1101100', '1000010', '1011100', '1001110', '1010000', '1000100', '1001000', '1110100']
// Parité des 6 chiffres de gauche selon le premier chiffre.
const PARITY = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL']

export function checkDigit(first12) {
  let total = 0
  for (let i = 0; i < 12; i++) total += Number(first12[i]) * (i % 2 ? 3 : 1)
  return (10 - (total % 10)) % 10
}

export function isValidEan13(value) {
  return /^\d{13}$/.test(value) && checkDigit(value.slice(0, 12)) === Number(value[12])
}

/** Chaîne de 95 caractères « 0 »/« 1 » : un module clair ou sombre par caractère. */
export function ean13Modules(value) {
  if (!isValidEan13(value)) throw new Error('EAN-13 invalide')
  const parity = PARITY[Number(value[0])]
  let bits = '101'
  for (let i = 0; i < 6; i++) {
    const digit = Number(value[i + 1])
    bits += (parity[i] === 'L' ? L : G)[digit]
  }
  bits += '01010'
  for (let i = 7; i < 13; i++) bits += R[Number(value[i])]
  return bits + '101'
}

/** Barres sous forme de segments { start, length } en modules, pour dessiner le SVG. */
export function ean13Bars(value) {
  const bits = ean13Modules(value)
  const bars = []
  let start = -1
  for (let i = 0; i <= bits.length; i++) {
    const dark = bits[i] === '1'
    if (dark && start < 0) start = i
    if (!dark && start >= 0) {
      bars.push({ start, length: i - start })
      start = -1
    }
  }
  return bars
}

/** Les barres de garde (début, milieu, fin) descendent plus bas que les autres. */
export function isGuard(start, length) {
  const end = start + length
  return end <= 3 || (start >= 45 && end <= 50) || start >= 92
}
