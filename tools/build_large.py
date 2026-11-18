# «الطبعة المكبّرة»: يبني من النسخة النصية (texts/bNN.json المأخوذة حرفياً من ملف الورد) ملف PDF بصفحات بمقاس الشاشة وخط كبير،
# يُقلَّب في القارئ مثل الكتاب، ويضع علامة «صفحة n» عند بداية كل صفحة من الكتاب المطبوع، ويحفظ خريطة الأرقام لتطابق الفهرس.
# الاستخدام: python3 tools/build_large.py bNN  (يحتاج playwright و pymupdf)
import sys, json, re, html, asyncio, os, pymupdf
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FONTS = os.environ.get("AMIRI_DIR", "/home/claude/work/fonts/Amiri-1.000")
W, H = 360, 600          # نقاط — نسبة شاشة الجوال تقريباً
FS = 20                  # حجم خط المتن
MT, MB, MS = 50, 40, 26  # هوامش: أعلى (للرأس) وأسفل (للتذييل) وجانبية
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

def build_html(book, T, head_lines):
    css = f"""
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Regular.ttf);font-weight:400}}
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Bold.ttf);font-weight:700}}
@page{{size:{W}pt {H}pt;margin:{MT}pt {MS}pt {MB}pt}}
html{{direction:rtl}} body{{margin:0;font-family:A,serif;font-size:{FS}pt;line-height:2.05;color:#1b1b1b;text-align:justify;text-align-last:right;word-spacing:.02em}}
p,blockquote{{margin:0 0 .6em;orphans:2;widows:2}} p.s{{text-align:right}} .tp *{{text-align:center;text-align-last:center}} p{{text-indent:1.2em}} p.cont,p.li{{text-indent:0}} p.li{{padding-inline-start:.8em}}
blockquote{{padding:.15em .7em;border-inline-start:3pt solid #b99a61;background:#f6f2e8;border-radius:4pt}}
h2,h3,h4{{font-weight:700;color:#173d35;text-align:center;line-height:1.6;margin:.55em 0 .35em;break-after:avoid;break-inside:avoid}}
h2{{font-size:1.16em}} h3{{font-size:1.1em}} h4{{font-size:1.04em}}
b{{color:#173d35}} sup.fn{{font-size:.58em;color:#315b4e;font-weight:700;line-height:0;vertical-align:.75em;padding:0 1pt}}
.orn{{text-align:center;color:#b99a61;letter-spacing:.5em}}
.mk{{display:flex;align-items:center;gap:8pt;margin:.7em 0 .55em;color:#fff;font-size:12.5pt;font-weight:700;break-after:avoid;break-inside:avoid}}
.mk::before,.mk::after{{content:"";flex:1;height:1.2pt;background:#b99a61}}
.mk span{{background:#315b4e;border-radius:20pt;padding:1pt 12pt 3pt}}
.fn-l{{list-style:none;margin:.3em 0 .7em;padding:.45em .7em .35em;background:#f4f7f5;border:.8pt solid #d6e2db;border-radius:6pt;font-size:15pt;line-height:1.85;color:#2b2b2b}} .fn-l::before{{content:"الحواشي";display:block;font-size:11pt;font-weight:700;color:#315b4e;margin-bottom:.1em}}
.fn-l li{{margin:0 0 .2em;text-align:right;padding-inline-start:1.6em;text-indent:-1.6em}} .fn-l b{{color:#315b4e;font-size:.8em}}
.q{{position:absolute;left:0;top:0;font-size:2pt;line-height:1;color:#fefefe;white-space:nowrap;font-style:normal}} .mk,h2,h3,h4,.tp{{position:relative}}
.tp{{height:{H-MT-MB-4}pt;display:flex;flex-direction:column;justify-content:center;text-align:center;break-after:page}}
.tp .t{{font-size:1.35em;font-weight:700;color:#173d35;line-height:1.7}} .tp .s{{font-size:.85em;line-height:1.8}}
"""
    out = ['<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>' + css + '</style></head><body>']
    out.append('<div class="tp">' + "".join(f'<div class="{c}">{html.escape(x)}</div>' for c, x in head_lines) + '</div>')
    hk = 0; heads = []
    for pg in T["pages"]:
        out.append(f'<div class="mk"><i class="q">QQP{pg["n"]}QQ</i><span>صفحة {str(pg["n"]).translate(AR)}</span></div>')
        body = pg["html"]
        def hmark(m):
            nonlocal hk
            hk += 1; heads.append((hk, html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip(), pg["n"]))
            o = m.group(0); i = o.index('>') + 1
            return o[:i] + f'<i class="q">QQH{hk}QQ</i>' + o[i:]
        body = re.sub(r"<(h[234])[^>]*>(.*?)</\1>", hmark, body)
        # الفقرات القصيرة (سطر أو سطران) بمحاذاة يمين بدل الضبط، حتى لا تتسع المسافات بين الكلمات
        def short(m):
            txt = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
            if len(txt) < 95:
                attrs = m.group(1)
                if 'class="' in attrs: attrs = attrs.replace('class="', 'class="s ')
                else: attrs += ' class="s"'
                return f"<p{attrs}>{m.group(2)}</p>"
            return m.group(0)
        body = re.sub(r"<p([^>]*)>(.*?)</p>", short, body)
        out.append(body)
        if pg["notes"]:
            out.append('<ol class="fn-l">' + "".join(f"<li><b>({str(i+1).translate(AR)})</b> {re.sub(r'^\s*\(\s*\)\s*', '', n)}</li>" for i, n in enumerate(pg["notes"])) + "</ol>")
    out.append("</body></html>")
    s = "".join(out)
    s = re.sub(r'(<sup class="fn">)\((\d+)\)', lambda m: m.group(1) + "(" + m.group(2).translate(AR) + ")", s)
    return s, heads

async def render(html_s, pdf_out):
    from playwright.async_api import async_playwright
    tmp = "/tmp/_large.html"; open(tmp, "w").write(html_s)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        await pg.goto("file://" + tmp); await pg.wait_for_timeout(600)
        await pg.pdf(path=pdf_out, prefer_css_page_size=True, print_background=True)
        await b.close()

def main(bid, head_lines):
    data = json.load(open(ROOT / "books.json")); book = next(b for b in data["books"] if b["id"] == bid)
    T = json.load(open(ROOT / book.get("text", f"texts/{bid}.json")))
    s, heads = build_html(book, T, head_lines)
    body_pdf = "/tmp/_large_body.pdf"; asyncio.run(render(s, body_pdf))
    d = pymupdf.open(body_pdf)
    # خريطة: لكل صفحة في الملف الجديد رقم الصفحة المطبوعة الظاهرة في أعلاها
    first = {}; hpage = {}; cur = 0; labels = []
    for i, p in enumerate(d):
        t = p.get_text()
        ms = [int(x) for x in re.findall(r"QQP(\d+)QQ", t)]
        for k in re.findall(r"QQH(\d+)QQ", t): hpage[int(k)] = i
        top = None
        for b in sorted(p.get_text("blocks"), key=lambda b: b[1]):
            if b[6] == 0 and b[4].strip() and "QQ" not in b[4]: top = b; break
        # إن بدأت صفحة مطبوعة في أعلى الصفحة فهي رقمها، وإلا تبقى على السابقة
        for n in ms: first.setdefault(n, i)
        if ms and (cur == 0 or (top is not None and any(first[n] == i for n in ms) and min(ms) and _starts_top(p, min(ms)))): cur = min(ms)
        elif ms and cur == 0: cur = min(ms)
        labels.append(cur)
        # بعد هذه الصفحة: الرقم الجاري هو آخر علامة فيها
        if ms: cur = max(ms)
    # نطاق كل صفحة: رقم أعلاها، وآخر صفحة مطبوعة تبدأ فيها
    rng = []; cur2 = 0
    for i, p in enumerate(d):
        ms = [int(x) for x in re.findall(r"QQP(\d+)QQ", p.get_text())]
        a = labels[i]; z = max(ms) if ms else a
        rng.append((a, z))
    hp = "/tmp/_large_hdr.pdf"; asyncio.run(render(header_html(book, rng), hp))
    hd = pymupdf.open(hp)
    for i, p in enumerate(d): p.show_pdf_page(p.rect, hd, i, overlay=True)
    # الغلاف الأصلي أولاً
    orig = pymupdf.open(ROOT / book["file"]); out = pymupdf.open()
    out.insert_pdf(orig, from_page=0, to_page=0); out.insert_pdf(d)
    fn = re.sub(r"\.pdf$", "-large.pdf", book["file"])
    out.save(ROOT / fn, garbage=3, deflate=True)
    pmap = [0] + labels                       # الغلاف
    chapters = [{"t": t, "p": hpage[k] + 2} for k, t, n in heads if k in hpage]
    starts = {str(n): i + 2 for n, i in first.items()}
    book["large"] = {"file": fn, "map": pmap, "starts": starts, "chapters": chapters, "v": int(book.get("large", {}).get("v", 0)) + 1}
    json.dump(data, open(ROOT / "books.json", "w"), ensure_ascii=False, indent=1)
    print(fn, "pages", out.page_count, "printed", max(pmap), "first", sorted(first.items())[:5])

def header_html(book, rng):
    t = re.sub(r"\s*-\s*.*$", "", book["title"])
    css = f"""
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Regular.ttf);font-weight:400}}
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Bold.ttf);font-weight:700}}
@page{{size:{W}pt {H}pt;margin:0}} html{{direction:rtl}} body{{margin:0;font-family:A,serif}}
.pg{{position:relative;width:{W}pt;height:{H}pt;break-after:page;overflow:hidden}}
.hd{{position:absolute;top:12pt;left:{MS}pt;right:{MS}pt;display:flex;align-items:center;justify-content:space-between;gap:8pt;padding-bottom:5pt;border-bottom:1pt solid #b99a61}}
.hd .t{{font-size:10.5pt;color:#6b7c75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:62%}}
.hd .n{{font-size:11.5pt;font-weight:700;color:#fff;background:#315b4e;border-radius:20pt;padding:0 10pt 2pt;white-space:nowrap}}
.ft{{position:absolute;bottom:12pt;left:0;right:0;text-align:center;font-size:12pt;font-weight:700;color:#315b4e}}
.ft span{{display:inline-block;border-top:1pt solid #b99a61;padding:2pt 14pt 0}}
"""
    out = ['<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>' + css + '</style></head><body>']
    for a, z in rng:
        if a <= 0 and z <= 0: out.append('<div class="pg"></div>'); continue
        a = a or z
        lab = f"صفحة {str(a).translate(AR)}" if a == z else f"صفحة {str(a).translate(AR)} – {str(z).translate(AR)}"
        out.append(f'<div class="pg"><div class="hd"><span class="t">{html.escape(t)}</span><span class="n">{lab}</span></div><div class="ft"><span>{str(a).translate(AR)}</span></div></div>')
    out.append("</body></html>"); return "".join(out)

def _starts_top(p, n):
    for b in sorted(p.get_text("blocks"), key=lambda b: b[1]):
        if b[6] != 0 or not b[4].strip(): continue
        return f"QQP{n}QQ" in b[4] or b[1] < 40
    return False

if __name__ == "__main__":
    main(sys.argv[1], json.loads(sys.argv[2]))
