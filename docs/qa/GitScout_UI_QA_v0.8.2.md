# GitScout UI QA · v0.8.2 Editorial Repository Identity

## 目标
将用户选定的方案 3（Editorial Typography）同步到 React 正式项目和独立 HTML 原型，并准备配套 SVG 图标、排行徽章与背景装饰资源。

## 项目名称规范
- Owner 独立显示在上方，小号青蓝色、全大写视觉和较宽字距。
- Repository 名称作为主标题，使用较大字号、较高字重和亮白色。
- 左侧使用青色—蓝色—紫色渐变竖线作为识别锚点。
- Description 位于标题下方，使用灰蓝色次级文字。
- 长仓库名自然换行，不随意截断。
- React 页面在项目库、Trending、Stars、推荐、感兴趣项目、研究、详情与周期对比中复用同一组件。

## 视觉资源
- brand-mark.svg：GitScout 品牌标记
- layers-mark.svg：页面层级图标
- repository-mark.svg：仓库档案图标
- crown-gold.svg / crown-silver.svg / crown-bronze.svg：前三名排行徽章
- neon-waves.svg：背景氛围曲线
- RepositoryIdentity.tsx：Owner / Repository / Description 统一组件
- ProjectRankBadge.tsx：前三名徽章组件

## 项目库布局
- 主区域为项目表格、搜索与语言筛选。
- 右侧包含 Stars TOP 3 和名称样式卡片预览。
- TOP 3 明确标注“当前已加载项目”，不把分页数据误称为全库排名。
- 搜索与语言筛选在已加载项目内即时生效。

## 验收清单
- [x] React 统一项目身份组件。
- [x] 项目库右侧排行与名称预览。
- [x] 本地 SVG 图标资源，无运行时外链依赖。
- [x] HTML 原型同步相同命名层级。
- [x] 长名称换行与窄屏布局规则。
- [x] GitHub Actions 构建与主题检查（Frontend build / Backend tests / Windows setup smoke test 全部通过）。
- [ ] 本地浏览器真实数据视觉回归。
