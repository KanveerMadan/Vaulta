import { describe, expect, it } from 'vitest'
import { formatINR, formatINRCompact, spokenINR } from './money'

describe('formatINR', () => {
  it('groups digits the Indian way', () => {
    expect(formatINR(120000)).toBe('₹1,20,000')
    expect(formatINR('10000000')).toBe('₹1,00,00,000')
    expect(formatINR(999)).toBe('₹999')
    expect(formatINR(1234567.8)).toBe('₹12,34,567.80')
  })
  it('shows paise only when there are any, unless asked', () => {
    expect(formatINR('649.00')).toBe('₹649')
    expect(formatINR(0.5)).toBe('₹0.50')
    expect(formatINR(649, { decimals: 2 })).toBe('₹649.00')
    expect(formatINR(1829.56, { decimals: 0 })).toBe('₹1,830')
  })
  it('uses a real minus sign', () => {
    expect(formatINR(-2200)).toBe('−₹2,200')
  })
  it('is safe with junk', () => {
    expect(formatINR(undefined)).toBe('₹0')
    expect(formatINR('abc')).toBe('₹0')
  })
})

describe('formatINRCompact', () => {
  it('uses k, lakh and crore', () => {
    expect([950, 12000, 120000, 125000, 34000000].map(formatINRCompact)).toEqual(['₹950', '₹12k', '₹1.2L', '₹1.3L', '₹3.4Cr'])
  })
})

describe('spokenINR', () => {
  it('says the direction in words', () => {
    expect(spokenINR(1200, 'in')).toBe('₹1,200 received')
    expect(spokenINR('450.50', 'out')).toBe('₹450.50 spent')
    expect(spokenINR(-90)).toBe('minus ₹90')
  })
})
