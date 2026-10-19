/** @type {import('tailwindcss').Config} */
// Colours come from CSS variables (src/styles/tokens.css) so every class follows the theme.
// Semantic names are the system; the older ramps (ink-*, sage-*, forest-*, gold, safe) are
// mapped onto the same tokens so existing markup themes correctly.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        canvas: v('canvas'),
        surface: v('surface'),
        sunken: v('sunken'),
        line: { DEFAULT: v('line'), strong: v('line-strong') },
        ink: {
          DEFAULT: v('ink'),
          900: v('ink'), 800: v('ink'), 700: v('ink-2'), 600: v('ink-2'),
          500: v('muted'), 400: v('muted'), 300: v('muted'), 200: v('line-strong'), 100: v('line'),
        },
        'ink-2': v('ink-2'),
        muted: v('muted'),
        faint: v('faint'),
        accent: { DEFAULT: v('accent'), text: v('accent-text'), strong: v('accent-strong'), tint: v('accent-tint'), line: v('accent-line') },
        'on-accent': v('on-accent'),
        inverse: v('inverse'),
        'on-inverse': v('on-inverse'),
        warn: { DEFAULT: v('warn'), tint: v('warn-tint') },
        danger: { DEFAULT: v('danger'), tint: v('danger-tint') },
        // legacy ramps → tokens
        sage: { 50: v('sunken'), 100: v('sunken'), 200: v('line'), 300: v('line-strong'), 400: v('faint'), 500: v('muted') },
        forest: {
          50: v('accent-tint'), 100: v('accent-tint'), 200: v('accent-line'), 300: v('accent'), 400: v('accent'),
          500: v('accent'), 600: v('accent-text'), 700: v('accent-text'), 800: v('accent-strong'),
          900: v('accent-strong'), 950: v('canvas'),
        },
        gold: v('warn'),
        safe: v('accent-text'),
      },
      fontFamily: {
        sans: ['var(--font-ui)'],
        display: ['var(--font-display)'],
        mono: ['var(--font-mono)'],
      },
      borderRadius: { sm: 'var(--r-sm)', md: 'var(--r-md)', lg: 'var(--r-lg)', xl: 'var(--r-md)', '2xl': 'var(--r-lg)' },
      boxShadow: { 1: 'var(--elev-1)', 2: 'var(--elev-2)', 3: 'var(--elev-3)', card: 'var(--elev-1)' },
      transitionTimingFunction: { out: 'var(--ease-out)', 'in-out': 'var(--ease-in-out)' },
      transitionDuration: { fast: 'var(--dur-fast)', DEFAULT: 'var(--dur)', slow: 'var(--dur-slow)' },
      fontSize: {
        micro: ['0.75rem', { lineHeight: '1rem' }],
        'display-s': ['2rem', { lineHeight: '1.05', letterSpacing: '-0.02em' }],
        'display-m': ['3rem', { lineHeight: '1', letterSpacing: '-0.03em' }],
        'display-l': ['clamp(3.25rem, 9vw, 5.5rem)', { lineHeight: '0.95', letterSpacing: '-0.035em' }],
      },
      keyframes: {
        'fade-in': { from: { opacity: 0 }, to: { opacity: 1 } },
        'rise': { from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'none' } },
        'shimmer': { from: { backgroundPosition: '-200% 0' }, to: { backgroundPosition: '200% 0' } },
      },
      animation: {
        'fade-in': 'fade-in var(--dur) var(--ease-out) both',
        'fade-up': 'rise var(--dur-slow) var(--ease-out) both',
        rise: 'rise var(--dur-slow) var(--ease-out) both',
        skeleton: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [
    // keyboard hints only where there's a mouse; swipe hints only on touch
    ({ addVariant }) => {
      addVariant('pointer-fine', '@media (pointer: fine)')
      addVariant('pointer-coarse', '@media (pointer: coarse)')
    },
  ],
}
