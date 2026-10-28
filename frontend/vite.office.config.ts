import { defineConfig } from 'vite'

// Builds the sandbox-frame office renderer. Output goes to office-host/ (NOT
// under public/, or vite would copy public/ into itself). The main build then
// ships it via rollupOptions input -> dist/office/.
export default defineConfig({
  define: {
    'process.env.NODE_ENV': '"production"',
    'process.version': '""',
    process: '({ env: { NODE_ENV: "production" } })',
    global: 'globalThis',
  },
  build: {
    outDir: 'office-host',
    emptyOutDir: true,
    lib: {
      entry: 'src/office/renderEntry.ts',
      formats: ['iife'],
      name: 'MeowOffice',
      fileName: () => 'render.js',
    },
    minify: true,
    rollupOptions: {
      output: { banner: 'window.process=window.process||{env:{NODE_ENV:"production"},version:"",browser:true,argv:[],cwd:function(){return"/"}};window.global=window.global||globalThis;' },
    },
  },
})
