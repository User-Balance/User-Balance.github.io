# 技术学习手册

[线上门户](https://user-balance.github.io/) · 仓库 `User-Balance/User-Balance.github.io`

中文 HTML 教程门户，涵盖 AI Infra、GPU 架构、算子优化和 Linux 运维。站点只展示教程，不提供旧博客、旧首页或独立配套资料下载区。

## 新增 HTML 自动收录

在本仓库的干净 main 工作区执行：

```bash
python3 scripts/publish_html.py /path/to/new-guide.html --title '教程标题' --category '系统运维' --description '一句话介绍' --date 2026-10-20 --tags 'Linux,SSH'
```

流程：同步远端 → 导入完成的 HTML → 自动生成首页卡片、搜索信息、文章数量、archive.json 和 sitemap.xml → 检查链接 → 提交并推送。GitHub Pages 在 main 更新后自动发布。推送后仍需确认 Pages 构建成功及公开 URL 内容。

输入必须是完整 HTML。建议制作自包含教程；本地资源需要一并放入站点对应目录并通过检查。脚本不会扫描整台电脑或后台抓取未完成草稿。

也可通过 HTML 元数据提供信息；未提供时提取已有标题、简介和主题关键词：

```html
<meta name="portal-title" content="教程标题">
<meta name="portal-category" content="AI Infra">
<meta name="portal-description" content="一句话介绍">
<meta name="portal-date" content="2026-10-20">
<meta name="portal-tags" content="训练,推理,Runtime">
```

分类 ID 为 infra、gpu、ops、general。脚本保留已归档文章的资料日期；归档不表示重新核验了文中的版本或实测结果。

## 只准备 / 重建目录 / 本地检查

```bash
python3 scripts/publish_html.py /path/to/new-guide.html --prepare-only
python3 scripts/build_catalog.py
python3 scripts/check_site.py
python3 -m unittest discover -s tests
python3 -m http.server 8000 --bind 127.0.0.1
```

打开 http://127.0.0.1:8000/ 。页面无 CDN、登录或分析追踪依赖，离线也可阅读。

## 发布配置

GitHub Pages：Deploy from a branch → main → /(root)。`.nojekyll` 直接发布静态文件，无旧 Jekyll 博客依赖。没有后台定时任务；每次制作完成的 HTML 通过发布脚本收录，再由 Pages 自动部署。

上传前检查内容是否可公开，不上传凭据、真实服务器环境报告或内部资料。失败时修复后重试；脚本不强制推送，不覆盖远端新提交，也不自动修改 GitHub 登录权限。
