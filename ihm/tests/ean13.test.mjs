import { test } from 'node:test'
import assert from 'node:assert/strict'
import { checkDigit, ean13Bars, ean13Modules, isGuard, isValidEan13 } from '../src/ean13.js'
import { describeIdentification, identifyCode } from '../src/identify.js'

test('clé de contrôle et validation', () => {
  assert.equal(checkDigit('376000000001'), 7)
  assert.ok(isValidEan13('3760000000017'))
  assert.ok(isValidEan13('4006381333931'))
  assert.ok(!isValidEan13('3760000000018'))
  assert.ok(!isValidEan13('376000000001'))
  assert.ok(!isValidEan13('37600000000a7'))
})

test('motif de 95 modules, gardes 101 / 01010 / 101', () => {
  for (const ean of ['3760000000017', '4006381333931', '5901234123457', '9780201379624']) {
    const bits = ean13Modules(ean)
    assert.equal(bits.length, 95)
    assert.equal(bits.slice(0, 3), '101')
    assert.equal(bits.slice(45, 50), '01010')
    assert.equal(bits.slice(92), '101')
  }
})

test('les barres reconstituent exactement le motif', () => {
  const ean = '3760000000017'
  const bits = ean13Modules(ean)
  const rebuilt = Array(95).fill('0')
  for (const { start, length } of ean13Bars(ean)) for (let i = 0; i < length; i++) rebuilt[start + i] = '1'
  assert.equal(rebuilt.join(''), bits)
})

test('barres de garde', () => {
  const guards = ean13Bars('3760000000017').filter((b) => isGuard(b.start, b.length))
  assert.equal(guards.length, 2 + 2 + 2) // début : 2 barres, milieu : 2, fin : 2
})

test('EAN invalide refusé par le dessin', () => {
  assert.throws(() => ean13Modules('3760000000018'))
})

test('identification du type de code', () => {
  assert.deepEqual(identifyCode('3760000000017'), { kind: 'ean13', value: '3760000000017' })
  assert.deepEqual(identifyCode(' 3 760000 000017 '), { kind: 'ean13', value: '3760000000017' })
  assert.deepEqual(identifyCode('376-0000-000017'), { kind: 'ean13', value: '3760000000017' })
  assert.deepEqual(identifyCode('https://produits.example/p/1'), { kind: 'qr', value: 'https://produits.example/p/1' })
  assert.deepEqual(identifyCode('3760000000018'), { kind: 'invalid-ean13' })
  assert.deepEqual(identifyCode('   '), { kind: 'empty' })
  assert.deepEqual(identifyCode('a'.repeat(2049)), { kind: 'too-long' })
  assert.equal(identifyCode('a'.repeat(2048)).kind, 'qr')
})

test('messages sous le champ', () => {
  assert.equal(describeIdentification(identifyCode('3760000000017')).ok, true)
  assert.equal(describeIdentification(identifyCode('abc')).ok, true)
  assert.equal(describeIdentification(identifyCode('3760000000018')).ok, false)
  assert.equal(describeIdentification(identifyCode('')).ok, null)
})
