<script setup>
import { computed } from 'vue'
import { ean13Bars, isGuard } from '../ean13.js'

const props = defineProps({ value: { type: String, required: true } })

// 95 modules de barres + zones de silence (9 à gauche, 7 à droite), chiffres sous les barres.
const QUIET_LEFT = 9
const WIDTH = QUIET_LEFT + 95 + 7
const BAR_HEIGHT = 52
const GUARD_HEIGHT = 58

const path = computed(() =>
  ean13Bars(props.value)
    .map(({ start, length }) => {
      const h = isGuard(start, length) ? GUARD_HEIGHT : BAR_HEIGHT
      return `M${QUIET_LEFT + start} 0h${length}v${h}h-${length}z`
    })
    .join('')
)

const groups = computed(() => [
  { text: props.value[0], x: QUIET_LEFT / 2 },
  { text: props.value.slice(1, 7), x: QUIET_LEFT + 3 + 21 },
  { text: props.value.slice(7), x: QUIET_LEFT + 50 + 21 },
])
</script>

<template>
  <svg
    class="barcode"
    :viewBox="`0 0 ${WIDTH} ${GUARD_HEIGHT + 12}`"
    role="img"
    :aria-label="`Code-barres EAN-13 ${value}`"
  >
    <rect :width="WIDTH" :height="GUARD_HEIGHT + 12" fill="#fff" />
    <path :d="path" fill="#17212e" />
    <text
      v-for="g in groups"
      :key="g.x"
      :x="g.x"
      :y="GUARD_HEIGHT + 9"
      text-anchor="middle"
      class="barcode-digits"
    >
      {{ g.text }}
    </text>
  </svg>
</template>
