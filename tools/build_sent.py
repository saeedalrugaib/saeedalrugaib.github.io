# «الطبعة المكبّرة» (طريقة: لا تُقطع الجملة): خط كبير ثابت، كل صفحة من الكتاب الأصلي تبدأ في شاشة جديدة،
# والشاشة لا تنتهي إلا بنهاية جملة. النص من ملف الورد حرفياً (texts/bNN.json)، والحواشي أسفل الشاشة التي فيها رقمها.
# الاستخدام: python3 tools/build_sent.py bNN
import sys, json, re, html, asyncio, os, pymupdf
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
FONTS = os.environ.get("AMIRI_DIR", "/home/claude/work/fonts/Amiri-1.000")
W, H, FS = 360, 600, 19.5
AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
END = set(".؟!:؛")

def split_sentences(inner):
    """يقسم محتوى الفقرة إلى جمل عند علامات نهاية الجملة خارج الوسوم، ويُلحق أرقام الحواشي والأقواس اللاحقة بالجملة."""
    out = []; buf = ""; depth = 0; i = 0; n = len(inner)
    while i < n:
        c = inner[i]
        if c == "<":
            j = inner.index(">", i); tag = inner[i:j + 1]; buf += tag
            if tag.startswith("</"): depth -= 1
            elif not tag.endswith("/>"): depth += 1
            i = j + 1; continue
        buf += c; i += 1
        if depth == 0 and c in END:
            # ما يلتصق بنهاية الجملة: أقواس/علامات تنصيص/رقم حاشية
            while i < n:
                m = re.match(r'(\s*<sup class="fn">.*?</sup>|[)"”»\]﴾﴿]+)', inner[i:])
                if not m: break
                buf += m.group(0); i += len(m.group(0))
            if i >= n or inner[i] == " ":
                out.append(buf); buf = ""
    if buf.strip(): out.append(buf)
    return [s for s in out if s.strip()]

def split_clauses(sent):
    """يقسم الجملة الطويلة إلى مقاطع عند الفاصلة «،» خارج الوسوم (لا تُستخدم إلا إذا كانت الجملة أطول من أن تبقى الشاشة شبه فارغة)."""
    out = []; buf = ""; depth = 0; i = 0
    while i < len(sent):
        c = sent[i]
        if c == "<":
            j = sent.index(">", i); tag = sent[i:j + 1]; buf += tag
            depth += -1 if tag.startswith("</") else (0 if tag.endswith("/>") else 1); i = j + 1; continue
        buf += c; i += 1
        if depth == 0 and c == "،" and (i >= len(sent) or sent[i] == " "): out.append(buf); buf = ""
    if buf.strip(): out.append(buf)
    return out

def join_cross_page(T):
    """إذا انتهت صفحة أصلية في منتصف جملة، تُنقل بقية الجملة (من أول الصفحة التالية) إلى آخرها مع حواشيها، حتى تكتمل الجملة في نفس الشاشة."""
    P = T["pages"]; moved = 0
    for k in range(len(P) - 1):
        a, b = P[k], P[k + 1]
        if not b["html"].startswith('<p class="cont">') or not a["html"].endswith("</p>"): continue
        last_txt = html.unescape(re.sub(r"<[^>]+>", "", a["html"][a["html"].rfind("<p"):])).strip()
        if not last_txt or last_txt[-1] in END: continue
        end = b["html"].index("</p>"); inner = b["html"][len('<p class="cont">'):end]
        sents = split_sentences(inner)
        if not sents: continue
        frag = sents[0]; rest = inner[len(frag):] if inner.startswith(frag) else None
        if rest is None: continue
        refs = [int(x) for x in re.findall(r'<sup class="fn">\((\d+)\)</sup>', frag)]
        base = len(a["notes"]); mapping = {}
        for i, r in enumerate(refs): mapping[r] = base + i + 1; a["notes"].append(b["notes"][r - 1])
        frag = re.sub(r'<sup class="fn">\((\d+)\)</sup>', lambda m: f'<sup class="fn">({mapping[int(m.group(1))]})</sup>', frag)
        a["html"] = a["html"][:-4] + " " + frag.strip() + "</p>"
        b["notes"] = [x for i, x in enumerate(b["notes"], 1) if i not in mapping]
        shift = lambda m: f'<sup class="fn">({int(m.group(1)) - sum(1 for r in mapping if r < int(m.group(1)))})</sup>'
        rest_html = ('<p class="cont">' + rest.strip() + "</p>") if rest.strip() else ""
        b["html"] = re.sub(r'<sup class="fn">\((\d+)\)</sup>', shift, rest_html + b["html"][end + 4:])
        moved += 1
    return moved

def build_html(book, T, head):
    print("جمل مكتملة عبر حدود الصفحات:", join_cross_page(T))
    t = re.sub(r"\s*-\s*.*$", "", book["title"])
    blocks_pages = []
    for pg in T["pages"]:
        body = re.sub(r'(<sup class="fn">)\((\d+)\)', lambda m: m.group(1) + "(" + m.group(2) + ")", pg["html"])
        bl = []
        for m in re.finditer(r'<(p|h2|h3|h4|blockquote|div)([^>]*)>(.*?)</\1>', body, re.S):
            tag, attrs, inner = m.groups()
            txt = html.unescape(re.sub(r"<[^>]+>", "", inner))
            if tag == "p" and len(txt) < 80: attrs = attrs.replace('class="', 'class="s ') if 'class="' in attrs else attrs + ' class="s"'
            if tag in ("p", "blockquote"):
                inner = "".join('<span class="sn">' + "".join(f'<span class="cl">{c}</span>' for c in split_clauses(x)) + "</span>" for x in split_sentences(inner))
            bl.append(f"<{tag}{attrs}>{inner}</{tag}>")
        notes = [re.sub(r'^\s*\(\s*\)\s*', '', x) for x in pg["notes"]]
        blocks_pages.append({"n": pg["n"], "blocks": bl, "notes": notes})
    css = f"""
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Regular.ttf);font-weight:400}}
@font-face{{font-family:A;src:url(file://{FONTS}/Amiri-Bold.ttf);font-weight:700}}
@page{{size:{W}pt {H}pt;margin:0}} html{{direction:rtl}} body{{margin:0;font-family:A,serif;color:#1b1b1b}}
.pg{{position:relative;width:{W}pt;height:{H}pt;overflow:hidden;break-after:page}}
.hd{{position:absolute;top:11pt;left:20pt;right:20pt;display:flex;align-items:flex-end;justify-content:space-between;gap:8pt;padding-bottom:4pt;border-bottom:1pt solid #b99a61}}
.hd .t{{font-size:10pt;line-height:1.45;color:#4f625b;font-weight:700;max-width:74%;text-wrap:balance}}
.hd .n{{font-size:11.5pt;font-weight:700;color:#fff;background:#315b4e;border-radius:20pt;padding:0 10pt 2pt;white-space:nowrap}}
.ft{{position:absolute;bottom:9pt;left:0;right:0;text-align:center;font-size:11.5pt;font-weight:700;color:#315b4e}}
.ft span{{border-top:1pt solid #b99a61;padding:1pt 14pt 0}}
.bx{{position:absolute;top:52pt;bottom:32pt;left:22pt;right:22pt;display:flex;flex-direction:column}}
.c{{font-size:{FS}pt;line-height:2;text-align:justify;text-align-last:right}}
.c p,.c blockquote{{margin:0 0 .55em}} .c p{{text-indent:1.1em}} .c p.cont,.c p.li,.c blockquote.cont{{text-indent:0}} .c p.li{{padding-inline-start:.8em}} .c p.s{{text-align:right}}
.c blockquote{{padding:.1em .6em;border-inline-start:2.5pt solid #b99a61;background:#f6f2e8;border-radius:3pt}}
.c h2,.c h3,.c h4{{font-weight:700;color:#173d35;text-align:center;line-height:1.6;margin:.3em 0 .35em}}
.c h2{{font-size:1.14em}} .c h3{{font-size:1.08em}} .c h4{{font-size:1.03em}}
.c b{{color:#173d35}} .c sup.fn{{font-size:.58em;color:#315b4e;font-weight:700;line-height:0;vertical-align:.75em;padding:0 1pt}}
.c .orn{{text-align:center;color:#b99a61;letter-spacing:.5em}}
.fnb{{margin-top:auto;padding-top:.35em}} .fnb[hidden]{{display:none}}
.fnb ol{{list-style:none;margin:0;padding:.35em .6em .25em;background:#f4f7f5;border:.8pt solid #d6e2db;border-radius:5pt;font-size:{FS*0.74:.2f}pt;line-height:1.75;color:#2b2b2b}}
.fnb li{{text-align:right;padding-inline-start:1.5em;text-indent:-1.5em}} .fnb b{{color:#315b4e;font-size:.85em}}
.more{{position:absolute;left:22pt;bottom:0;font-style:normal;font-size:10pt;font-weight:400;color:#8a7346}}
.tp{{text-align:center;justify-content:center}} .tp .t{{font-size:21pt;font-weight:700;color:#173d35;line-height:1.7}} .tp .s{{font-size:14pt;line-height:1.9}}
"""
    tpage = '<div class="pg"><div class="bx tp">' + "".join(f'<div class="{c}">{html.escape(x)}</div>' for c, x in head) + "</div></div>"
    js = r"""
const DATA = __DATA__, TITLE = __TITLE__;
const AR = (s) => String(s).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
const root = document.getElementById("root"); const MAP = [];
function newPage(n, part) {
  const pg = document.createElement("div"); pg.className = "pg";
  pg.innerHTML = '<div class="hd"><span class="t"></span><span class="n"></span></div><div class="bx"><div class="c body"></div><div class="fnb c" hidden><ol></ol></div></div><div class="ft"><span></span></div>';
  pg.querySelector(".t").textContent = TITLE; pg.querySelector(".n").textContent = "صفحة " + AR(n) + (part > 1 ? " (تابع)" : "");
  pg.querySelector(".ft span").textContent = AR(n); root.appendChild(pg); MAP.push(n);
  const hd = pg.querySelector(".hd"); pg.querySelector(".bx").style.top = (hd.offsetTop + hd.offsetHeight + 9) + "px"; return pg;
}
function fits(pg, notes) {
  const ol = pg.querySelector(".fnb ol"), box = pg.querySelector(".fnb"); ol.innerHTML = "";
  const refs = [...pg.querySelectorAll(".body sup.fn")].map((s) => +s.textContent.replace(/\D/g, ""));
  refs.forEach((r) => { if (notes[r - 1] != null) { const li = document.createElement("li"); li.innerHTML = "<b>(" + AR(r) + ")</b> " + notes[r - 1]; ol.appendChild(li); } });
  box.hidden = !ol.children.length;
  const bx = pg.querySelector(".bx"); return bx.scrollHeight <= bx.clientHeight + 1;
}
for (const P of DATA) {
  let part = 1, pg = newPage(P.n, part), body = pg.querySelector(".body");
  const tmp = document.createElement("div");
  for (const h of P.blocks) {
    tmp.innerHTML = h; const blk = tmp.firstElementChild; body.appendChild(blk);
    if (fits(pg, P.notes)) continue;
    blk.remove();
    const sns = [...blk.querySelectorAll(":scope > .sn")];
    if (!sns.length) { // عنوان أو كتلة بلا جمل: تنتقل كاملة للشاشة التالية
      fits(pg, P.notes); pg = newPage(P.n, ++part); body = pg.querySelector(".body"); body.appendChild(blk); fits(pg, P.notes); continue;
    }
    // نوزّع الجمل: ما يتسع يبقى، والباقي يبدأ شاشة جديدة كفقرة متابِعة
    let cur = blk.cloneNode(false); body.appendChild(cur); let first = true;
    for (const s of sns) {
      cur.appendChild(s);
      if (!fits(pg, P.notes)) {
        s.remove();
        // الجملة لا تتسع: إن كانت الشاشة ما زالت شبه فارغة نوزّع مقاطعها (عند الفواصل) بدل ترك فراغ كبير
        const bx = pg.querySelector(".bx"), used = body.scrollHeight / bx.clientHeight;
        const cls = [...s.querySelectorAll(":scope > .cl")];
        if (used < 0.6 && cls.length > 1) {
          const part1 = s.cloneNode(false); cur.appendChild(part1); let k = 0;
          for (; k < cls.length; k++) { part1.appendChild(cls[k]); if (!fits(pg, P.notes)) { cls[k].remove(); break; } }
          if (!part1.childNodes.length) part1.remove();
          if (k < cls.length) { const rest = s.cloneNode(false); cls.slice(k).forEach((c) => rest.appendChild(c)); fits(pg, P.notes);
            pg = newPage(P.n, ++part); body = pg.querySelector(".body"); cur = blk.cloneNode(false); cur.classList.add("cont"); body.appendChild(cur); cur.appendChild(rest); fits(pg, P.notes); }
          continue;
        }
        if (!cur.childNodes.length) cur.remove();
        fits(pg, P.notes);
        pg = newPage(P.n, ++part); body = pg.querySelector(".body");
        cur = blk.cloneNode(false); cur.classList.add("cont"); body.appendChild(cur); cur.appendChild(s);
        fits(pg, P.notes);
      }
    }
  }
  fits(pg, P.notes);
}
// علامة «يتبع» أسفل الشاشات التي تكمل صفحتها في الشاشة التالية
const pages = [...root.children];
pages.forEach((p, i) => { if (pages[i + 1] && MAP[i] === MAP[i + 1]) { const m = document.createElement("i"); m.className = "more"; m.textContent = "يتبع ←"; p.querySelector(".ft").appendChild(m); } });
document.body.dataset.map = JSON.stringify(MAP); document.body.dataset.done = 1;
"""
    js = js.replace("__DATA__", json.dumps(blocks_pages, ensure_ascii=False)).replace("__TITLE__", json.dumps(t, ensure_ascii=False))
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{tpage}<div id="root"></div><script>{js}</script></body></html>'

async def render(s, out):
    from playwright.async_api import async_playwright
    open("/tmp/_sent.html", "w").write(s)
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        await pg.goto("file:///tmp/_sent.html"); await pg.wait_for_selector("body[data-done]", timeout=120000); await pg.wait_for_timeout(300)
        mp = json.loads(await pg.evaluate("document.body.dataset.map"))
        over = await pg.evaluate("[...document.querySelectorAll('#root .pg .bx')].map((b,i)=>b.scrollHeight>b.clientHeight+2?i:-1).filter(i=>i>=0)")
        await pg.pdf(path=out, prefer_css_page_size=True, print_background=True); await b.close()
    return mp, over

def main(bid):
    data = json.load(open(ROOT / "books.json")); book = next(b for b in data["books"] if b["id"] == bid)
    T = json.load(open(ROOT / book.get("text", f"texts/{bid}.json"))); head = json.load(open(ROOT / f"texts/{bid}.head.json"))
    mp, over = asyncio.run(render(build_html(book, T, head), "/tmp/_sent.pdf"))
    d = pymupdf.open("/tmp/_sent.pdf"); orig = pymupdf.open(ROOT / book["file"])
    out = pymupdf.open(); out.insert_pdf(orig, from_page=0, to_page=0); out.insert_pdf(d)
    fn = re.sub(r"\.pdf$", "-large.pdf", book["file"]); out.save(ROOT / fn, garbage=3, deflate=True)
    pmap = [0, 0] + mp
    assert len(pmap) == out.page_count, (len(pmap), out.page_count)
    starts = {}
    for i, n in enumerate(pmap):
        if n: starts.setdefault(str(n), i + 1)
    ch = []
    for pg in T["pages"]:
        for m in re.finditer(r"<h[234][^>]*>(.*?)</h[234]>", pg["html"]):
            ch.append({"t": html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(), "p": starts[str(pg["n"])]})
    old = book.get("large", {})
    book["large"] = {"file": fn, "map": pmap, "starts": starts, "chapters": ch, "v": int(old.get("v", 0)) + 1, "layout": "sentences"}
    json.dump(data, open(ROOT / "books.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    c = Counter(mp)
    print(fn, out.page_count, "screens per page:", dict(Counter(c.values())), "overflow screens:", over)

if __name__ == "__main__":
    main(sys.argv[1])
