"""Step: article (Markdown + WeChat-safe HTML) and the review preview page."""
import json, re, html as _html
from jinja2 import Environment, FileSystemLoader
from .common import TEMPLATES, CATEGORIES, CATEGORY_ORDER, out_dir, load_brief, video_name

env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=False, lstrip_blocks=False)


def run(date):
    b = load_brief(date); od = out_dir(date)
    ctx = {"b": b, "cats": CATEGORY_ORDER, "C": CATEGORIES}
    md = env.get_template("article.md.j2").render(**ctx)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    (od / "article.md").write_text(md, "utf-8")
    # escape text fields for HTML
    eb = json.loads(json.dumps({k: v for k, v in b.items() if not k.startswith("_")}, ensure_ascii=False))
    def esc(o):
        if isinstance(o, str): return _html.escape(o, quote=False)
        if isinstance(o, list): return [esc(x) for x in o]
        if isinstance(o, dict): return {k: (v if k == "url" else esc(v)) for k, v in o.items()}
        return o
    eb = esc(eb); eb.update({k: v for k, v in b.items() if k.startswith("_")})
    h = env.get_template("article_wechat.html.j2").render(b=eb, cats=CATEGORY_ORDER, C=CATEGORIES)
    h = re.sub(r"\n\s*\n", "\n", h).strip()
    assert "<style" not in h and "<script" not in h, "WeChat HTML must stay inline-only"
    (od / "article.html").write_text(h + "\n", "utf-8")
    print(f"  -> {od/'article.md'}\n  -> {od/'article.html'}  ({len(h)//1024} KB, {len(b['items'])} items)")


def preview(date):
    b = load_brief(date); od = out_dir(date)
    body = (od / "article.html").read_text("utf-8") if (od / "article.html").exists() else ""
    page = env.get_template("preview.html.j2").render(b=b, article=body, date=date,
                                                      video=video_name(date), srt=video_name(date).replace(".mp4", ".srt"))
    (od / "preview.html").write_text(page, "utf-8")
    print(f"  -> {od/'preview.html'}")
