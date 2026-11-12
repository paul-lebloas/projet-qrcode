<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ProductLabel from './components/ProductLabel.vue'
import { MAX_IMAGE_BYTES, cacheStats, scanCode, scanImage, searchProducts } from './api.js'
import { describeIdentification, identifyCode } from './identify.js'

const EXAMPLES = [
  { label: 'Biscuits (EAN-13)', code: '3760000000017' },
  { label: 'Café (QR Code)', code: 'https://produits.example/p/1002' },
  { label: 'Code inconnu', code: '4006381333931' },
]

const code = ref('')
const identification = computed(() => describeIdentification(identifyCode(code.value)))

const loading = ref(false)
const result = ref(null)
const errorMessage = ref('')
let requestId = 0

const query = ref('')
const searching = ref(false)
const searchItems = ref(null)
const searchError = ref('')

const stats = ref(null)

const previewUrl = ref('')
const fileInput = ref(null)

function setPreview(file) {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = file ? URL.createObjectURL(file) : ''
}
onBeforeUnmount(() => setPreview(null))

async function loadStats() {
  try {
    stats.value = await cacheStats()
  } catch {
    stats.value = null
  }
}
onMounted(loadStats)

// Lance une recherche ; seule la réponse à la dernière requête est affichée.
async function run(action) {
  const id = ++requestId
  loading.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const response = await action()
    if (id === requestId) result.value = response
  } catch (error) {
    if (id === requestId) errorMessage.value = error.message
  } finally {
    if (id === requestId) loading.value = false
  }
  loadStats()
}

function submitCode() {
  const id = identifyCode(code.value)
  if (id.kind === 'empty') {
    errorMessage.value = 'Saisissez un EAN-13 ou le contenu d’un QR Code.'
    result.value = null
    return
  }
  if (!identification.value.ok) {
    errorMessage.value = identification.value.text
    result.value = null
    return
  }
  setPreview(null)
  run(() => scanCode(code.value.trim()))
}

function useExample(example) {
  code.value = example.code
  submitCode()
}

function onFileChosen(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    errorMessage.value = 'Choisissez un fichier image (JPEG, PNG, WebP…).'
    result.value = null
    return
  }
  if (file.size > MAX_IMAGE_BYTES) {
    errorMessage.value = 'Cette image dépasse 5 Mo. Choisissez une image plus légère.'
    result.value = null
    return
  }
  setPreview(file)
  run(() => scanImage(file))
}

async function submitSearch() {
  searching.value = true
  searchError.value = ''
  try {
    searchItems.value = (await searchProducts(query.value.trim())).items
  } catch (error) {
    searchItems.value = null
    searchError.value = error.message
  } finally {
    searching.value = false
  }
  loadStats()
}

function openProduct(product) {
  setPreview(null)
  code.value = product.ean13 ?? product.qr_code
  run(() => scanCode(code.value))
}

const statsText = computed(() => {
  const s = stats.value
  if (!s) return ''
  if (s.redis !== 'up') return 'Cache Redis indisponible : les réponses viennent directement de la base.'
  const total = s.hits + s.misses
  if (total === 0) return 'Cache Redis en ligne. Aucune lecture pour l’instant.'
  return `Cache Redis en ligne. ${s.hits} réponse${s.hits > 1 ? 's' : ''} sur ${total} lue${s.hits > 1 ? 's' : ''} dans le cache (${Math.round(s.hit_ratio * 100)} %).`
})
</script>

<template>
  <div class="page">
    <header class="masthead">
      <h1>Scan produit</h1>
      <p>Retrouvez un produit avec son EAN-13, son QR Code ou une photo du code.</p>
    </header>

    <main class="layout">
      <div class="inputs">
        <section aria-labelledby="h-identify">
          <h2 id="h-identify">Identifier un produit</h2>

          <form class="field-row" @submit.prevent="submitCode" novalidate>
            <label for="code">EAN-13 ou contenu du QR Code</label>
            <div class="field-line">
              <input
                id="code"
                v-model="code"
                type="text"
                inputmode="text"
                autocomplete="off"
                spellcheck="false"
                maxlength="2200"
                aria-describedby="code-hint"
              />
              <button type="submit" class="primary" :disabled="loading">Identifier</button>
            </div>
            <p
              id="code-hint"
              class="hint"
              :class="{ bad: identification.ok === false, good: identification.ok === true }"
            >
              {{ identification.text }}
            </p>
          </form>

          <div class="photo">
            <input
              id="photo"
              ref="fileInput"
              class="visually-hidden"
              type="file"
              accept="image/*"
              capture="environment"
              @change="onFileChosen"
            />
            <label for="photo" class="button secondary">Envoyer une photo du code</label>
            <img v-if="previewUrl" :src="previewUrl" alt="Photo envoyée" class="preview" />
          </div>

          <p class="examples-title" id="examples-title">Essayer avec un exemple</p>
          <ul class="examples" aria-labelledby="examples-title">
            <li v-for="example in EXAMPLES" :key="example.code">
              <button type="button" class="chip" :disabled="loading" @click="useExample(example)">
                {{ example.label }}
              </button>
            </li>
          </ul>
        </section>

        <section aria-labelledby="h-search">
          <h2 id="h-search">Chercher par nom</h2>
          <form class="field-row" @submit.prevent="submitSearch">
            <label for="query">Nom, marque ou catégorie</label>
            <div class="field-line">
              <input id="query" v-model="query" type="search" autocomplete="off" maxlength="100" />
              <button type="submit" class="secondary" :disabled="searching">Chercher</button>
            </div>
          </form>
          <p v-if="searchError" class="error" role="alert">{{ searchError }}</p>
          <template v-if="searchItems">
            <p v-if="searchItems.length === 0" class="muted">Aucun produit ne correspond à cette recherche.</p>
            <ul v-else class="results">
              <li v-for="item in searchItems" :key="item.id">
                <button type="button" class="result-item" @click="openProduct(item)">
                  <span class="result-name">{{ item.name }}</span>
                  <span v-if="item.brand" class="result-brand">{{ item.brand }}</span>
                </button>
              </li>
            </ul>
          </template>
        </section>
      </div>

      <section class="outcome" aria-label="Résultat" aria-live="polite" :aria-busy="loading">
        <div v-if="loading" class="label scanning">
          <p class="scanning-text">Recherche en cours…</p>
          <span class="scanline" aria-hidden="true"></span>
        </div>

        <p v-else-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>

        <ProductLabel v-else-if="result && result.found" :key="result.identifier.value" :result="result" />

        <div v-else-if="result" class="not-found">
          <h3>Aucun produit pour ce code</h3>
          <p>
            {{ result.identifier.type === 'ean13' ? 'EAN-13' : 'QR Code' }}
            <span class="break">{{ result.identifier.value }}</span>
          </p>
          <p class="muted">
            Vérifiez le code, ou cherchez le produit par son nom. Cette absence est gardée un court moment dans le cache.
          </p>
        </div>

        <div v-else class="empty">
          <p>Le produit apparaîtra ici sous forme d’étiquette de rayon.</p>
        </div>
      </section>
    </main>

    <footer class="status">
      <p v-if="statsText">{{ statsText }}</p>
    </footer>
  </div>
</template>
