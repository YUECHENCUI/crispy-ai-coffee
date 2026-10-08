"""Step: 公众号 cover (900x383) + 1:1 thumbnail, rendered from HTML at 2x then downsampled."""
from jinja2 import Environment, FileSystemLoader
from PIL import Image
from .common import TEMPLATES, ASSETS, out_dir, load_brief

env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)


def _shot(html_path, w, h, png):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        pg.goto(html_path.as_uri()); pg.evaluate("document.fonts.ready.then(()=>1)"); pg.wait_for_timeout(150)
        pg.screenshot(path=str(png)); br.close()


def run(date):
    b = load_brief(date); od = out_dir(date); bd = od / "cover"; bd.mkdir(parents=True, exist_ok=True)
    ctx = {"b": b, "brand_css": (TEMPLATES / "brand.css").as_uri(), "logo": (ASSETS / "logo.svg").as_uri(),
           "cover_head": b.get("cover_head", b["headline"])}
    for name, tpl, (w, h), final in [("cover", "cover.html.j2", (900, 383), (900, 383)),
                                     ("thumb", "thumb.html.j2", (540, 540), (1080, 1080))]:
        hp = bd / f"{name}.html"; hp.write_text(env.get_template(tpl).render(**ctx), "utf-8")
        big = bd / f"{name}@2x.png"; _shot(hp, w, h, big)
        im = Image.open(big).convert("RGB")
        out = od / (f"cover_900x383.png" if name == "cover" else "thumb_1x1.png")
        (im.resize(final, Image.LANCZOS) if im.size != final else im).save(out, optimize=True)
        print(f"  -> {out}  {final[0]}x{final[1]}")
