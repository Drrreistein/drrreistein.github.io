#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blog_publish.py — 把 posts/ 下的 Markdown 一键发布成博客文章（HTML + 首页列表 + GitHub Pages）

工作流：
    md（posts/xxx.md） -> 博客样式 HTML（article-xxx.html） -> 插入 index.html 文章列表
      -> git commit -> push 到 origin(felix-blog) 与 pages(drrreistein.github.io)
      -> 等 Pages 构建 -> 检查线上 200

常用命令：
    python3 tools/blog_publish.py --list                  # 看 posts/ 里有哪些 md、哪些已发布
    python3 tools/blog_publish.py posts/我的文章.md       # 发布单篇
    python3 tools/blog_publish.py --all                   # 发布 posts/ 下所有未发布的 md
    python3 tools/blog_publish.py posts/我的文章.md --dry-run   # 只渲染看效果，不提交
    python3 tools/blog_publish.py posts/我的文章.md --slug my-post   # 指定 URL 文件名

md 文件格式（frontmatter 可选，不写就用一级标题当标题、今天当日期）：
    ---
    title: 文章标题
    date: 2026-11-05
    summary: 首页卡片上显示的一句话摘要
    slug: my-post-name
    ---
    # 文章标题
    正文...

约定：
    - md 源文件放 posts/，发布后原样保留（作为归档）
    - html 生成在仓库根目录，命名 article-<slug>.html，与现有文章一致
    - 重复发布同一篇会覆盖旧 html 并替换首页卡片，不会产生重复条目
"""
import argparse
import html as html_lib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOG = Path("/Users/a1-6/WorkBuddy/20260313105301")
POSTS = BLOG / "posts"
INDEX = BLOG / "index.html"
VENV_PY = Path.home() / ".workbuddy/binaries/python/envs/default/bin/python"

REMOTES = ["origin", "pages"]          # origin = felix-blog 备份；pages = drrreistein.github.io 线上
PAGES_REPO = "Drrreistein/drrreistein.github.io"

# ---------------------------------------------------------------- 模板

HEAD_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 磊 的思考与写作</title>
    <meta name="description" content="{summary}">
    <link rel="stylesheet" href="styles.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Georgia:wght@400;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="top-decoration">
        <svg viewBox="0 0 2880 100" preserveAspectRatio="xMidYMid slice">
            <defs>
                <path id="wave1" d="M0,40 C150,80 350,0 500,40 C650,80 850,0 1000,40 C1150,80 1350,0 1500,40 C1650,80 1850,0 2000,40 C2150,80 2350,0 2500,40 C2650,80 2850,0 3000,40 L3000,0 L0,0 Z"/>
                <path id="wave2" d="M0,60 C180,20 320,80 480,60 C640,40 820,90 980,60 C1140,30 1300,80 1460,60 C1620,40 1780,90 1940,60 C2100,30 2260,80 2420,60 C2580,40 2740,90 2900,60 L2900,0 L0,0 Z"/>
                <path id="wave3" d="M0,80 C160,50 280,90 440,80 C600,70 760,95 920,80 C1080,65 1240,85 1400,80 C1560,70 1720,95 1880,80 C2040,65 2200,85 2360,80 C2520,70 2680,95 2840,80 L2840,0 L0,0 Z"/>
            </defs>
            <g class="wave-path-1"><use href="#wave1" fill="#991b1b" fill-opacity="0.8"/></g>
            <g class="wave-path-2"><use href="#wave2" fill="#991b1b" fill-opacity="0.6"/></g>
            <g class="wave-path-3"><use href="#wave3" fill="#b91c1c" fill-opacity="0.4"/></g>
        </svg>
    </div>

    <header class="header">
        <div class="header-content">
            <div class="blog-identity">
                <div class="avatar-container">
                    <video autoplay muted loop playsinline class="avatar avatar-video">
                        <source src="Bark.mp4" type="video/mp4">
                    </video>
                </div>
                <h1 class="blog-title">磊 的思考与写作</h1>
            </div>
            <nav class="navigation">
                <a href="index.html#blog">blog</a>
                <a href="reading-notes.html">reading notes</a>
                <a href="podcast-notes.html">podcast notes</a>
                <a href="projects.html">projects</a>
                <a href="about.html">about</a>
            </nav>
            <button class="lang-switch" id="langSwitch">中文</button>
        </div>
    </header>

    <main class="main-content">
        <article class="article">
            <h1 class="article-title article-title-full">{title}</h1>
            <p class="article-date">
                <span class="date-text">写于 {date_zh}</span>
            </p>
            <div class="article-body">
{body}
            </div>
        </article>
    </main>

    <footer class="footer">
        <div class="footer-content">
            <p class="copyright">© 2026 磊。保留所有权利。</p>
        </div>
    </footer>

    <script src="script.js"></script>
</body>
</html>
"""

RENDER_CODE = r'''
import sys, re, markdown
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
# frontmatter 已在外部剥离；把独立的 --- 行转成 <hr>，避免出现 <p>---</p>
text = re.sub(r"(?m)^\s*---\s*$", "\n<hr>\n", text)
body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
                         output_format="html5")
open(dst, "w", encoding="utf-8").write(body)
'''

# ---------------------------------------------------------------- 工具函数

def run(cmd, cwd=None, check=False):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def log(step, msg):
    print(f"[{step}] {msg}", flush=True)


def find_python():
    for py in [str(VENV_PY), sys.executable]:
        if py and Path(py).exists() and run([py, "-c", "import markdown"]).returncode == 0:
            return py
    sys.exit("没找到带 markdown 库的 Python，请先 pip install markdown")


def split_frontmatter(text):
    """返回 (meta_dict, body_text)。"""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm, body = parts[1], parts[2]
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip().strip('"\'')
    return meta, body.lstrip("\n")


def slugify(name):
    s = Path(name).stem.strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    return s


def plain_text(md_body, limit=110):
    """从 md 正文提取纯文本摘要。"""
    t = re.sub(r"```.*?```", " ", md_body, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[#>*`_\-]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:limit] + "…") if len(t) > limit else t


def render(md_path, body_path):
    py = find_python()
    p = run([py, "-c", RENDER_CODE, str(md_path), str(body_path)])
    if p.returncode != 0:
        sys.exit(f"渲染失败：{p.stderr.strip()}")
    return body_path.read_text(encoding="utf-8")


def build_page(title, date_zh, summary, body_html):
    return HEAD_TPL.format(
        title=html_lib.escape(title),
        summary=html_lib.escape(summary[:150]),
        date_zh=date_zh,
        body=body_html.rstrip(),
    )


CARD_TPL = """            <li class="article-list-item">
                <span class="article-list-date">{date_en}</span>
                <div class="article-list-content">
                    <h2 class="article-list-title">
                        <a href="{href}">{title}</a>
                    </h2>
                    <p class="article-list-subtitle">{summary}</p>
                </div>
            </li>
"""


def upsert_card(index_html, href, card):
    """在 index.html 的 article-list 里插入或替换卡片（按 href 去重）。"""
    if href in index_html:
        # 已存在：整段替换（从包含该 href 的 <li> 到对应 </li>）
        pattern = re.compile(
            r'[ \t]*<li class="article-list-item">(?:(?!</li>).)*?' + re.escape(href) +
            r'(?:(?!</li>).)*?</li>\n', re.S)
        new_html, n = pattern.subn(card, index_html, count=1)
        if n:
            return new_html, "updated"
        return index_html, "exists"

    marker = "<!-- 所有博客文章 -->"
    anchor = index_html.find(marker)
    if anchor == -1:
        anchor = index_html.find('<ul class="article-list">')
        if anchor == -1:
            sys.exit("index.html 里找不到文章列表容器（ul.article-list）")
        anchor += len('<ul class="article-list">')
        return index_html[:anchor] + "\n" + card + index_html[anchor:], "inserted"
    anchor += len(marker)
    # 跳过紧随其后的空白
    rest = index_html[anchor:]
    stripped = rest.lstrip("\n")
    pad = rest[:len(rest) - len(stripped)]
    return index_html[:anchor] + pad + card + stripped, "inserted"


def git_publish(files, msg):
    run(["git", "add", "--"] + [str(f) for f in files], cwd=BLOG)
    st = run(["git", "status", "--porcelain", "--"] + [str(f) for f in files], cwd=BLOG)
    if not st.stdout.strip():
        log("git", "无变更，跳过提交")
        return None
    c = run(["git", "commit", "-q", "-m", msg], cwd=BLOG)
    if c.returncode != 0:
        sys.exit(f"提交失败：{c.stderr.strip()}")
    head = run(["git", "rev-parse", "HEAD"], cwd=BLOG).stdout.strip()
    log("git", f"提交 {head[:7]}：{msg}")

    for remote in REMOTES:
        if run(["git", "remote", "get-url", remote], cwd=BLOG).returncode != 0:
            log("git", f"跳过未配置的 remote：{remote}")
            continue
        p = run(["git", "push", remote, "master:master"], cwd=BLOG)
        if p.returncode != 0:
            log("git", f"推送 {remote} 失败：{(p.stderr or p.stdout).strip()[:200]}")
        else:
            log("git", f"已推送 {remote}")
    return head


def wait_pages(url, head, timeout=150):
    deadline = time.time() + timeout
    built = False
    while time.time() < deadline:
        r = run(["gh", "api", f"repos/{PAGES_REPO}/pages/builds/latest",
                 "--jq", '.status + " " + .commit'])
        parts = r.stdout.strip().split()
        if len(parts) == 2 and parts[0] == "built" and parts[1].startswith(head[:7]):
            built = True
            break
        time.sleep(6)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "blog_publish"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.getcode()
    except Exception as e:
        code = f"请求失败 {e}"
    log("pages", f"{'已构建' if built else '构建中'} | 线上 {code} | {url}")

# ---------------------------------------------------------------- 主流程

def publish_one(md_path, args):
    md_path = md_path.resolve()
    text = md_path.read_text(encoding="utf-8")
    meta, body_md = split_frontmatter(text)

    m = re.search(r"^#\s+(.+)$", body_md, re.M)
    title = meta.get("title") or (m.group(1).strip() if m else md_path.stem)
    if m:
        # 页面已有 h1，正文里的一级标题始终剥离，避免重复
        body_md = re.sub(r"^#\s+.+$", "", body_md, count=1, flags=re.M).lstrip("\n")

    date_raw = meta.get("date", "")
    dt = None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(date_raw, fmt)
            break
        except ValueError:
            continue
    dt = dt or datetime.fromtimestamp(md_path.stat().st_mtime)
    date_en = dt.strftime("%b %d, %Y").replace(" 0", " ")
    date_zh = f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"

    summary = meta.get("summary") or meta.get("description") or plain_text(body_md)
    slug = args.slug or meta.get("slug") or slugify(md_path.name)
    html_name = f"article-{slug}.html"
    html_path = BLOG / html_name

    # 渲染正文
    tmp_md = BLOG / ".tmp_render.md"
    tmp_body = BLOG / ".tmp_render.html"
    tmp_md.write_text(body_md, encoding="utf-8")
    body_html = render(tmp_md, tmp_body)
    tmp_md.unlink(missing_ok=True)
    tmp_body.unlink(missing_ok=True)

    if "<h2" not in body_html and "<p" not in body_html:
        sys.exit("渲染结果为空，请检查 md 内容")

    page = build_page(title, date_zh, summary, body_html)
    log("1/4", f"渲染 {md_path.name} -> {html_name}（{len(page) // 1024} KB）")

    card = CARD_TPL.format(date_en=date_en, href=html_name,
                           title=html_lib.escape(title), summary=html_lib.escape(summary))
    index_html = INDEX.read_text(encoding="utf-8")
    new_index, action = upsert_card(index_html, html_name, card)
    log("2/4", f"首页列表{'将更新' if action == 'updated' else '将插入'}：{title}")

    url = f"https://drrreistein.github.io/{html_name}"
    if args.dry_run:
        preview = Path("/tmp") / html_name
        preview.write_text(page, encoding="utf-8")
        print("\n[dry-run] 计划（未改动仓库内任何文件）：")
        print(f"  预览页: {preview}")
        print(f"  html  : {html_path}")
        print(f"  首页  : {INDEX}（{action}）")
        print(f"  线上  : {url}")
        print("  去掉 --dry-run 即正式发布。")
        return None

    html_path.write_text(page, encoding="utf-8")
    INDEX.write_text(new_index, encoding="utf-8")

    head = git_publish([html_path, INDEX], args.msg or f"post: {title}")
    if head and not args.no_wait:
        wait_pages(url, head)
    elif head:
        log("pages", f"跳过等待 | {url}")
    return url


def main():
    ap = argparse.ArgumentParser(description="把 posts/ 下的 md 一键发布成博客文章")
    ap.add_argument("md", nargs="?", help="md 文件路径（默认：posts/ 下最新的一篇）")
    ap.add_argument("--all", action="store_true", help="发布 posts/ 下所有 md")
    ap.add_argument("--list", action="store_true", help="列出 posts/ 里的 md 与发布状态")
    ap.add_argument("--slug", help="指定输出文件名（article-<slug>.html）")
    ap.add_argument("--msg", help="commit message")
    ap.add_argument("--dry-run", action="store_true", help="只渲染与改首页，不提交")
    ap.add_argument("--no-wait", action="store_true", help="不等待 Pages 构建")
    a = ap.parse_args()

    POSTS.mkdir(exist_ok=True)
    mds = sorted([p for p in POSTS.glob("*.md")
                  if not p.name.startswith("_") and p.name.lower() != "readme.md"],
                 key=lambda p: p.stat().st_mtime, reverse=True)

    if a.list:
        if not mds:
            print(f"posts 目录（{POSTS}）里还没有 md 文件")
            return
        print(f"md 目录：{POSTS}")
        index_html = INDEX.read_text(encoding="utf-8")
        for p in mds:
            slug = slugify(p.name)
            done = f"article-{slug}.html" in index_html
            print(f"  [{'已发布' if done else '未发布'}] {p.name}")
        return

    if a.all:
        if not mds:
            sys.exit(f"posts 目录里没有 md：{POSTS}")
        for p in mds:
            publish_one(p, a)
        return

    target = Path(a.md).resolve() if a.md else (mds[0] if mds else None)
    if not target or not target.is_file():
        sys.exit(f"找不到 md 文件。把 md 放进 {POSTS} 或用参数指定路径。")
    publish_one(target, a)


if __name__ == "__main__":
    main()
