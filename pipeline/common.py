"""Shared paths / helpers for the 脆脆的AI早咖啡 pipeline."""
import json, datetime, subprocess, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEKDAYS_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

CATEGORIES = {
    "tech":     {"zh": "技术", "en": "TECH",   "color": "#4C7DFF"},  # LLM / models / core AI
    "app":      {"zh": "应用", "en": "APP",    "color": "#2EC4B6"},  # everyday-life / fun / viral consumer AI
    "hardtech": {"zh": "硬科技", "en": "HARD", "color": "#9B6BFF"},  # robotics, autonomy, chips hw
    "science":  {"zh": "科学", "en": "SCI",    "color": "#5AD67D"},  # AI+science / math / bio
    "capital":  {"zh": "资本", "en": "CAP",    "color": "#F2B233"},  # funding, markets, IPOs
    "biz":      {"zh": "商业", "en": "BIZ",    "color": "#E8A017"},  # business strategy (non-deal)
    "gossip":   {"zh": "八卦·人物", "en": "PEOPLE", "color": "#FF4D8D"},
}
CATEGORY_ORDER = ["tech", "app", "hardtech", "science", "capital", "biz", "gossip"]


# 视频号助手 short-title: keep 《》 quotes : + ? % ℃ ; turn ，、;!。 etc. into spaces
_SHORT_TITLE_KEEP = set("《》「」『』""''＂＇:：+？?%℃°")


def sanitize_short_title(title: str, max_len: int = 16) -> str:
    """Replace disallowed punctuation with a single space, collapse spaces, cap ≤16 chars."""
    chars = []
    for c in title or "":
        if c.isspace():
            chars.append(" ")
        elif c.isalnum() or "一" <= c <= "鿿" or c in _SHORT_TITLE_KEEP:
            chars.append(c)
        elif "㐀" <= c <= "䶿" or "豈" <= c <= "﫿":
            chars.append(c)
        else:
            chars.append(" ")
    return re.sub(r" +", " ", "".join(chars)).strip()[:max_len].rstrip()



VARIANT = None   # e.g. "v2" -> output/DATE/v2/ (set by run.py --variant)


def set_variant(v):
    global VARIANT
    VARIANT = v or None


def out_dir(date: str) -> Path:
    return OUTPUT / date / VARIANT if VARIANT else OUTPUT / date


def channel() -> dict:
    return json.loads((ASSETS / "channel.json").read_text("utf-8"))


def issue_no(b: dict) -> int:
    """Episode number: brief.issue_no if set, else days since channel launch_date + 1."""
    if b.get("issue_no"):
        return int(b["issue_no"])
    launch = datetime.date.fromisoformat(channel()["launch_date"])
    return (b["_date"] - launch).days + 1 if "_date" in b else 1


def video_name(date: str) -> str:
    return f"{channel()['file_prefix']}-{date}.mp4"


def load_brief(date: str) -> dict:
    p = out_dir(date) / "brief.json"
    if not p.exists():
        raise SystemExit(f"[x] {p} not found. Write brief.json first (see README step 2).")
    b = json.loads(p.read_text(encoding="utf-8"))
    d = datetime.date.fromisoformat(b["issue_date"])
    b["_date"] = d
    b["_weekday"] = WEEKDAYS[d.weekday()]
    b["_weekday_en"] = WEEKDAYS_EN[d.weekday()]
    b["_date_dot"] = d.strftime("%Y.%m.%d")
    b["_md"] = d.strftime("%m.%d")
    b["_items_by_id"] = {it["id"]: it for it in b["items"]}
    b["_issue_no"] = issue_no(b)
    return b


def validate_brief(b: dict) -> list:
    """Return a list of human-readable problems (empty = OK)."""
    errs = []
    for k in ["issue_date", "headline", "lede", "items", "video"]:
        if k not in b:
            errs.append(f"missing top-level key: {k}")
    ids = set()
    for i, it in enumerate(b.get("items", [])):
        for k in ["id", "category", "title", "summary", "why", "sources"]:
            if not it.get(k):
                errs.append(f"item[{i}] missing {k}")
        if it.get("category") not in CATEGORIES:
            errs.append(f"item[{i}] bad category {it.get('category')}")
        if not any(s.get("url", "").startswith("http") for s in it.get("sources", [])):
            errs.append(f"item[{i}] has no source URL")
        ids.add(it.get("id"))
    for j, s in enumerate(b.get("video", {}).get("scenes", [])):
        if s["type"] == "story" and s.get("item") not in ids:
            errs.append(f"video scene[{j}] references unknown item {s.get('item')}")
        if not s.get("narration"):
            errs.append(f"video scene[{j}] has no narration")
    if "TODO" in json.dumps({k: v for k, v in b.items() if not k.startswith("_")}, ensure_ascii=False, default=str):
        errs.append("brief.json still contains TODO placeholders")
    n_story = sum(1 for s in b.get("video", {}).get("scenes", []) if s["type"] == "story")
    if not 4 <= n_story <= 6:
        errs.append(f"video should cover 4–6 stories (has {n_story})")
    chars = sum(len(s.get("narration", "")) for s in b.get("video", {}).get("scenes", []))
    if not 250 <= chars <= 430:
        errs.append(f"narration total {chars} chars — aim for ~330–410 incl. punctuation (≈75–90 s at +10–12%)")
    for j, s in enumerate(b.get("video", {}).get("scenes", [])):
        if s.get("take_from") and s["take_from"] not in s.get("narration", ""):
            errs.append(f"video scene[{j}] take_from '{s['take_from']}' not found in narration")
        if s.get("take") and len(s["take"]) > 20:
            errs.append(f"video scene[{j}] on-screen take too long ({len(s['take'])} > 20 chars)")
    for j, s in enumerate(b.get("video", {}).get("scenes", [])):
        if "公众号" in s.get("narration", ""):
            errs.append(f"video scene[{j}] narration mentions 公众号 (dropped for now)")
    # schema (field types / lengths) — schema/brief.schema.json
    try:
        import jsonschema
        sch = json.loads((ROOT / "schema" / "brief.schema.json").read_text("utf-8"))
        for e in jsonschema.Draft202012Validator(sch).iter_errors({k: v for k, v in b.items() if not k.startswith("_")}):
            errs.append(f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}")
    except ImportError:
        pass
    # 脆脆 persona: fixed catchphrases (assets/channel.json) + banned clichés (assets/persona.md)
    ch = channel(); cp = ch.get("catchphrases", {})
    scenes = b.get("video", {}).get("scenes", [])
    stories = [s for s in scenes if s.get("type") == "story"]
    if cp and scenes:
        if scenes[0].get("type") != "title" or not scenes[0]["narration"].startswith(cp["opening"]):
            errs.append(f"title narration must start with the fixed opening: {cp['opening']}")
        if scenes[-1].get("type") != "outro" or scenes[-1]["narration"] != cp["signoff"]:
            errs.append(f"outro narration must be exactly: {cp['signoff']}")
        for k, s in enumerate(stories):
            n = s.get("narration", "")
            if s.get("segment") == "zha":
                if k != len(stories) - 1: errs.append("the gossip (segment zha) story must be the last story")
                if not n.startswith(cp["zha"]): errs.append(f"zha story must start with {cp['zha']}")
            elif k > 0 and not n.startswith(cp["transition"]):
                errs.append(f"story {k + 1} must start with {cp['transition']}")
            if cp["take"] not in n: errs.append(f"story {k + 1} narration needs a 「{cp['take']}…」 line")
            if not s.get("take"): errs.append(f"story {k + 1} needs an on-screen take (≤20 chars)")
    for s in scenes:
        for w in ch.get("banned_phrases", []):
            if w.lower() in s.get("narration", "").lower(): errs.append(f"banned phrase 「{w}」 in narration (see assets/persona.md)")
    for k, s in enumerate(scenes):
        m = s.get("media")
        if m and not all(m.get(f) for f in ("url", "page", "credit")):
            errs.append(f"scene {k} media needs url + page (source) + credit")
    sph = b.get("sph")
    if sph is not None:
        tags = sph.get("hashtags", [])
        if not 3 <= len(tags) <= 6: errs.append(f"sph.hashtags should have 3–6 tags (has {len(tags)})")
        if not sph.get("title"): errs.append("sph.title missing")
        else:
            raw = sph["title"]
            clean = sanitize_short_title(raw)
            if not clean:
                errs.append("sph.title empty after 视频号助手 sanitization")
            elif raw.strip() != clean:
                errs.append(f"sph.title has punctuation 视频号助手 rejects — write it as: {clean!r} (commas→spaces; only 《》引号:：+？?%℃ allowed)")
            elif not 1 <= len(clean) <= 16:
                errs.append(f"sph.title length {len(clean)} — want ≤16 after sanitize")
        if not 1 <= len(sph.get("description", [])) <= 3: errs.append("sph.description should be 1–3 lines")
    return errs


def ffprobe_duration(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())
