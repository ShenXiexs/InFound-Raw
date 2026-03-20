# 迅达桌面客户端项目说明文档

## 项目概述

这是一个基于 Electron + Vue 3 + TypeScript 构建的桌面应用程序，主要用于 TikTok 达人营销业务。项目采用 monorepo 结构，包含主应用和
RPA 模拟器两个主要部分。

当前仓库中的公开版本已经完成脱敏处理：

- 所有环境地址、注册链接、自动更新地址统一替换为占位符或 `example.com`
- 文档中的账号、应用密码、Creator ID 等示例数据已替换为演示值
- 嵌套仓库的 `.git` 元数据已移除，避免泄露内部远端地址

## 技术栈

- **主框架**: Electron 40.6.0
- **前端框架**: Vue 3.5.28
- **构建工具**: Vite 7.3.1
- **语言**: TypeScript 5.9.3
- **状态管理**: Pinia (Vue) + 自定义全局状态
- **UI 组件库**: Naive UI
- **网络请求**: 自定义封装
- **数据持久化**: electron-store + 系统钥匙串
- **自动化**: Playwright + playwright-core

## 项目结构

```
infound-desktop-client/
├── apps/
│   ├── frontend.desktop/           # 主桌面应用
│   └── frontend.rpa.simulation/    # RPA 模拟器
├── packages/
│   └── frontend.desktop.shared/    # 共享包
├── package.json
└── pnpm-workspace.yaml
```

## 核心模块详解

### 1. 主应用 (frontend.desktop)

#### 1.1 目录结构

```
src/
├── common/                 # 公共配置和类型定义
│   ├── app-config.ts      # 应用配置管理
│   ├── app-constants.ts   # 常量定义
│   └── types/             # 公共类型定义
├── main/                  # 主进程代码
│   ├── index.ts          # 主进程入口
│   ├── modules/          # 功能模块
│   │   ├── ipc/          # IPC 通信
│   │   ├── state/        # 全局状态管理
│   │   ├── store/        # 数据持久化
│   │   └── exception/    # 异常处理
│   ├── services/         # 业务服务层
│   ├── utils/            # 工具函数
│   └── windows/          # 窗口管理
├── preload/              # 预加载脚本
└── renderer/             # 渲染进程代码
    ├── src/
    │   ├── pages/        # 页面组件
    │   ├── components/   # 公共组件
    │   └── store/        # 前端状态管理
    └── index.html        # 入口 HTML
```

#### 1.2 核心概念

**IPC 通信机制**

- 使用装饰器模式管理 IPC 调用
- 分为控制器基类和具体实现
- 支持类型安全的通信

**状态管理模式**

```
主进程状态 ←→ 渲染进程状态 (Pinia)
     ↓
   持久化存储 (electron-store)
```

**窗口管理系统**

- 主窗口管理
- 启动页窗口
- TK WebContentsView 窗口

#### 1.3 关键文件说明

**main/index.ts**

```typescript
// 主进程入口点
// 负责应用生命周期管理、窗口创建、IPC 初始化等
```

**modules/state/global-state.ts**

```typescript
// 全局状态管理器
// 统一管理应用状态的内存存储和持久化
```

**modules/store/app-store.ts**

```typescript
// 数据持久化层
// 使用 electron-store 管理配置数据
// 敏感信息存储在系统钥匙串中
```

### 2. 共享包 (frontend.desktop.shared)

包含可复用的工具函数、类型定义和服务：

- 日志服务
- RPA 自动化引擎
- 工具函数集合
- 类型定义

### 3. RPA 模拟器

用于模拟用户操作的独立应用，结构与主应用类似但更轻量。

## 开发环境搭建

### 1. 环境要求

- Node.js 18+
- pnpm 8+
- Python 3.7+ (用于 node-gyp)

### 2. 安装依赖

```bash
pnpm install
```

### 2.1 环境变量

`apps/frontend.desktop/.env.stg` 与 `apps/frontend.desktop/.env.pro` 仅保留演示占位值，接入真实环境前请改为本地私有配置，不要直接提交真实域名、盐值、Token 或账号信息。

### 3. 开发启动

```bash
# 启动主应用开发环境
pnpm --filter frontend.desktop dev

# 启动 RPA 模拟器
pnpm --filter frontend.rpa.simulation dev
```

## 核心功能模块

### 1. 用户认证系统

- Token 管理（系统钥匙串存储）
- 用户信息持久化
- 登录状态同步

### 2. 网络请求层

- 基于 Electron net 模块封装
- 自动处理 Cookie 和 Token
- 请求/响应拦截器

### 3. IPC 通信系统

- 类型安全的进程间通信
- 装饰器简化 API 定义
- 自动错误处理

### 4. 状态同步机制

```
主进程 ↔ 渲染进程
  ↓
持久化存储
```

### 5. RPA 自动化

- 元素定位引擎
- 操作执行器
- 人机交互模拟

## 代码规范

### 1. TypeScript 配置

- 严格模式开启
- 类型推导优先
- 接口优于类型别名

### 2. 代码风格

- 使用 Prettier 格式化
- ESLint 静态检查
- 提交前自动格式化

### 3. 命名约定

- 类名：PascalCase
- 变量/函数：camelCase
- 常量：UPPER_SNAKE_CASE
- 私有成员：下划线前缀

## 调试技巧

### 1. 主进程调试

```bash
# 在开发者工具中调试主进程
npm run dev -- --inspect=5858
```

### 2. 渲染进程调试

- 使用 Vue DevTools
- Chrome 开发者工具

### 3. 日志查看

```bash
# 查看应用日志
# Windows: %APPDATA%\{app-name}\logs\
# macOS: ~/Library/Logs/{app-name}/
```

## 常见问题

### 1. 依赖安装失败

```bash
# 清理缓存重新安装
pnpm store prune
pnpm install --force
```

### 2. 构建问题

```bash
# 检查类型错误
pnpm run typecheck

# 清理构建缓存
rm -rf out/ dist/
pnpm run build
```

### 3. IPC 通信问题

- 检查通道名称是否匹配
- 确认参数类型正确
- 查看主进程日志

## 部署发布

### 1. 构建命令

```bash
# Windows
pnpm run build:win

# macOS
pnpm run build:mac

# Linux
pnpm run build:linux
```

### 2. 自动更新配置

- 使用 electron-updater
- 配置你自己的更新服务器地址
- 版本号管理

## 最佳实践

1. **状态管理**: 优先使用全局状态，避免组件间直接通信
2. **错误处理**: 统一异常处理机制，提供友好的错误提示
3. **性能优化**: 合理使用缓存，避免频繁的 IPC 调用
4. **安全性**: 敏感信息加密存储，启用上下文隔离
5. **可维护性**: 保持代码模块化，良好的注释和文档

## 学习资源

- [Electron 官方文档](https://www.electronjs.org/docs)
- [Vue 3 官方文档](https://vuejs.org/)
- [TypeScript 手册](https://www.typescriptlang.org/docs/)
- [Playwright 文档](https://playwright.dev/)

---

这份文档为新开发者提供了项目的整体概览和技术细节，帮助快速上手开发工作。建议结合实际代码阅读来深入理解各个模块的具体实现。
