import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './styles/global.css'

const Home = () => import('./views/Home.vue')
const Quotes = () => import('./views/Quotes.vue')
const ContractDetail = () => import('./views/ContractDetail.vue')
const TQuote = () => import('./views/TQuote.vue')
const Volatility = () => import('./views/Volatility.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/quotes', component: Quotes },
    { path: '/tquote', component: TQuote },
    { path: '/contract/:code', component: ContractDetail },
    { path: '/volatility', component: Volatility }
  ]
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus)
app.mount('#app')
