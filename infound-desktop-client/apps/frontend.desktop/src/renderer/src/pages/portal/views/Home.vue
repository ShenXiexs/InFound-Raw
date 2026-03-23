<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import type { ShopEntryInfoDTO, ShopListInfoDTO } from '@common/types/ipc-type'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'
import ShopEditorDialog from '@renderer/pages/portal/components/ShopEditorDialog.vue'
import { formatBackendDateTime } from '@renderer/utils/date-time'

const TOKEN_INVALID_CODE = 1251
type ShopType = 'CROSS_BORDER' | 'LOCAL'

interface ShopRow extends ShopListInfoDTO {
  remark: string
  lastOpenTime: string
}

const TOTAL_QUOTA = 20
const PAGE_SIZE = 10

const router = useRouter()
const message = useMessage()
const currentPage = ref(1)
const remarkModalVisible = ref(false)
const deleteModalVisible = ref(false)
const editingShopId = ref<string | null>(null)
const editingRemark = ref('')
const deletingShop = ref<ShopRow | null>(null)
const isLoadingShops = ref(false)
const isSavingRemark = ref(false)
const isDeletingShop = ref(false)
const entryIdMap = ref<Map<string, number>>(new Map())
const shopEditorVisible = ref(false)
const shopEditorMode = ref<'add' | 'edit'>('add')
const editingShopForDialog = ref<ShopRow | null>(null)

const shopList = ref<ShopRow[]>([])

const pagedShops = computed<ShopRow[]>(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return shopList.value.slice(start, start + PAGE_SIZE)
})

const totalPages = computed<number>(() => {
  return Math.max(1, Math.ceil(shopList.value.length / PAGE_SIZE))
})

const quotaText = computed<string>(() => `${shopList.value.length}/${TOTAL_QUOTA}`)

const formatType = (type: ShopType): string => {
  return type === 'CROSS_BORDER' ? '跨境店铺' : '本土店铺'
}

const getEntryMapKey = (shopType: ShopType, regionCode: string): string => `${shopType}:${regionCode}`

const ensureEntryIdMap = async (): Promise<boolean> => {
  if (entryIdMap.value.size > 0) return true

  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_GET_ENTRIES)
    if (!result.success) {
      message.error(result.error || '获取店铺入口信息失败')
      return false
    }

    const map = new Map<string, number>()
    ;(result.data || []).forEach((item: ShopEntryInfoDTO, index: number) => {
      const entryId = typeof item.entryId === 'number' ? item.entryId : index + 1
      map.set(getEntryMapKey(item.shopType, item.regionCode), entryId)
    })
    entryIdMap.value = map
    return true
  } catch (error) {
    window.logger.error('获取店铺入口信息失败', error)
    message.error('获取店铺入口信息失败，请稍后重试')
    return false
  }
}

const resolveEntryId = async (shop: ShopRow): Promise<number | null> => {
  if (typeof shop.entryId === 'number') {
    return shop.entryId
  }

  const loaded = await ensureEntryIdMap()
  if (!loaded) return null

  return entryIdMap.value.get(getEntryMapKey(shop.shopType, shop.regionCode)) || null
}

const gotoAddShopPage = (): void => {
  shopEditorMode.value = 'add'
  editingShopForDialog.value = null
  shopEditorVisible.value = true
}

const forceBackToLogin = async (): Promise<void> => {
  try {
    await window.ipc.invoke(IPC_CHANNELS.API_AUTH_LOGOUT)
  } catch {
    // 忽略登出接口失败，继续清理本地状态并跳转登录
  }

  rendererStore.currentState.currentUser = undefined
  rendererStore.currentState.isLogin = false
  rendererStore.currentState.enableDebug = false

  await router.replace({ path: '/login', query: { needLogin: '1' } })
}

const checkTokenOnHome = async (): Promise<void> => {
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.API_AUTH_CHECK_TOKEN)
    if (!result.success && result.code === TOKEN_INVALID_CODE) {
      window.logger.warn('token 失效，准备跳转登录页')
      await forceBackToLogin()
    }
  } catch (error) {
    window.logger.error('主页校验 token 失败', error)
    await forceBackToLogin()
  }
}

const loadShopList = async (): Promise<void> => {
  if (isLoadingShops.value) return

  isLoadingShops.value = true
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_LIST)
    if (!result.success) {
      message.error(result.error || '获取店铺列表失败')
      return
    }

    const list = (result.data || []).map((item) => ({
      ...item,
      remark: item.remark || '',
      entryId: item.entryId,
      lastOpenTime: formatBackendDateTime(item.shopLastOpen || (item as any).lastOpenTime)
    }))

    shopList.value = list
    if (currentPage.value > totalPages.value) {
      currentPage.value = totalPages.value
    }
  } catch (error) {
    window.logger.error('获取店铺列表失败', error)
    message.error('获取店铺列表失败，请稍后重试')
  } finally {
    isLoadingShops.value = false
  }
}

const onPageChange = (page: number): void => {
  currentPage.value = page
}

const openRemarkModal = (row: ShopRow): void => {
  editingShopId.value = row.id
  editingRemark.value = row.remark
  remarkModalVisible.value = true
}

const saveRemark = async (): Promise<void> => {
  if (isSavingRemark.value) return

  const id = editingShopId.value
  if (id === null) return

  const target = shopList.value.find((item) => item.id === id)
  if (!target) return

  const entryId = await resolveEntryId(target)
  if (entryId === null) {
    message.error('缺少 entryId，无法修改备注')
    return
  }

  isSavingRemark.value = true
  try {
    const remark = editingRemark.value.trim()
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_UPDATE, {
      id: target.id,
      name: target.name,
      remark,
      entryId
    })

    if (!result.success) {
      message.error(result.error || '修改备注失败')
      return
    }

    target.remark = remark
    target.entryId = entryId
    remarkModalVisible.value = false
    message.success('备注已保存')
  } catch (error) {
    window.logger.error('修改备注失败', error)
    message.error('修改备注失败，请稍后重试')
  } finally {
    isSavingRemark.value = false
  }
}

const closeRemarkModal = (): void => {
  remarkModalVisible.value = false
}

const onOpenShop = async (row: ShopRow): Promise<void> => {
  const settingId = row.id?.trim()
  if (!settingId) {
    message.error('店铺ID缺失，无法打开店铺窗口')
    return
  }

  const payload = {
    id: settingId,
    name: row.name,
    region: row.regionCode,
    loginUrl: row.loginUrl
  }
  window.logger.info('打开店铺参数', payload)
  window.ipc.send(IPC_CHANNELS.TK_SHOP_OPEN_WINDOW, payload)
  message.success(`已打开店铺：${row.name}`)
}

const onEditShop = (row: ShopRow): void => {
  shopEditorMode.value = 'edit'
  editingShopForDialog.value = { ...row }
  shopEditorVisible.value = true
}

const performDeleteShop = (row: ShopRow): void => {
  shopList.value = shopList.value.filter((item) => item.id !== row.id)
  if (currentPage.value > totalPages.value) {
    currentPage.value = totalPages.value
  }
  message.success(`已删除店铺：${row.name}`)
}

const openDeleteModal = (row: ShopRow): void => {
  deletingShop.value = row
  deleteModalVisible.value = true
}

const closeDeleteModal = (): void => {
  deleteModalVisible.value = false
  deletingShop.value = null
}

const confirmDeleteShop = async (): Promise<void> => {
  if (!deletingShop.value || isDeletingShop.value) return

  const target = deletingShop.value
  isDeletingShop.value = true
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_DELETE, { id: target.id })
    if (!result.success) {
      message.error(result.error || '删除店铺失败')
      return
    }

    performDeleteShop(target)
    closeDeleteModal()
  } catch (error) {
    window.logger.error('删除店铺失败', error)
    message.error('删除店铺失败，请稍后重试')
  } finally {
    isDeletingShop.value = false
  }
}

const onShopEditorSuccess = async (): Promise<void> => {
  await loadShopList()
}

onMounted(() => {
  void checkTokenOnHome()
  void loadShopList()
  window.ipc.send(IPC_CHANNELS.WEBSOCKET_CONNECT)
  window.ipc.send(IPC_CHANNELS.RPA_TASK_START)
})

onUnmounted(async () => {
  window.ipc.send(IPC_CHANNELS.WEBSOCKET_DISCONNECT)
})
</script>

<template>
  <div class="shop-manage-page">
    <n-card :bordered="false" class="shop-manage-card">
      <div class="page-header">
        <h2 class="page-title">店铺管理</h2>
        <div class="header-actions">
          <span class="quota-text">已用/总数：{{ quotaText }}</span>
          <n-button type="primary" @click="gotoAddShopPage">添加店铺</n-button>
        </div>
      </div>

      <n-table :single-line="false" class="shop-table" striped>
        <thead>
          <tr>
            <th class="col-index">序号</th>
            <th class="col-name">店铺名称</th>
            <th class="col-type">店铺类型</th>
            <th class="col-remark">备注</th>
            <th class="col-time">最后打开时间</th>
            <th class="col-actions">管理</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in pagedShops" :key="row.id">
            <td class="td-index">{{ (currentPage - 1) * PAGE_SIZE + idx + 1 }}</td>
            <td class="td-name">
              <div class="name-cell">
                <n-icon class="name-icon" size="16">
                  <i-hugeicons-map-pin />
                </n-icon>
                <span>{{ row.name }}</span>
              </div>
            </td>
            <td class="td-type">{{ formatType(row.shopType) }}</td>
            <td class="td-remark">
              <div class="remark-cell">
                <n-ellipsis :tooltip="false" class="remark-text">
                  {{ row.remark || '-' }}
                </n-ellipsis>
                <n-button class="remark-edit-btn" size="small" text @click="openRemarkModal(row)">
                  <template #icon>
                    <n-icon size="16">
                      <i-hugeicons-pencil />
                    </n-icon>
                  </template>
                </n-button>
              </div>
            </td>
            <td class="td-time">{{ row.lastOpenTime }}</td>
            <td class="td-actions">
              <div class="manage-actions">
                <n-button secondary size="small" @click="onOpenShop(row)">
                  <template #icon>
                    <n-icon>
                      <i-hugeicons-browser />
                    </n-icon>
                  </template>
                  打开
                </n-button>
                <n-button secondary size="small" @click="onEditShop(row)">
                  <template #icon>
                    <n-icon>
                      <i-hugeicons-pencil />
                    </n-icon>
                  </template>
                  编辑
                </n-button>
                <n-button secondary size="small" type="error" @click="openDeleteModal(row)">
                  <template #icon>
                    <n-icon>
                      <i-hugeicons-delete-02 />
                    </n-icon>
                  </template>
                  删除
                </n-button>
              </div>
            </td>
          </tr>
          <tr v-if="pagedShops.length === 0">
            <td class="empty-row" colspan="6">暂无店铺数据</td>
          </tr>
        </tbody>
      </n-table>

      <div class="pagination-wrap">
        <n-pagination :item-count="shopList.length" :page="currentPage" :page-count="totalPages" :page-size="PAGE_SIZE" @update:page="onPageChange" />
      </div>
    </n-card>

    <n-modal v-model:show="remarkModalVisible">
      <n-card :bordered="false" role="dialog" style="width: 520px" title="编辑备注">
        <n-input v-model:value="editingRemark" :autosize="{ minRows: 5, maxRows: 8 }" maxlength="200" placeholder="请输入备注内容" show-count type="textarea" />
        <div class="modal-actions">
          <n-button @click="closeRemarkModal">取消</n-button>
          <n-button :loading="isSavingRemark" type="primary" @click="saveRemark">保存</n-button>
        </div>
      </n-card>
    </n-modal>

    <n-modal v-model:show="deleteModalVisible">
      <n-card :bordered="false" class="delete-modal-card" role="dialog" title="确认删除店铺">
        <div class="delete-modal-content">
          <n-icon color="#d03050" size="28">
            <i-hugeicons-delete-02 />
          </n-icon>
          <p class="delete-modal-text">
            你确定要删除店铺
            <span class="delete-shop-name">「{{ deletingShop?.name || '' }}」</span>
            吗？
          </p>
          <p class="delete-modal-subtext">删除后将无法恢复，请谨慎操作。</p>
        </div>
        <div class="modal-actions">
          <n-button @click="closeDeleteModal">取消</n-button>
          <n-button :loading="isDeletingShop" type="error" @click="confirmDeleteShop">确认删除</n-button>
        </div>
      </n-card>
    </n-modal>

    <shop-editor-dialog v-model:show="shopEditorVisible" :mode="shopEditorMode" :shop="editingShopForDialog" @success="onShopEditorSuccess" />
  </div>
</template>

<style lang="scss" scoped>
.shop-manage-page {
  padding: 20px;
}

.shop-manage-card {
  border-radius: 14px;
  box-shadow: 0 8px 22px rgba(20, 34, 53, 0.08);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  color: #1f2a3d;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.quota-text {
  color: #5b6472;
  font-size: 14px;
}

.shop-table {
  margin-top: 6px;
}

:deep(.shop-table table) {
  width: 100%;
  table-layout: fixed;
}

.col-index {
  width: 70px;
}

.col-name {
  width: 240px;
}

.col-type {
  width: 130px;
}

.col-remark {
  width: 280px;
}

.col-time {
  width: 190px;
}

.col-actions {
  width: 260px;
}

.td-index {
  width: 70px;
}

.td-name {
  width: 240px;
}

.td-type {
  width: 130px;
}

.td-remark {
  width: 280px;
}

.td-time {
  width: 190px;
}

.td-actions {
  width: 260px;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.name-icon {
  color: #8142f6;
}

.remark-cell {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  min-width: 0;
}

.remark-text {
  flex: 1 1 auto;
  min-width: 0;
  line-height: 20px;
  word-break: break-word;
}

.ellipsis-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.remark-edit-btn {
  flex-shrink: 0;
}

.manage-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.empty-row {
  text-align: center;
  color: #8f98a6;
  padding: 28px 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.modal-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.delete-modal-card {
  width: min(680px, calc(100vw - 32px));
}

.delete-modal-content {
  padding: 10px 0 6px;
}

.delete-modal-text {
  margin: 10px 0 6px;
  font-size: 16px;
  color: #2e3748;
}

.delete-shop-name {
  color: #d03050;
  font-weight: 600;
}

.delete-modal-subtext {
  margin: 0;
  color: #8c95a3;
  font-size: 13px;
}

@media (max-width: 900px) {
  .shop-manage-page {
    padding: 12px;
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .pagination-wrap {
    justify-content: flex-start;
  }
}
</style>
