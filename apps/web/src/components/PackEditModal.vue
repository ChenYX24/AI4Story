<script setup lang="ts">
import { ref, watch, computed } from "vue";
import BaseButton from "./BaseButton.vue";
import BaseModal from "./BaseModal.vue";
import { useAssetShelfStore } from "@/stores/assetShelf";
import { useToastStore } from "@/stores/toast";
import { createPack, updatePack } from "@/api/endpoints";
import type { PackOut } from "@/api/endpoints";

const props = defineProps<{
  open: boolean;
  editPack?: PackOut | null;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", pack: PackOut): void;
}>();

const assetShelf = useAssetShelfStore();
const toast = useToastStore();

const name = ref("");
const description = ref("");
const isPublic = ref(false);
const selected = ref<Set<string>>(new Set());
const busy = ref(false);

const isEdit = computed(() => !!props.editPack);

watch(() => props.open, (v) => {
  if (!v) return;
  if (props.editPack) {
    name.value = props.editPack.name;
    description.value = props.editPack.description || "";
    isPublic.value = props.editPack.public;
    selected.value = new Set(props.editPack.asset_ids);
  } else {
    name.value = "";
    description.value = "";
    isPublic.value = false;
    selected.value = new Set();
  }
});

function toggle(id: string) {
  const s = new Set(selected.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  selected.value = s;
}

async function submit() {
  if (!name.value.trim()) { toast.push("请输入包名", "warn"); return; }
  if (selected.value.size === 0) { toast.push("至少选一件资产", "warn"); return; }
  busy.value = true;
  try {
    let pack: PackOut;
    const ids = Array.from(selected.value);
    if (isEdit.value && props.editPack) {
      pack = await updatePack(props.editPack.code, {
        name: name.value.trim(),
        description: description.value.trim(),
        asset_ids: ids,
        public: isPublic.value,
      });
    } else {
      pack = await createPack({
        name: name.value.trim(),
        description: description.value.trim(),
        asset_ids: ids,
        public: isPublic.value,
      });
    }
    toast.push(isEdit.value ? "已更新" : `分享码 ${pack.code} 已生成`, "success");
    emit("saved", pack);
  } catch (e: any) {
    toast.push(e?.message || "操作失败", "error");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <BaseModal :open="open" :title="isEdit ? '编辑资产包' : '创建资产包'" max-width="520px" @close="emit('close')">
    <label class="block mb-3">
      <span class="text-xs text-ink-soft block mb-1">包名</span>
      <input v-model="name" maxlength="30" type="text" placeholder="如：我的角色合集"
             class="w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft" />
    </label>
    <label class="block mb-3">
      <span class="text-xs text-ink-soft block mb-1">描述（可选）</span>
      <textarea v-model="description" rows="2" maxlength="120" placeholder="简单介绍一下这个包"
                class="w-full px-3 py-2 rounded-lg border border-paper-edge bg-white focus:outline-none focus:border-accent-soft resize-y"></textarea>
    </label>
    <label class="flex items-center gap-2 text-sm text-ink-soft mb-4">
      <input type="checkbox" v-model="isPublic" class="accent-accent" />
      公开到资产商城
    </label>

    <div class="text-xs text-ink-soft mb-2">选择资产 ({{ selected.size }} / {{ assetShelf.myAssets.length }})</div>
    <div class="max-h-52 overflow-y-auto border border-paper-edge rounded-lg p-2 grid grid-cols-4 gap-2">
      <div
        v-for="a in assetShelf.myAssets"
        :key="a.id"
        class="aspect-square rounded-lg p-1 grid place-items-center cursor-pointer border-2 transition relative"
        :class="selected.has(a.id) ? 'border-accent bg-accent/10' : 'border-transparent bg-paper-deep hover:bg-gold-mute'"
        @click="toggle(a.id)"
      >
        <img :src="a.url" :alt="a.name" class="max-w-full max-h-full object-contain" />
        <span v-if="selected.has(a.id)" class="absolute top-0.5 right-0.5 w-4 h-4 grid place-items-center bg-accent text-white rounded-full text-[10px]">✓</span>
      </div>
      <div v-if="assetShelf.myAssets.length === 0" class="col-span-4 text-center py-6 text-xs text-ink-mute">
        还没有自创资产
      </div>
    </div>

    <template #footer>
      <BaseButton variant="soft" pill @click="emit('close')">取消</BaseButton>
      <BaseButton pill :disabled="busy || !name.trim() || selected.size === 0" @click="submit">
        {{ busy ? '处理中…' : isEdit ? '保存' : '创建' }}
      </BaseButton>
    </template>
  </BaseModal>
</template>
