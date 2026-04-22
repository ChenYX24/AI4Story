<script setup lang="ts">
defineProps<{
  compact?: boolean; // compact=true 用作 banner，不占全屏
}>();
const emit = defineEmits<{ (e: "explore"): void }>();
</script>

<template>
  <section
    class="relative w-full overflow-hidden rounded-b-[48px] flex flex-col items-center justify-center text-center"
    :class="compact
      ? 'min-h-[360px] py-10 bg-gradient-to-b from-cinema via-cinema-soft to-[#2a1a0b]'
      : 'min-h-[88vh] py-16 bg-gradient-to-b from-[#1a0f06] via-cinema to-[#2a1a0b]'"
  >
    <!-- 星空 -->
    <div
      class="absolute inset-0 pointer-events-none opacity-60"
      style="background-image:
        radial-gradient(1px 1px at 12% 22%, #fff 50%, transparent 100%),
        radial-gradient(1px 1px at 28% 72%, #fff 50%, transparent 100%),
        radial-gradient(1.5px 1.5px at 46% 42%, #ffd8a6 50%, transparent 100%),
        radial-gradient(1px 1px at 62% 82%, #fff 50%, transparent 100%),
        radial-gradient(1px 1px at 78% 30%, #fff 50%, transparent 100%),
        radial-gradient(1.5px 1.5px at 90% 60%, #ffc97a 50%, transparent 100%),
        radial-gradient(1px 1px at 16% 54%, #fff 50%, transparent 100%),
        radial-gradient(1px 1px at 85% 15%, #fff 50%, transparent 100%);"
    ></div>

    <!-- 上下胶卷齿轨 -->
    <div
      class="absolute left-0 right-0 top-6 h-9"
      style="background: repeating-linear-gradient(90deg, #0f0f0f 0 20px, #1f1f1f 20px 24px, #0f0f0f 24px 44px, #000 44px 48px); border-top: 2px solid #ffcb63; border-bottom: 2px solid #ffcb63; box-shadow: 0 0 30px rgba(255,203,99,0.35);"
    ></div>
    <div
      class="absolute left-0 right-0 bottom-6 h-9"
      style="background: repeating-linear-gradient(90deg, #0f0f0f 0 20px, #1f1f1f 20px 24px, #0f0f0f 24px 44px, #000 44px 48px); border-top: 2px solid #ffcb63; border-bottom: 2px solid #ffcb63; box-shadow: 0 0 30px rgba(255,203,99,0.35);"
    ></div>

    <!-- 主视觉：三帧胶片 -->
    <div class="relative z-[2] flex items-stretch justify-center gap-3 px-6 max-w-[1100px] animate-floaty">
      <!-- 左侧帧 -->
      <div class="hidden sm:grid w-[180px] h-[240px] place-items-center text-[80px] opacity-60 border-2 border-[#3a2a12] bg-[#0b0b0b] shadow-[inset_0_0_30px_rgba(255,203,99,.15)]">🦊</div>
      <!-- 中心帧 -->
      <div
        class="relative grid place-items-center w-[360px] sm:w-[420px] h-[320px] sm:h-[360px] bg-[#0b0b0b] border-2 border-gold text-white"
        style="box-shadow: inset 0 0 60px rgba(255,203,99,.25), 0 0 60px rgba(255,203,99,.55);"
      >
        <div class="relative">
          <div
            class="absolute -inset-8 rounded-full animate-glow-pulse pointer-events-none -z-10"
            style="background: radial-gradient(ellipse at center, rgba(255,203,99,.55) 0%, transparent 60%); filter: blur(14px);"
          ></div>
          <div
            class="text-[52px] sm:text-[62px] font-black tracking-[0.12em] leading-none"
            style="background: linear-gradient(180deg, #fff2d2 0%, #ffcb63 58%, #d59339 100%); -webkit-background-clip: text; background-clip: text; color: transparent; text-shadow: 0 0 20px rgba(255,203,99,.4);"
          >漫秀</div>
          <div class="mt-2 text-xl sm:text-2xl tracking-[0.24em] font-bold text-gold-mute">
            Mind<span class="text-gold">Show</span>
          </div>
          <div class="mt-3 text-[11px] sm:text-xs tracking-[0.24em] text-gold-mute/80">
            AI 互动绘本剧场
          </div>
        </div>
      </div>
      <!-- 右侧帧 -->
      <div class="hidden sm:grid w-[180px] h-[240px] place-items-center text-[80px] opacity-60 border-2 border-[#3a2a12] bg-[#0b0b0b] shadow-[inset_0_0_30px_rgba(255,203,99,.15)]">🌙</div>
    </div>

    <!-- 向下探索 CTA -->
    <button
      v-if="!compact"
      @click="emit('explore')"
      class="mt-8 relative z-[2] px-7 py-3 rounded-full text-sm font-bold tracking-wider text-[#3a1e07] animate-floaty"
      style="background: linear-gradient(135deg, #ffcb63 0%, #ff9048 100%); box-shadow: 0 6px 20px rgba(255,203,99,.45);"
    >向下探索 ↓</button>

    <slot name="overlay" />
  </section>
</template>
