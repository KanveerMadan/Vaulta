/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#0D0D14',
        card:     '#13131E',
        elevated: '#1A1A28',
        border:   '#252535',
        brand:    '#6C63FF',
        'brand-light': '#8B85FF',
        'brand-dim':   'rgba(108,99,255,0.12)',
        positive: '#10B981',
        negative: '#F43F5E',
        warning:  '#F59E0B',
        't1': '#EEEEFF',
        't2': '#8888AA',
        't3': '#55556A',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'fade-up':   'fadeUp 0.5s ease both',
        'fade-in':   'fadeIn 0.4s ease both',
        'shimmer':   'shimmer 1.8s infinite',
      },
      keyframes: {
        fadeUp:  { from: { opacity: 0, transform: 'translateY(20px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        fadeIn:  { from: { opacity: 0 }, to: { opacity: 1 } },
        shimmer: { '0%': { backgroundPosition: '-400px 0' }, '100%': { backgroundPosition: '400px 0' } },
      },
    },
  },
  plugins: [],
}