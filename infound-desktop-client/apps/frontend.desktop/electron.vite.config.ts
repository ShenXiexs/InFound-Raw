import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import IconsResolver from 'unplugin-icons/resolver'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import Icons from 'unplugin-icons/vite'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        output: {
          format: 'es'
        }
      },
      bytecode: true
    },
    resolve: {
      alias: {
        '@main': resolve(__dirname, 'src/main'),
        '@common': resolve(__dirname, 'src/common')
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
        '@common': resolve(__dirname, 'src/common')
      }
    }
  },
  renderer: {
    resolve: {
      alias: {
        '@common': resolve(__dirname, 'src/common'),
        '@renderer': resolve('src/renderer/src')
      }
    },
    build: {
      minify: true,
      outDir: './out/renderer',
      rollupOptions: {
        input: {
          splash: resolve(__dirname, 'src/renderer/splash.html'),
          index: resolve(__dirname, 'src/renderer/index.html'),
          tkshop: resolve(__dirname, 'src/renderer/tkshop.html'),
          universal: resolve(__dirname, 'src/renderer/universal.html'),
          //updater: resolve(__dirname, 'src/renderer/updater.html'),
          //login: resolve(__dirname, 'src/renderer/login.html')
        }
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
      }),
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
      }),
      Icons({
        // 自动安装缺失的图标集（可选，推荐开启）
        autoInstall: true
      })
    ]
  }
})
