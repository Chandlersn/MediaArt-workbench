import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default defineConfig({
  root: '.',
  base: './',
  publicDir: 'public',

  plugins: [
    vue()
  ],

  server: {
    port: 3004,
    open: false,
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/upload': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/download': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/resources': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/templates': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/data': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/assets': { target: 'http://localhost:8080', changeOrigin: true, secure: false },
      '/MediaArt_Archives': { target: 'http://localhost:8080', changeOrigin: true, secure: false }
    },
    cors: true
  },

  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    // sourcemap 生成是构建内存的主要消耗方：本机内存偏紧时开启会因
    // "memory allocation failed" 直接构建失败（实测关掉后一次通过）。
    // 默认关闭；需要调试线上包时用 `SOURCEMAP=1 npm run build` 打开。
    // 日常开发用 `npm run dev`，走 vite dev server、不压缩，不受此项影响。
    sourcemap: process.env.SOURCEMAP === '1',
    cssMinify: true,
    minify: 'terser',
    terserOptions: {
      compress: { drop_console: false, drop_debugger: true }
    },
    rollupOptions: {
      input: { main: path.resolve(__dirname, 'index.html') },
      output: {
        entryFileNames: 'js/[name]-[hash].js',
        chunkFileNames: 'js/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name.endsWith('.css')) return 'css/[name]-[hash][extname]';
          if (/\.(png|jpe?g|gif|svg|webp|ico)$/i.test(assetInfo.name)) return 'images/[name]-[hash][extname]';
          if (/\.(woff2?|eot|ttf|otf)$/i.test(assetInfo.name)) return 'fonts/[name]-[hash][extname]';
          return 'assets/[name]-[hash][extname]';
        }
      }
    },
    chunkSizeWarningLimit: 1000
  },

  css: {
    devSourcemap: true,
    postcss: { plugins: [] }
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    },
    extensions: ['.js', '.json', '.vue']
  },

  optimizeDeps: {
    include: ['chart.js'],
    exclude: []
  },

  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version || '2.0')
  }
});
