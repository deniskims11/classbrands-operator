import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Relative base: the same build is copied to public/b/<brand>/ for every brand.
export default defineConfig({
  plugins: [react()],
  base: './',
})
