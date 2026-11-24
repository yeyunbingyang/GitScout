# GitScout v0.8.2 · Editorial Repository Identity

> 用户选定的方案 3（Editorial Typography）作为仓库名称的正式展示规范，适用于 React 正式应用与独立 HTML 原型。

## 1. 目标

解决 `owner/repository` 连续字符串过长、层级不清、在窄表格和排名小组件中难以快速扫描的问题。保留 GitHub 仓库的真实名称与跳转目标，不改变数据模型、API、采集逻辑和 SQLite schema。

## 2. 名称排版

| 层级 | 规则 | 视觉 |
|---|---|---|
| Owner | 从 `full_name` 拆分；视觉上大写展示 | 小号青蓝色、较宽字距 |
| Repository | 显示仓库真实名称，不显示 owner 前缀 | 大号加粗、亮白色 |
| Accent | 名称块左侧竖向识别线 | 紫 → 蓝 → 青渐变与柔和外发光 |
| Description | 仓库简介或当前页面上下文 | 灰蓝色、小字号、自然换行 |
| Rank | 与名称块独立呈现 | 数字徽标；前三名可用金银铜皇冠 |

Owner 的大写仅是 CSS 视觉转换，不改写 GitHub 原始 owner 字段。标题保留真实大小写和连字符。

## 3. 组件规格

React 使用 `frontend/src/components/RepositoryIdentity.tsx`，支持：

- `table`：榜单与表格行。
- `compact`：紧凑排行、研究列表与摘要。
- `card`：右侧名称预览卡片。
- `hero`：项目详情页主标题。

`to` 属性存在时使用 React Router 内部链接；不传 `to` 时以普通标题展示。外部 GitHub 链接继续由所在页面单独提供，避免把内部详情与外链动作混为一体。

## 4. 图标与效果资源

所有资源保存在 `frontend/public/assets/gitscout/`，运行时不依赖第三方图标 CDN。

| 文件 | 用途 |
|---|---|
| `brand-mark.svg` | GitScout 品牌图标，青蓝紫渐变描边 |
| `layers-mark.svg` | 页面标题与项目库层级图标 |
| `repository-mark.svg` | 仓库详情档案图标 |
| `crown-gold.svg` | 排名第一 |
| `crown-silver.svg` | 排名第二 |
| `crown-bronze.svg` | 排名第三 |
| `neon-waves.svg` | 右下方低透明度氛围曲线 |
| `icon-preview.svg` | 本地 SVG 资源总览 |

Lucide React 继续承担导航、搜索、筛选、状态、图表操作等常规线性图标。自定义 SVG 只用于品牌、仓库识别、前三名徽章和装饰性光效。

## 5. 动效与可访问性

- 品牌与徽章使用 `drop-shadow`，不为每个普通图标添加强烈光晕。
- 表格标题 hover 只增强文字与焦点，不改变布局尺寸。
- 卡片 hover 位移控制在 1px。
- 遵循 `prefers-reduced-motion`。
- 装饰性 SVG 使用空 alt 或 `aria-hidden`；交互链接必须保留可读的仓库名称。

## 6. 页面覆盖

- 项目库、日 / 周 / 月榜、Stars 总榜。
- 智能推荐、周期趋势对比。
- 感兴趣项目、项目研究。
- 仓库详情、趋势总览中的热门项目。

## 7. 不在本版本范围内

- 不修改 owner / repository 的数据库字段。
- 不更改 Stars、日榜、周榜、月榜推荐权重与计算逻辑。
- 不更换 React、FastAPI、SQLite 技术栈。
- 不把静态示例数据写入正式数据库。
