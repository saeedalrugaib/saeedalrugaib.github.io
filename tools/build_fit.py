# «الطبعة المكبّرة» بنفس تقسيم صفحات الكتاب الأصلي: كل صفحة مطبوعة = صفحة واحدة بمقاس الشاشة،
# ونصها كاملاً (من ملف الورد حرفياً) بأكبر خط يتسع للصفحة، فلا تنقطع الجمل بين صفحتين أكثر مما في الأصل.
# الاستخدام: python3 tools/build_fit.py bNN
import sys, json, re, html, asyncio, os, pymupdf
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FONTS = os.environ.get("AMIRI_DIR", "/home/claude/work/fonts/Amiri-1.000")
W, H = 360, 600
MAXF, MINF = 22, 12.5
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

def page_html(book, T, head_lines, off):
    t = re.sub(r"\s*-\s*.*$", "", book["title"])
    css = f"""
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Regular.ttf);font-weight:400}}
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Bold.ttf);font-weight:700}}
@page{{size:{W}pt {H}pt;margin:0}} html{{direction:rtl}} body{{margin:0;font-family:A,serif;color:#1b1b1b}}
.pg{{position:relative;width:{W}pt;height:{H}pt;overflow:hidden;break-after:page}}
.hd{{position:absolute;top:11pt;left:20pt;right:20pt;display:flex;align-items:center;justify-content:space-between;gap:8pt;padding-bottom:4pt;border-bottom:1pt solid #b99a61}}
.hd .t{{font-size:10pt;color:#6b7c75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:64%}}
.hd .n{{font-size:11.5pt;font-weight:700;color:#fff;background:#315b4e;border-radius:20pt;padding:0 10pt 2pt}}
.ft{{position:absolute;bottom:9pt;left:0;right:0;text-align:center;font-size:11.5pt;font-weight:700;color:#315b4e}}
.ft span{{border-top:1pt solid #b99a61;padding:1pt 14pt 0}}
.bx{{position:absolute;top:40pt;bottom:30pt;left:18pt;right:18pt;display:flex;flex-direction:column}}
.c{{font-size:var(--f);line-height:1.9;text-align:justify;text-align-last:right}}
.c p,.c blockquote{{margin:0 0 .45em}} .c p{{text-indent:1.1em}} .c p.cont,.c p.li{{text-indent:0}} .c p.li{{padding-inline-start:.8em}} .c p.s{{text-align:right}}
.c blockquote{{padding:.1em .6em;border-inline-start:2.5pt solid #b99a61;background:#f6f2e8;border-radius:3pt}}
.c h2,.c h3,.c h4{{font-weight:700;color:#173d35;text-align:center;line-height:1.55;margin:.25em 0 .3em}}
.c h2{{font-size:1.15em}} .c h3{{font-size:1.08em}} .c h4{{font-size:1.03em}}
.c b{{color:#173d35}} .c sup.fn{{font-size:.58em;color:#315b4e;font-weight:700;line-height:0;vertical-align:.75em;padding:0 1pt}}
.c .orn{{text-align:center;color:#b99a61;letter-spacing:.5em}}
.fn{{margin-top:auto;padding-top:.3em}}
.fn ol{{list-style:none;margin:0;padding:.35em .6em .25em;background:#f4f7f5;border:.8pt solid #d6e2db;border-radius:5pt;font-size:calc(var(--f) * .74);line-height:1.75;color:#2b2b2b}}
.fn li{{text-align:right;padding-inline-start:1.5em;text-indent:-1.5em}} .fn b{{color:#315b4e;font-size:.85em}}
.tp{{text-align:center;justify-content:center}} .tp .t{{font-size:21pt;font-weight:700;color:#173d35;line-height:1.7}} .tp .s{{font-size:14pt;line-height:1.9}}
"""
    out = ['<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>' + css + "</style></head><body>"]
    out.append('<div class="pg"><div class="bx tp">' + "".join(f'<div class="{c}">{html.escape(x)}</div>' for c, x in head_lines) + "</div></div>")
    for pg in T["pages"]:
        body = pg["html"]
        def short(m):
            txt = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
            if len(txt) < 80:
                a = m.group(1); a = a.replace('class="', 'class="s ') if 'class="' in a else a + ' class="s"'
                return f"<p{a}>{m.group(2)}</p>"
            return m.group(0)
        body = re.sub(r"<p([^>]*)>(.*?)</p>", short, body)
        body = re.sub(r'(<sup class="fn">)\((\d+)\)', lambda m: m.group(1) + "(" + m.group(2).translate(AR) + ")", body)
        notes = "".join(f"<li><b>({str(i+1).translate(AR)})</b> {re.sub(r'^\s*\(\s*\)\s*', '', n)}</li>" for i, n in enumerate(pg["notes"]))
        n = str(pg["n"]).translate(AR)
        out.append(f'<div class="pg"><div class="hd"><span class="t">{html.escape(t)}</span><span class="n">صفحة {n}</span></div>'
                   f'<div class="bx"><div class="c">{body}</div>' + (f'<div class="fn c"><ol>{notes}</ol></div>' if notes else "") +
                   f'</div><div class="ft"><span>{n}</span></div></div>')
    out.append("""<script>
for (const bx of document.querySelectorAll('.bx:not(.tp)')) {
  let f = %s; const set = () => bx.querySelectorAll('.c').forEach(e => e.style.setProperty('--f', f + 'pt'));
  set(); while (f > %s && bx.scrollHeight > bx.clientHeight + 1) { f -= 0.25; set(); }
  bx.dataset.f = f;
}
document.body.dataset.done = 1;
</script></body></html>""" % (MAXF, MINF))
    return "".join(out)

async def render(s, pdf_out):
    from playwright.async_api import async_playwright
    tmp = "/tmp/_fit.html"; open(tmp, "w").write(s)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        await pg.goto("file://" + tmp); await pg.wait_for_selector("body[data-done]"); await pg.wait_for_timeout(300)
        sizes = await pg.evaluate("[...document.querySelectorAll('.bx:not(.tp)')].map(b => [+b.dataset.f, b.scrollHeight > b.clientHeight + 1])")
        await pg.pdf(path=pdf_out, prefer_css_page_size=True, print_background=True)
        await b.close()
    return sizes

def main(bid):
    data = json.load(open(ROOT / "books.json")); book = next(b for b in data["books"] if b["id"] == bid)
    T = json.load(open(ROOT / book.get("text", f"texts/{bid}.json")))
    head = json.load(open(ROOT / f"texts/{bid}.head.json"))
    off = int(book.get("pageOffset", 0))
    sizes = asyncio.run(render(page_html(book, T, head, off), "/tmp/_fit_body.pdf"))
    d = pymupdf.open("/tmp/_fit_body.pdf"); orig = pymupdf.open(ROOT / book["file"])
    out = pymupdf.open(); out.insert_pdf(orig, from_page=0, to_page=0); out.insert_pdf(d)
    fn = re.sub(r"\.pdf$", "-large.pdf", book["file"]); out.save(ROOT / fn, garbage=3, deflate=True)
    assert out.page_count == orig.page_count, (out.page_count, orig.page_count)
    pmap = [0, 0] + [pg["n"] for pg in T["pages"]]
    old = book.get("large", {})
    book["large"] = {"file": fn, "map": pmap, "starts": {str(pg["n"]): i + 3 for i, pg in enumerate(T["pages"])}, "chapters": old.get("chapters_fit", []), "v": int(old.get("v", 0)) + 1, "layout": "pages"}
    # العناوين: صفحة كل عنوان = صفحة الأصل نفسها
    ch = []
    for i, pg in enumerate(T["pages"]):
        for m in re.finditer(r"<h[234][^>]*>(.*?)</h[234]>", pg["html"]):
            ch.append({"t": html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(), "p": i + 3})
    book["large"]["chapters"] = ch
    json.dump(data, open(ROOT / "books.json", "w"), ensure_ascii=False, indent=1)
    fs = [s[0] for s in sizes]
    print(fn, out.page_count, "font min/median/max", min(fs), sorted(fs)[len(fs)//2], max(fs), "overflow", [i + 3 for i, s in enumerate(sizes) if s[1]])

if __name__ == "__main__":
    main(sys.argv[1])
