# posts/ — 博客文章源文件目录

把你写好的 Markdown 放在这个目录里，一条命令即可发布成博客文章并同步到 GitHub Pages。

## 一键发布

```bash
# 发布单篇（发布 posts/ 下最新的一篇，会自动排序）
python3 tools/blog_publish.py

# 指定文件
python3 tools/blog_publish.py posts/我的文章.md

# 发布 posts/ 下所有未发布或已修改的 md
python3 tools/blog_publish.py --all

# 先预览（只渲染，不改仓库、不推送）
python3 tools/blog_publish.py posts/我的文章.md --dry-run

# 查看发布状态
python3 tools/blog_publish.py --list
```

## 脚本会做什么

1. 读取 md，解析 frontmatter（可选）
2. 渲染成博客样式 HTML → `article-<slug>.html`
3. 在 `index.html` 首页文章列表插入/更新卡片（按链接去重，不会重复）
4. `git commit` 并推送到 `origin`（felix-blog）和 `pages`（drrreistein.github.io）
5. 等待 GitHub Pages 构建并检查线上是否 200

发布后地址：`https://drrreistein.github.io/article-<slug>.html`

## md 写法

frontmatter 全部可选，不写就用正文第一个 `# 一级标题` 当标题、文件修改时间当日期。

```markdown
---
title: 文章标题
date: 2026-11-05
summary: 首页卡片上显示的一句话摘要
slug: my-post-name
---

正文……
```

支持的 Markdown：标题、粗斜体、列表、引用、代码块、表格、图片、分割线。

## 提示

- 文件名建议用中文，`slug` 建议用英文（决定 URL）
- 重复发布同一篇会覆盖旧页面并替换首页卡片，不会产生重复条目
- 发布后 md 原样保留，作为归档
