/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 与 TUI 暗色主题一致（cyan 路由 / green 引用 / yellow 图表）
        bg: {
          base: '#0a0e14',
          panel: '#11151c',
          border: '#1e242e'
        },
        fg: {
          primary: '#c9d1d9',
          muted: '#8b949e'
        },
        accent: {
          cyan: '#56b6c2',
          green: '#7ec699',
          yellow: '#e5c07b',
          red: '#e06c75',
          purple: '#c678dd'
        }
      }
    }
  },
  plugins: []
}
