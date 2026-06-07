/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // App surfaces — light sage
        sage: {
          50:  '#F2F7F3',  // app background
          100: '#E8F0EA',  // subtle tint
          200: '#D4E4D7',  // borders
          300: '#B8CFC0',  // stronger borders
          400: '#8FAF98',  // muted text
          500: '#5F8A6A',  // secondary text
        },
        // Forest — mid-tone, used for accents, buttons, highlights
        forest: {
          950: '#030A05',
          900: '#0A1A0E',
          800: '#0F2614',
          700: '#16361C',
          600: '#1E4826',
          500: '#27602F',
          400: '#2D6A4F',  // primary accent
          300: '#4A9955',
          200: '#6DB87A',
          100: '#A8D9B0',
          50:  '#E8F5EB',
        },
        // Ink — for text on light surfaces
        ink: {
          900: '#1A2E1E',  // headings
          700: '#2D4A32',  // body
          500: '#4A6B50',  // secondary
          300: '#7A9E80',  // muted
          100: '#C5DAC8',  // very muted
        },
        cream: {
          50:  '#FFFEF9',
          100: '#FBF8F0',
          200: '#F5F0E4',
          300: '#EDE6D5',
          400: '#D9CEB8',
          500: '#B8AA90',
        },
        gold:   '#B5852A',
        danger: '#C0392B',
        safe:   '#2D6A4F',
      },
      fontFamily: {
        sans:    ['"Instrument Sans"', 'sans-serif'],
        display: ['"Fraunces"', 'serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'fade-up':  'fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in':  'fadeIn 0.35s ease both',
        'skeleton': 'skeleton 1.8s ease-in-out infinite',
        'float':    'float 6s ease-in-out infinite',
      },
      keyframes: {
        fadeUp:   { '0%': { opacity: 0, transform: 'translateY(18px)' }, '100%': { opacity: 1, transform: 'none' } },
        fadeIn:   { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        skeleton: { '0%,100%': { opacity: 0.5 }, '50%': { opacity: 0.9 } },
        float:    { '0%,100%': { transform: 'translateY(0px)' }, '50%': { transform: 'translateY(-6px)' } },
      },
      boxShadow: {
        'card':       '0 1px 3px rgba(45,106,79,0.06), 0 4px 16px rgba(45,106,79,0.04)',
        'card-hover': '0 4px 12px rgba(45,106,79,0.1), 0 8px 32px rgba(45,106,79,0.06)',
        'button':     '0 1px 3px rgba(45,106,79,0.25), inset 0 1px 0 rgba(255,255,255,0.1)',
      },
    },
  },
  plugins: [],
}