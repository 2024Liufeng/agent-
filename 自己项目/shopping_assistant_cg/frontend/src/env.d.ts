/// <reference types="vite/client" />

// 告诉 TypeScript：导入 .vue 文件时，把它视为 Vue 组件。
declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
