import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    // 开发页面地址：http://127.0.0.1:5173
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      // 对应设计：前端统一请求 /api，开发服务器把请求转给 FastAPI。
      // 例如 /api/chat 会转发到 http://127.0.0.1:8000/api/chat。
      // SSE 的 /api/chat/{conversation_id}/events 也使用同一个代理。
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
