// 对应设计：这是 Vue 前端的启动入口。
// 浏览器打开 index.html 后，会加载本文件，创建 App.vue 并挂载到 #app。
import { createApp } from 'vue';
import App from './App.vue';

// App.vue 是整个页面的根组件；ChatPanel 和 ProgressPanel 由它组织。
createApp(App).mount('#app');
