# 技术学习手册

一个无构建依赖的中文静态知识门户，归档 AI Infra、GPU 架构与算子优化、Linux 运维学习材料。

## 内容

- `index.html`：门户、搜索与分类。
- `ai-infra-mindmap.html`：AI Infra 全景脑图。
- `mi355x-operator-ecosystem-guide.html`：MI355X 算子生态、版本匹配与安装。
- `mi355x-gemm-sweep-lab.html`：FP8 A8W8 blockscale GEMM 的分块、调度与 sweep。
- `nvidia-h20-b200-architecture-lab.html`：H20/B200 架构、数据流与 GEMM sweep。
- `sshd-ssh-mutual-trust-guide.html`：sshd 部署、SSH 公钥认证、互信与排障。
- `mi355x-operator-ecosystem-guide.md`、`mi355x-env-check.py`、`nvidia-device-probe.cu`：参考文档与只读设备查询代码。

## GitHub Pages

仓库：`User-Balance/User-Balance.github.io`。个人网站地址：`https://user-balance.github.io/`。

在仓库 **Settings → Pages → Build and deployment** 中选择 **Deploy from a branch**，分支 `main`，目录 `/(root)`。已有 `_config.yml`、`_layouts`、`_posts`、`blog` 和 `css` 继续使用 Jekyll 发布，保留原博客 URL。新门户和五篇教程是没有 front matter 的静态 HTML，原样复制到发布目录。

原首页另存为 `legacy-home.html`，门户提供“原有博客”和“原首页”入口。**不要添加 `.nojekyll`**，否则既有博客模板与文章不会被渲染。仓库更新后 Pages 会重新发布，可以在 Actions / Pages 部署记录查看状态；应检查公开 URL 确认上线。

## 本地预览与校验

```bash
python3 scripts/check_site.py
python3 -m http.server 8000 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8000/`。也可以直接打开 `index.html`；新门户和教程没有 CDN、登录或分析追踪依赖。上述简单 HTTP 服务不会编译旧 Jekyll 博客，旧博客的最终效果以 GitHub Pages/Jekyll 构建为准。

## 更新

编辑对应 HTML，再检查内部链接、交互、命令与资料日期。新增教程时同步首页卡片和 `archive.json`。发布内容只应包含可公开的学习材料，不要放入密钥、真实环境输出或内部服务器信息。

文中版本/产品规格均有适用日期或来源边界。未实机测试的安装或 GPU 命令保留明确说明；结构估算不等于性能测量。
