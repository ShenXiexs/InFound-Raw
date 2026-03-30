import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import IconsResolver from 'unplugin-icons/resolver'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import Icons from 'unplugin-icons/vite'
import { PluginOption } from 'vite'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        output: {
          format: 'cjs'
        }
      },
      bytecode: true
    },
    resolve: {
      alias: {
        '@main': resolve(__dirname, 'src/main'),
        '@common': resolve(__dirname, 'src/common'),
        '@desktop-rpa': resolve(__dirname, '../../packages/frontend.desktop.rpa/src')
      }
    }
  },
  preload: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts')
        },
        output: {
          format: 'cjs'
        }
      },
      bytecode: true
    },
    resolve: {
      alias: {
        '@common': resolve(__dirname, 'src/common'),
        '@desktop-rpa': resolve(__dirname, '../../packages/frontend.desktop.rpa/src')
      }
    }
  },
  renderer: {
    resolve: {
      alias: {
        '@common': resolve(__dirname, 'src/common'),
        '@desktop-rpa': resolve(__dirname, '../../packages/frontend.desktop.rpa/src'),
        '@renderer': resolve('src/renderer/src')
      }
    },
    plugins: [
      vue(),
      AutoImport({
        imports: [
          'vue',
          {
            'naive-ui': ['useDialog', 'useMessage', 'useNotification', 'useLoadingBar']
          }
        ]
      }) as PluginOption,
      Components({
        resolvers: [
          // 自动解析 Icon 组件（核心：识别 i- 前缀的图标）
          IconsResolver({
            // 指定图标集前缀，hugeicons 对应的前缀是 hi
            prefix: 'i',
            // 预设图标集，这里指定 hugeicons
            enabledCollections: ['hugeicons']
          }),
          NaiveUiResolver()
        ]
      }) as PluginOption,
      Icons({
        autoInstall: true
      }) as PluginOption
    ]
  }
})
