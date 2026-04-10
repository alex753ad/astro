/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        zodiac: {
          fire: '#E74C3C',
          earth: '#27AE60',
          air: '#3498DB',
          water: '#2980B9',
        },
        aspect: {
          harmony: '#3498DB',
          tension: '#E74C3C',
          neutral: '#F39C12',
        },
        brand: {
          dark: '#0F0A1A',
          deeper: '#1A1230',
          card: '#231C38',
          accent: '#8B5CF6',
          glow: '#A78BFA',
          text: '#E2DFF0',
          muted: '#9B97B0',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
