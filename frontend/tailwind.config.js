/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        zodiac: {
          fire:  '#E74C3C',
          earth: '#27AE60',
          air:   '#3498DB',
          water: '#2980B9',
        },
        aspect: {
          harmony: 'var(--aspect-harmony)',
          tension: 'var(--aspect-tension)',
          neutral: 'var(--aspect-neutral)',
        },
        brand: {
          bg:     'var(--bg)',
          card:   'var(--bg-card)',
          deeper: 'var(--bg-deeper)',
          border: 'var(--border)',
          text:   'var(--text-primary)',
          muted:  'var(--text-secondary)',
          accent: 'var(--accent)',
          glow:   'var(--accent-glow)',
        },
      },
      // Источник — токены в src/index.css (--font-display/--font-body), а не
      // список здесь: до 14.09.2026 стек был записан в четырёх местах сразу.
      fontFamily: {
        display: ['var(--font-display)'],
        body:    ['var(--font-body)'],
      },
    },
  },
  plugins: [],
};
