import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Home from './views/Home.vue'
import TQuote from './views/TQuote.vue'
import Quotes from './views/Quotes.vue'
import Kline from './views/Kline.vue'
import Strategy from './views/Strategy.vue'
import Volatility from './views/Volatility.vue'
import ContractDetail from './views/ContractDetail.vue'
import Screener from './views/Screener.vue'
import './styles/global.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/tquote', component: TQuote },
    { path: '/quotes', component: Quotes },
    { path: '/kline', component: Kline },
    { path: '/strategy', component: Strategy },
    { path: '/volatility', component: Volatility },
    { path: '/screener', component: Screener },
    { path: '/contract/:code', component: ContractDetail },
  ],
})

createApp(App).use(router).mount('#app')
