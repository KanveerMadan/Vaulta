/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        forest: {
          950: '#030A05',
          900: '#0A1A0E',
          800: '#0F2614',
          700: '#16361C',
          600: '#1E4826',
          500: '#27602F',
          400: '#347A3D',
          300: '#4A9955',
          200: '#6DB87A',
          100: '#A8D9B0',
          50:  '#E8F5EB',
        },
        cream: {
          50:  '#FFFEF9',
          100: '#FBF8F0',
          200: '#F5F0E4',
          300: '#EDE6D5',
          400: '#D9CEB8',
          500: '#B8AA90',
        },
        gold:   '#C9A84C',
        danger: '#C0392B',
        safe:   '#166534',
      },
      fontFamily: {
        sans:    ['"Instrument Sans"', 'sans-serif'],
        display: ['"Fraunces"', 'serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'fade-up':   'fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in':   'fadeIn 0.35s ease both',
        'slide-in':  'slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) both',
        'skeleton':  'skeleton 1.8s ease-in-out infinite',
        'count-up':  'fadeIn 0.6s ease both',
        'float':     'float 6s ease-in-out infinite',
      },
      keyframes: {
        fadeUp:  { '0%': { opacity: 0, transform: 'translateY(20px)' }, '100%': { opacity: 1, transform: 'none' } },
        fadeIn:  { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        slideIn: { '0%': { opacity: 0, transform: 'translateX(-16px)' }, '100%': { opacity: 1, transform: 'none' } },
        skeleton:{ '0%,100%': { opacity: 0.4 }, '50%': { opacity: 0.75 } },
        float:   { '0%,100%': { transform: 'translateY(0px)' }, '50%': { transform: 'translateY(-8px)' } },
      },
      boxShadow: {
        'card':  '0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.06)',
        'card-hover': '0 4px 12px rgba(0,0,0,0.12), 0 8px 32px rgba(0,0,0,0.08)',
        'green': '0 0 0 3px rgba(74, 153, 85, 0.2)',
        'inset': 'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
    },
  },
  plugins: [],
}