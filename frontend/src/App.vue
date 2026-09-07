<template>
  <div id="app">
    <header class="top-bar">
      <router-link to="/" class="brand">
        <span class="brand-icon">🎬</span>
        <span class="brand-text">
          <span class="brand-title">小说转漫剧</span>
          <span class="brand-sub">AI 剧本工坊</span>
        </span>
      </router-link>
      <nav class="top-nav">
        <router-link to="/" class="nav-link">项目</router-link>
        <router-link to="/create" class="btn btn-primary btn-sm">新建项目</router-link>
      </nav>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 20px;
  margin-bottom: 28px;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none !important;
  color: var(--text) !important;
}

.brand-icon {
  font-size: 28px;
  line-height: 1;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.brand-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--text);
}

.brand-sub {
  font-size: 11px;
  color: var(--text-light);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.top-nav {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-link {
  font-size: 14px;
  color: var(--text-dim) !important;
  font-weight: 500;
  padding: 4px 0;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.nav-link:hover,
.nav-link.router-link-active {
  color: var(--text) !important;
  border-bottom-color: var(--primary);
}
</style>
