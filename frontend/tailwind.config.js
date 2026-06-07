/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Forest greens
        forest: {
          950: '#060D08',
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
        // Cream / warm whites
        cream: {
          50:  '#FFFEF9',
          100: '#FBF8F0',
          200: '#F5F0E4',
          300: '#EDE6D5',
          400: '#D9CEB8',
          500: '#B8AA90',
        },
        // Accents
        gold:   '#C9A84C',
        danger: '#C0392B',
        safe:   '#27AE60',
      },
      fontFamily: {
        sans:    ['"Instrument Sans"', 'sans-serif'],
        display: ['"Fraunces"', 'serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '8px',
        lg: '12px',
        xl: '16px',
        '2xl': '20px',
      },
      animation: {
        'fade-up':  'fadeUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in':  'fadeIn 0.3s ease both',
        'skeleton': 'skeleton 1.6s ease-in-out infinite',
      },
      keyframes: {
        fadeUp:   { '0%': { opacity: 0, transform: 'translateY(18px)' }, '100%': { opacity: 1, transform: 'none' } },
        fadeIn:   { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        skeleton: { '0%,100%': { opacity: 0.4 }, '50%': { opacity: 0.8 } },
      },
    },
  },
  plugins: [],
}