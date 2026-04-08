// 显式导入所有可能用到的国旗图标
import ICircleFlagsCn from '~icons/circle-flags/cn'
import ICircleFlagsUs from '~icons/circle-flags/us'
import ICircleFlagsJp from '~icons/circle-flags/jp'
import ICircleFlagsKr from '~icons/circle-flags/kr'
import ICircleFlagsVn from '~icons/circle-flags/vn'
import ICircleFlagsTh from '~icons/circle-flags/th'
import ICircleFlagsId from '~icons/circle-flags/id'
import ICircleFlagsMy from '~icons/circle-flags/my'
import ICircleFlagsPh from '~icons/circle-flags/ph'
import ICircleFlagsSg from '~icons/circle-flags/sg'
import ICircleFlagsGb from '~icons/circle-flags/gb'
import ICircleFlagsIe from '~icons/circle-flags/ie'
import ICircleFlagsEs from '~icons/circle-flags/es'
import ICircleFlagsFr from '~icons/circle-flags/fr'
import ICircleFlagsDe from '~icons/circle-flags/de'
import ICircleFlagsAu from '~icons/circle-flags/au'
import ICircleFlagsNz from '~icons/circle-flags/nz'
import ICircleFlagsCa from '~icons/circle-flags/ca'
import ICircleFlagsBr from '~icons/circle-flags/br'
import ICircleFlagsMx from '~icons/circle-flags/mx'
import ICircleFlagsAe from '~icons/circle-flags/ae'

// 国旗图标组件映射
const FLAG_COMPONENTS: Record<string, any> = {
  CN: ICircleFlagsCn,
  US: ICircleFlagsUs,
  JP: ICircleFlagsJp,
  KR: ICircleFlagsKr,
  VN: ICircleFlagsVn,
  TH: ICircleFlagsTh,
  ID: ICircleFlagsId,
  MY: ICircleFlagsMy,
  PH: ICircleFlagsPh,
  SG: ICircleFlagsSg,
  UK: ICircleFlagsGb,
  GB: ICircleFlagsGb,
  IE: ICircleFlagsIe,
  ES: ICircleFlagsEs,
  FR: ICircleFlagsFr,
  DE: ICircleFlagsDe,
  AU: ICircleFlagsAu,
  NZ: ICircleFlagsNz,
  CA: ICircleFlagsCa,
  BR: ICircleFlagsBr,
  MX: ICircleFlagsMx,
  AE: ICircleFlagsAe
}

// 获取国旗图标组件
const getFlagComponent = (regionCode: string): any => {
  const code = (regionCode || 'CN').toUpperCase()
  return FLAG_COMPONENTS[code] || ICircleFlagsCn
}

export { getFlagComponent }
