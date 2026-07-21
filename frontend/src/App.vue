<script setup>
import AppLayout from './components/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>

<style scoped>
.app-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px;
}
</style>
