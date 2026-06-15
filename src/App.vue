<script setup>
import { computed, onMounted, ref } from 'vue'

const view = ref('items')
const items = ref([])
const sources = ref([])
const rules = ref([])
const loading = ref(false)
const error = ref('')
const selectedSource = ref('')
const newSource = ref({
  name: '',
  fetcher_type: 'rss',
  config_text: '{"feed_url":"https://linux.do/latest.rss"}',
  fetch_interval_minutes: 15,
  enabled: true
})
const newRule = ref({
  source_id: '',
  field: 'title',
  match_type: 'contains',
  pattern: '',
  enabled: true
})

const sourceOptions = computed(() => [{ id: '', name: '全部来源' }, ...sources.value])

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {})
    }
  })
  const data = await response.json()
  if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || '请求失败')
  return data
}

async function loadItems() {
  loading.value = true
  error.value = ''
  try {
    const qs = selectedSource.value ? `?source_id=${selectedSource.value}` : ''
    items.value = (await api('/api/items' + qs)).items || []
  } catch (e) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  sources.value = (await api('/api/sources')).sources || []
}

async function loadRules() {
  rules.value = (await api('/api/filter-rules')).rules || []
}

async function refreshAll() {
  await Promise.all([loadSources(), loadRules()])
  await loadItems()
}

async function createSource() {
  const payload = {
    name: newSource.value.name,
    fetcher_type: newSource.value.fetcher_type,
    config: JSON.parse(newSource.value.config_text),
    fetch_interval_minutes: Number(newSource.value.fetch_interval_minutes),
    enabled: newSource.value.enabled
  }
  await api('/api/sources', { method: 'POST', body: JSON.stringify(payload) })
  newSource.value.name = ''
  await refreshAll()
}

async function toggleSource(source) {
  await api(`/api/sources/${source.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled: !source.enabled })
  })
  await loadSources()
}

async function fetchSource(source) {
  await api(`/api/fetch/${source.id}`, { method: 'POST' })
  await refreshAll()
}

async function createRule() {
  await api('/api/filter-rules', {
    method: 'POST',
    body: JSON.stringify({
      source_id: newRule.value.source_id ? Number(newRule.value.source_id) : null,
      field: newRule.value.field,
      match_type: newRule.value.match_type,
      pattern: newRule.value.pattern,
      enabled: newRule.value.enabled
    })
  })
  newRule.value.pattern = ''
  await refreshAll()
}

async function applyRules() {
  await api('/api/filter-rules/apply', { method: 'POST' })
  await loadItems()
}

function fmtDate(value) {
  if (!value) return '未标注时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(refreshAll)
</script>

<template>
  <main class="app">
    <header class="topbar">
      <div>
        <p class="eyebrow">Personal information flow</p>
        <h1>Info Flow Hub</h1>
        <p class="subtitle">RSS、网页抓取和 CDP 浏览器抓取汇入同一份 SQLite。</p>
      </div>
      <nav class="tabs">
        <button :class="{ active: view === 'items' }" @click="view = 'items'">信息流</button>
        <button :class="{ active: view === 'sources' }" @click="view = 'sources'">来源</button>
        <button :class="{ active: view === 'rules' }" @click="view = 'rules'">过滤</button>
      </nav>
    </header>

    <section v-if="view === 'items'" class="panel">
      <div class="panel-head">
        <div>
          <h2>最新内容</h2>
          <p>默认隐藏被过滤规则净化的条目。</p>
        </div>
        <div class="actions">
          <select v-model="selectedSource" @change="loadItems">
            <option v-for="source in sourceOptions" :key="source.id" :value="source.id">{{ source.name }}</option>
          </select>
          <button @click="loadItems">刷新</button>
        </div>
      </div>
      <div v-if="loading" class="state">加载中...</div>
      <div v-else-if="error" class="state error">{{ error }}</div>
      <div v-else-if="!items.length" class="empty">还没有内容。先添加来源并手动抓取一次。</div>
      <article v-for="item in items" :key="item.id" class="feed-item">
        <div class="meta">
          <span>{{ item.source_name }}</span>
          <span>{{ fmtDate(item.published_at || item.fetched_at) }}</span>
          <span v-if="item.author">{{ item.author }}</span>
        </div>
        <h2><a :href="item.url" target="_blank" rel="noreferrer">{{ item.title || item.url || '无标题条目' }}</a></h2>
        <p>{{ item.content }}</p>
      </article>
    </section>

    <section v-else-if="view === 'sources'" class="panel">
      <div class="panel-head">
        <div>
          <h2>信息源</h2>
          <p>RSS 可直接抓取；CDP 浏览器抓取在 openclawonly 上验证。</p>
        </div>
      </div>
      <form class="form-grid" @submit.prevent="createSource">
        <input v-model="newSource.name" required placeholder="名称，例如 linux.do" />
        <select v-model="newSource.fetcher_type">
          <option value="rss">rss</option>
          <option value="http_scrape">http_scrape</option>
          <option value="cdp_browser">cdp_browser</option>
        </select>
        <input v-model.number="newSource.fetch_interval_minutes" type="number" min="1" />
        <textarea v-model="newSource.config_text" required rows="3"></textarea>
        <label class="check"><input v-model="newSource.enabled" type="checkbox" /> 启用</label>
        <button type="submit">新增来源</button>
      </form>
      <article v-for="source in sources" :key="source.id" class="source-row">
        <div>
          <strong>{{ source.name }}</strong>
          <span>{{ source.fetcher_type }} · {{ source.item_count || 0 }} 条 · 隐藏 {{ source.hidden_count || 0 }}</span>
          <small>最近抓取 {{ source.last_fetched_at || '暂无' }}</small>
        </div>
        <div class="row-actions">
          <button @click="fetchSource(source)">抓取</button>
          <button @click="toggleSource(source)">{{ source.enabled ? '停用' : '启用' }}</button>
        </div>
      </article>
    </section>

    <section v-else class="panel">
      <div class="panel-head">
        <div>
          <h2>过滤规则</h2>
          <p>当前阶段只支持 hide，用于净化不想看的条目。</p>
        </div>
        <button @click="applyRules">回溯应用</button>
      </div>
      <form class="form-grid" @submit.prevent="createRule">
        <select v-model="newRule.source_id">
          <option value="">全局规则</option>
          <option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option>
        </select>
        <select v-model="newRule.field">
          <option value="title">title</option>
          <option value="content">content</option>
          <option value="author">author</option>
        </select>
        <select v-model="newRule.match_type">
          <option value="contains">contains</option>
          <option value="regex">regex</option>
        </select>
        <input v-model="newRule.pattern" required placeholder="关键词或正则" />
        <label class="check"><input v-model="newRule.enabled" type="checkbox" /> 启用</label>
        <button type="submit">新增规则</button>
      </form>
      <article v-for="rule in rules" :key="rule.id" class="rule-row">
        <strong>{{ rule.source_id ? `source #${rule.source_id}` : '全局' }}</strong>
        <span>{{ rule.field }} {{ rule.match_type }} "{{ rule.pattern }}" → {{ rule.action }}</span>
      </article>
    </section>
  </main>
</template>
