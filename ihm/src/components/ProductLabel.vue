<script setup>
import { computed } from 'vue'
import EanBarcode from './EanBarcode.vue'

const props = defineProps({ result: { type: Object, required: true } })

const product = computed(() => props.result.product)
const barcodeValue = computed(() => product.value.ean13 ?? null)

const identifierLabel = computed(() =>
  props.result.identifier.type === 'ean13' ? 'EAN-13' : 'QR Code'
)

const origin = computed(() => {
  const { source, detected_by: detectedBy } = props.result
  if (source === 'text') return 'Code saisi'
  return detectedBy === 'text' ? 'Photo, numéro lu par reconnaissance de texte' : 'Photo, code lu sur l’image'
})

const cacheText = computed(
  () =>
    ({
      HIT: 'Réponse lue dans le cache Redis',
      MISS: 'Lu en base, puis enregistré dans le cache',
      BYPASS: 'Cache indisponible, lu directement en base',
    })[props.result.cache] ?? props.result.cache
)
</script>

<template>
  <article class="label sweep" :aria-label="`Fiche produit : ${product.name}`">
    <p v-if="product.category" class="label-category">{{ product.category }}</p>
    <div class="label-body">
      <h3 class="label-name">{{ product.name }}</h3>
      <p v-if="product.brand" class="label-brand">{{ product.brand }}</p>
      <p v-if="product.description" class="label-description">{{ product.description }}</p>
      <EanBarcode v-if="barcodeValue" :value="barcodeValue" />
    </div>
    <dl class="label-facts">
      <div>
        <dt>Code lu</dt>
        <dd>{{ identifierLabel }} {{ result.identifier.value }}</dd>
      </div>
      <div>
        <dt>Origine</dt>
        <dd>{{ origin }}</dd>
      </div>
      <div>
        <dt>Cache</dt>
        <dd :data-cache="result.cache">{{ cacheText }}</dd>
      </div>
    </dl>
  </article>
</template>
