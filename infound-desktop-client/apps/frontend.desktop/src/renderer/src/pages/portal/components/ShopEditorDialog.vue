<script lang="ts" setup>
import { computed, reactive, ref, watch } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import type { ShopEntryInfoDTO, ShopListInfoDTO } from '@common/types/ipc-type'

type ShopType = 'cross-border' | 'local' | null
type ApiShopType = 'LOCAL' | 'CROSS_BORDER'
type ShopDialogMode = 'add' | 'edit'

interface ShopDialogProps {
  show: boolean
  mode?: ShopDialogMode
  shop?: ShopListInfoDTO | null
}

interface CountryOption {
  entryId: number
  regionCode: string
  regionName: string
  shopType: ApiShopType
  flag: string
}

interface ShopEntryWithId extends ShopEntryInfoDTO {
  entryId: number
}

interface ShopFormModel {
  storeName: string
  shopType: ShopType
  countryCode: string
  remark: string
  agreementAccepted: boolean
}

const props = withDefaults(defineProps<ShopDialogProps>(), {
  mode: 'add',
  shop: null
})

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'success'): void
}>()

const COUNTRY_FLAG_OPTIONS: Array<{ regionCode: string; flag: string }> = [
  { regionCode: 'UK', flag: '🇬🇧' },
  { regionCode: 'IE', flag: '🇮🇪' },
  { regionCode: 'ES', flag: '🇪🇸' },
  { regionCode: 'FR', flag: '🇫🇷' },
  { regionCode: 'DE', flag: '🇩🇪' },
  { regionCode: 'ID', flag: '🇮🇩' },
  { regionCode: 'TH', flag: '🇹🇭' },
  { regionCode: 'MY', flag: '🇲🇾' },
  { regionCode: 'PH', flag: '🇵🇭' },
  { regionCode: 'SG', flag: '🇸🇬' },
  { regionCode: 'VN', flag: '🇻🇳' },
  { regionCode: 'JP', flag: '🇯🇵' },
  { regionCode: 'AU', flag: '🇦🇺' },
  { regionCode: 'NZ', flag: '🇳🇿' },
  { regionCode: 'US', flag: '🇺🇸' },
  { regionCode: 'CA', flag: '🇨🇦' },
  { regionCode: 'BR', flag: '🇧🇷' },
  { regionCode: 'MX', flag: '🇲🇽' },
  { regionCode: 'AE', flag: '🇦🇪' }
]

const AGREEMENT_TEXT = `寻达店铺授权协议
生效日期：【2026】年【03】月【20】日
发布时间：【2026】年【03】月【20】日
更新日期：【2026】年【03】月【20】日

《寻达店铺授权协议》（以下简称《本协议》）是您（自然人、法人或其他组织）与华钥网络科技有限公司之间用户使用寻达软件同意授权店铺的协议。

请您务必谨慎阅读、充分理解本协议各条款内容，特别是免除或者限制责任的条款（以加粗形式提示注意），并选择接受或不接受。一旦您使用“软件服务”，即表明您完全同意并接受本协议各项条款，同时包括接受软件服务对协议各项条款随时所做的任何修改。如果您不同意本协议中的条款，您无权使用本“软件服务”或其任何更新。

一、授权内容

依据本协议精准界定的约定范畴，您特此授予寻达在协议生效期间，仅基于为用户提供约定服务之必要目的，对经授权的 TikTok 店铺数据享有读取权限。该权限涵盖的数据范围包括但不限于：达人广场提供的公共达人信息，如达人名称、达人 ID、达人联系方式、达人的建联数据、达人带货数据等；店铺基础信息，例如店铺名称、店铺 Id、店铺头像等（但不包含店铺订单信息）。核心目的在于，使寻达能够凭借上述数据，为用户提供诸如实现达人建联过滤筛选进而提升达人建联效率、开展达人数据深度剖析挖掘等软件特定功能及衍生相关其他关于达人邀约的服务和功能。
请您充分知悉并深入理解，我方为您提供的功能与服务处于持续动态更新、迭代及拓展延伸状态。若存在某一功能或服务不在上述预先详细说明的范畴内，但涉及收集您的信息，我方将严格依照现行有效的法律法规要求，通过在软件页面设置清晰醒目的提示、构建符合规范标准的交互流程、发布于网站的官方公告等合法合规且具有公示效力的方式，另行向您全面、详尽地阐释信息收集的具体内容及确切范围。同时，明确在未获得用户同意前，禁止对新功能或服务相关数据进行任何实质性收集或使用，以此充分保障您作为数据主体依法享有的知情权与同意权，确保相关数据处理活动完全符合法律规定及本协议的明确约定 。


二、双方权利与义务

用户权利义务

1）用户有权监督寻达对授权权限的使用情况，确保寻达严格按照本协议约定的目的和范围使用店铺相关数据和权限。
2）用户应按照 Tiktok 平台规则及本协议约定，保证其店铺的合法运营，并向寻达提供真实、准确、完整的店铺数据以便寻达顺利获取授权数据。
3）用户可随时终止本授权协议，并要求寻达立即停止使用店铺相关权限及数据，但同时用户不可再使用寻达软件服务。

寻达权力及义务
1）寻达有权在授权范围内使用用户提供的 Tiktok 店铺数据及权限，用于开发、优化和运营与本协议约定功能或服务相关的软件产品或服务。
2）寻达应严格遵守保密义务，对在授权过程中获取的用户店铺数据及其他商业秘密予以保密，不得向任何第三方披露、转让或用于其他未经甲方书面同意的目的。
3）寻达应采取必要的技术和管理措施，保障用户店铺数据的安全，防止数据泄露、篡改或丢失。
4）寻达应按照本协议约定的功能或服务内容，为用户提供稳定、可靠的软件产品或服务，并及时处理用户在使用过程中提出的问题和建议。

三、数据使用与保护

1）寻达仅可在本协议明确授权的业务场景下使用用户店铺数据，不得将数据用于其他任何目的或与任何第三方共享数据，除非获得用户的另行书面授权。
2）寻达应建立健全的数据安全管理制度，对店铺数据进行分类存储、加密处理，并定期进行数据备份。在数据使用过程中，应遵循最小化原则，仅获取实现授权功能所必需的数据，并在使用完毕后及时删除相关数据。


四、协议的变更与解除

本协议的任何变更或补充需经双方书面协商一致，并签署相关协议或书面文件后方可生效。
我司有权根据业务发展和法律法规的要求，对本软件的服务内容和功能进行变更、暂停或终止。
若因上述变更导致您无法继续使用或相关功能受到影响，我司将提前通知您，并尽量提供合理的解决方案。

五、争议解决

本协议的签订、履行、解释及争议解决均适用中华人民共和国法律。如双方在本协议履行过程中发生争议，应首先通过友好协商解决；协商不成的，任何一方均有权向有管辖权的人民法院提起诉讼。`

const FLAG_MAP = new Map(COUNTRY_FLAG_OPTIONS.map((item) => [item.regionCode, item.flag]))

const message = useMessage()
const formRef = ref<FormInst | null>(null)
const isSubmitting = ref(false)
const isLoadingEntries = ref(false)
const hasLoadedEntries = ref(false)
const shopEntries = ref<ShopEntryWithId[]>([])

const getInitialForm = (): ShopFormModel => ({
  storeName: '',
  shopType: null,
  countryCode: '',
  remark: '',
  agreementAccepted: false
})

const formValue = reactive<ShopFormModel>(getInitialForm())

const modalVisible = computed<boolean>({
  get: () => props.show,
  set: (value) => emit('update:show', value)
})

const isEditMode = computed<boolean>(() => props.mode === 'edit')
const dialogTitle = computed<string>(() => (isEditMode.value ? '编辑店铺' : '添加新店铺'))
const submitBtnText = computed<string>(() => (isEditMode.value ? '保存修改' : '授权添加'))

const apiShopTypeToFormType = (type: ApiShopType): ShopType => {
  return type === 'LOCAL' ? 'local' : 'cross-border'
}

const effectiveShopType = computed<ApiShopType>(() => {
  return formValue.shopType === 'local' ? 'LOCAL' : 'CROSS_BORDER'
})

const countryOptions = computed<CountryOption[]>(() => {
  const list = shopEntries.value.filter((item) => item.shopType === effectiveShopType.value)
  const dedup = new Map<string, CountryOption>()

  for (const item of list) {
    if (!dedup.has(item.regionCode)) {
      dedup.set(item.regionCode, {
        entryId: item.entryId,
        regionCode: item.regionCode,
        regionName: item.regionName,
        shopType: item.shopType,
        flag: FLAG_MAP.get(item.regionCode) || '🌐'
      })
    }
  }

  return Array.from(dedup.values())
})

const rules: FormRules = {
  storeName: [
    {
      required: true,
      validator: () => {
        const storeName = formValue.storeName.trim()
        if (storeName.length < 1) {
          return new Error('请输入店铺名称')
        }
        if (storeName.length > 50) {
          return new Error('店铺名称长度不能超过50个字符')
        }
        return true
      },
      trigger: ['input', 'blur']
    }
  ],
  shopType: [
    {
      required: true,
      validator: () => {
        if (!formValue.shopType) {
          return new Error('请选择店铺类型')
        }
        return true
      },
      trigger: ['change', 'blur']
    }
  ],
  countryCode: [
    {
      required: true,
      validator: () => {
        if (!formValue.countryCode) {
          return new Error('请选择店铺国家')
        }
        return true
      },
      trigger: ['change', 'blur']
    }
  ],
  agreementAccepted: [
    {
      required: true,
      validator: () => {
        if (!formValue.agreementAccepted) {
          return new Error('请阅读并同意授权协议')
        }
        return true
      },
      trigger: ['change', 'blur']
    }
  ],
  remark: [
    {
      validator: () => {
        if (formValue.remark.length > 200) {
          return new Error('备注不能超过200字')
        }
        return true
      },
      trigger: ['input', 'blur']
    }
  ]
}

const resetForm = (): void => {
  Object.assign(formValue, getInitialForm())
  formRef.value?.restoreValidation()
}

const applyEditFormValue = (shop: { name: string; shopType: ApiShopType; regionCode: string; remark?: string }): void => {
  formValue.storeName = shop.name || ''
  formValue.shopType = apiShopTypeToFormType(shop.shopType)

  const availableCountryCodes = new Set(countryOptions.value.map((item) => item.regionCode))
  formValue.countryCode = availableCountryCodes.has(shop.regionCode) ? shop.regionCode : ''
  formValue.remark = shop.remark || ''
  formValue.agreementAccepted = true
}

const loadShopEntries = async (): Promise<boolean> => {
  if (isLoadingEntries.value) return false
  if (hasLoadedEntries.value) return true

  isLoadingEntries.value = true
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_GET_ENTRIES)
    if (!result.success) {
      message.error(result.error || '获取店铺入口信息失败')
      return false
    }

    const entries = result.data || []
    shopEntries.value = entries.map((item, index) => ({
      ...item,
      entryId: typeof item.entryId === 'number' ? item.entryId : index + 1
    }))
    hasLoadedEntries.value = true
    return true
  } catch (error) {
    window.logger.error('获取店铺入口信息失败', error)
    message.error('获取店铺入口信息失败，请稍后重试')
    return false
  } finally {
    isLoadingEntries.value = false
  }
}

const hydrateFormForDialog = async (): Promise<void> => {
  resetForm()
  const loaded = await loadShopEntries()
  if (!loaded) return

  if (!isEditMode.value) return

  if (!props.shop?.id) {
    message.error('缺少店铺信息，无法编辑')
    return
  }

  applyEditFormValue({
    name: props.shop.name,
    shopType: props.shop.shopType,
    regionCode: props.shop.regionCode,
    remark: props.shop.remark || ''
  })
}

const onTypeChange = (value: ShopType): void => {
  formValue.shopType = value
  const availableCountryCodes = new Set(countryOptions.value.map((item) => item.regionCode))
  if (!availableCountryCodes.has(formValue.countryCode)) {
    formValue.countryCode = ''
  }
}

const onSelectCountry = (regionCode: string): void => {
  formValue.countryCode = regionCode
}

const onClose = (): void => {
  modalVisible.value = false
}

const onSubmit = async (): Promise<void> => {
  if (isSubmitting.value) return

  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  const selectedCountry = countryOptions.value.find((item) => item.regionCode === formValue.countryCode)
  if (!selectedCountry) {
    message.error('请选择店铺国家')
    return
  }

  isSubmitting.value = true
  try {
    const basePayload = {
      name: formValue.storeName.trim(),
      entryId: selectedCountry.entryId,
      remark: formValue.remark.trim()
    }

    if (isEditMode.value) {
      const shopId = props.shop?.id?.trim()
      if (!shopId) {
        message.error('缺少店铺ID，无法修改')
        return
      }

      const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_UPDATE, {
        id: shopId,
        ...basePayload
      })
      if (!result.success) {
        message.error(result.error || '修改店铺失败')
        return
      }
    } else {
      const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_ADD, basePayload)
      if (!result.success) {
        message.error(result.error || '新建店铺失败')
        return
      }
    }

    message.success(isEditMode.value ? '修改店铺成功' : '添加店铺成功')
    emit('success')
    modalVisible.value = false
  } catch (error) {
    window.logger.error(isEditMode.value ? '修改店铺失败' : '新建店铺失败', error)
    message.error(isEditMode.value ? '修改店铺失败，请稍后重试' : '新建店铺失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      void hydrateFormForDialog()
      return
    }

    resetForm()
  }
)

watch(
  () => [props.mode, props.shop?.id] as const,
  () => {
    if (props.show) {
      void hydrateFormForDialog()
    }
  }
)
</script>

<template>
  <n-modal v-model:show="modalVisible" :mask-closable="true">
    <n-card class="shop-form-card" :bordered="false" role="dialog">
      <template #header>
        <div class="page-header">
          <n-h2 class="page-title">{{ dialogTitle }}</n-h2>
          <n-button circle class="close-btn" quaternary @click="onClose">
            <span class="close-icon">×</span>
          </n-button>
        </div>
      </template>

      <n-form ref="formRef" :model="formValue" :rules="rules" label-placement="top" size="large">
        <n-form-item label="店铺名称" path="storeName" required>
          <n-input v-model:value="formValue.storeName" maxlength="50" show-count clearable placeholder="请输入店铺名称" />
        </n-form-item>

        <n-form-item label="店铺类型" path="shopType" required>
          <n-radio-group :value="formValue.shopType" :disabled="isEditMode" @update:value="onTypeChange">
            <n-space>
              <n-radio-button value="cross-border">跨境店铺</n-radio-button>
              <n-radio-button value="local">本土店铺</n-radio-button>
            </n-space>
          </n-radio-group>
        </n-form-item>

        <n-form-item label="选择国家" path="countryCode" required>
          <n-spin :show="isLoadingEntries">
            <n-space class="country-grid" :size="10">
              <n-button
                v-for="country in countryOptions"
                :key="country.regionCode"
                :secondary="formValue.countryCode === country.regionCode"
                :type="formValue.countryCode === country.regionCode ? 'primary' : 'default'"
                :color="formValue.countryCode === country.regionCode ? '#8142f6' : undefined"
                :text-color="formValue.countryCode === country.regionCode ? '#ffffff' : undefined"
                :disabled="isEditMode"
                class="country-btn"
                @click="onSelectCountry(country.regionCode)"
              >
                <span class="flag">{{ country.flag }}</span>
                <span>{{ country.regionName }}</span>
              </n-button>
            </n-space>
          </n-spin>
        </n-form-item>

        <n-form-item label="备注" path="remark">
          <n-input v-model:value="formValue.remark" type="textarea" :autosize="{ minRows: 3, maxRows: 4 }" maxlength="200" show-count placeholder="请输入备注（选填，200字内）" />
        </n-form-item>

        <n-form-item path="agreementAccepted" required class="agreement-check-item">
          <n-checkbox v-model:checked="formValue.agreementAccepted">我已阅读并同意授权协议</n-checkbox>
        </n-form-item>

        <n-form-item label="授权协议正文">
          <div class="agreement-wrap">
            <textarea class="agreement-text" :value="AGREEMENT_TEXT" readonly rows="5" />
          </div>
        </n-form-item>

        <div class="action-row">
          <n-button :loading="isSubmitting" type="primary" color="#8142f6" text-color="#ffffff" @click="onSubmit">{{ submitBtnText }}</n-button>
          <n-button @click="onClose">取消</n-button>
        </div>
      </n-form>
    </n-card>
  </n-modal>
</template>

<style lang="scss" scoped>
.shop-form-card {
  width: min(860px, calc(100vw - 32px));
  height: 80vh;
  max-height: 80vh;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
}

.shop-form-card :deep(.n-card__content) {
  overflow-y: auto;
}

.page-title {
  margin: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.close-btn {
  flex-shrink: 0;
}

.close-icon {
  font-size: 20px;
  line-height: 1;
}

.country-grid {
  width: 100%;
}

.country-btn {
  min-width: 132px;
  justify-content: flex-start;
}

.flag {
  margin-right: 6px;
  font-size: 18px;
  line-height: 1;
}

.agreement-wrap {
  width: 100%;
  border: 1px solid #d9dce3;
  border-radius: 8px;
  background: #fafbfc;
}

.agreement-text {
  width: 100%;
  min-height: 110px;
  max-height: 320px;
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  padding: 10px 12px;
  border: none;
  background: transparent;
  resize: vertical;
  outline: none;
  font-size: 13px;
  line-height: 1.6;
  color: #3f4856;
}

.action-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

:deep(.agreement-check-item) {
  margin-top: -40px;
}

@media (max-width: 760px) {
  .country-btn {
    min-width: 120px;
  }
}
</style>
