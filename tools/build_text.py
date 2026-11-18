# الاستخدام: python3 tools/build_text.py ملف.docx books/book-NN.pdf texts/bNN.json رقم_صفحة_المقدمة_في_الملف فرق_الترقيم
# يبني «النسخة النصية المكبّرة» لكتاب من ملف الورد الأصلي، ويقسّمها على صفحات الكتاب المنشور (PDF)
# بحيث يطابق رقم كل صفحة الرقم المطبوع في الكتاب والفهرس. النص يؤخذ كما هو من الورد بلا أي تعديل.
import sys, json, re, zipfile, subprocess, unicodedata, difflib, html, shutil, os
import pymupdf

SYM = {  # رموز خطوط الزخرفة في الورد ← نص يونيكود
 ('AGA Arabesque','F072'):'ﷺ', ('AGA Arabesque','F065'):'ﷺ',
 ('AGA Arabesque','F074'):'رضي الله عنه', ('AGA Arabesque','F075'):'رضي الله عنها', ('AGA Arabesque','F079'):'رضي الله عنهم',
 ('KFGQPC Arabic Symbols 01','F053'):'عليه السلام',
 ('AGA Arabesque','F028'):'﴾', ('AGA Arabesque','F029'):'﴿',
 ('AGA Arabesque','F060'):'⁂', ('AGA Arabesque','F06D'):'⁂', ('AGA Arabesque','F04D'):'⁂',
 ('Wingdings','F0DB'):'◂',
}
HON = {'رضي الله عنها','ﷺ','رضي الله عنه','رضي الله عنها','رضي الله عنهم','عليه السلام','رحمه الله'}
FONTMAP = {'Adwaa Elsalaf': {'$': 'رحمه الله'}, 'AAA GoldenLotus': {'▲': 'رضي الله عنها', '﷽': '﷽'}}

def prep_docx(src, dst):
    z = zipfile.ZipFile(src); out = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
    for it in z.infolist():
        data = z.read(it.filename)
        if it.filename in ('word/document.xml', 'word/footnotes.xml'):
            s = data.decode('utf8')
            def rep(m):
                k = (m.group(1), m.group(2).upper())
                if k not in SYM: raise SystemExit(f'رمز غير معروف {k}')
                return '<w:t xml:space="preserve">' + SYM[k] + '</w:t>'
            s = re.sub(r'<w:sym w:font="([^"]+)" w:char="([^"]+)"/>', rep, s)
            def runrep(m):
                r = m.group(0); f = re.search(r'w:ascii="([^"]+)"', r)
                if not f or f.group(1) not in FONTMAP: return r
                mp = FONTMAP[f.group(1)]
                def tt(mm):
                    t = mm.group(2)
                    bad = [ch for ch in t if ch not in mp and not ch.isspace() and (ch.isascii() or '\ue000' <= ch <= '\uf8ff' or ch in '▲▼◆●■')]
                    if bad: raise SystemExit(f'رمز غير معروف في خط {f.group(1)}: {bad}')
                    return mm.group(1) + ''.join(mp.get(ch, ch) for ch in t) + '</w:t>'
                return re.sub(r'(<w:t[^>]*>)([^<]*)</w:t>', tt, r)
            s = re.sub(r'<w:r[ >].*?</w:r>', runrep, s, flags=re.S)
            # الرموز المكتوبة مباشرة بمحارف الاستخدام الخاص (خط AGA Arabesque)
            s = s.replace('', 'ﷺ').replace('', 'ﷺ').replace('', 'رضي الله عنه')
            data = s.encode('utf8')
        out.writestr(it, data)
    out.close()

def N(s):  # تطبيع للمطابقة فقط (لا يُعرض)
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'[ً-ٰٟۖ-ۭـ]', '', s)
    s = s.translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    s = re.sub(r'[^ء-ي]', '', s)
    return re.sub('[ال]', '', s)

# ---------- قراءة ورد عبر pandoc AST ----------
def inl_words(inls, st, out):
    """يحوّل العناصر السطرية إلى كلمات: (نص, عريض, حواشي[])"""
    for e in inls:
        t = e['t']; c = e.get('c')
        if t == 'Str': out.append([c, st.get('b', False), []])
        elif t in ('Space', 'SoftBreak'): out.append(None)
        elif t == 'LineBreak': out.append(None)
        elif t == 'Strong': inl_words(c, dict(st, b=True), out)
        elif t in ('Emph', 'Underline', 'SmallCaps', 'Strikeout', 'Superscript', 'Subscript'): inl_words(c, st, out)
        elif t == 'Span': inl_words(c[1], st, out)
        elif t == 'Quoted': out.append(['“', st.get('b', False), []]); inl_words(c[1], st, out); out.append(['”', st.get('b', False), []])
        elif t == 'Link': inl_words(c[1], st, out)
        elif t == 'Note':
            note = []
            for b in c:
                if b['t'] in ('Para', 'Plain'):
                    w = []; inl_words(b['c'], {}, w); note.append(join(w))
            # تُلحق الحاشية بآخر كلمة
            for x in reversed(out):
                if x is not None: x[2].append(' '.join(note).strip()); break
            else: out.append(['', False, [' '.join(note).strip()]])
        elif t == 'Code': out.append([c[1], False, []])
        elif t == 'Image': pass
        elif t == 'Math': out.append([c[1], False, []])
        elif t == 'RawInline': pass
        elif t == 'Cite': inl_words(c[1], st, out)

def join(w):
    s = []; cur = ''
    for x in w:
        if x is None: s.append(cur); cur = ''
        else: cur += x[0]
    s.append(cur); return re.sub(r'\s+', ' ', ' '.join(s)).strip()

def words_of(inls):
    raw = []; inl_words(inls, {}, raw)
    # دمج الأجزاء المتلاصقة (بلا مسافة) في كلمة واحدة
    words = []; glue = False
    for x in raw:
        if x is None: glue = False; continue
        if glue and words: words[-1][0] += x[0]; words[-1][2] += x[2]; words[-1][1] = words[-1][1] and x[1]
        else: words.append(list(x)); glue = True
    return [w for w in words if w[0] or w[2]]

def blocks_from(ast):
    res = []
    def walk(bs, quote=False, bullet=None):
        for b in bs:
            t = b['t']; c = b.get('c')
            if t == 'Header': res.append({'k': 'h', 'lvl': c[0], 'w': words_of(c[2])})
            elif t in ('Para', 'Plain'):
                w = words_of(c)
                if w: res.append({'k': 'q' if quote else ('li' if bullet else 'p'), 'w': w})
            elif t == 'BlockQuote': walk(c, True)
            elif t in ('BulletList', 'OrderedList'):
                items = c if t == 'BulletList' else c[1]
                for it in items: walk(it, quote, True)
            elif t == 'Div': walk(c[1], quote, bullet)
            elif t == 'Table':
                # الجدول: كل صف سطر واحد بخلاياه مفصولة
                def cells(o):
                    if isinstance(o, dict):
                        if o.get('t') in ('Para', 'Plain'): yield words_of(o['c'])
                        else:
                            cc = o.get('c')
                            if isinstance(cc, (dict, list)): yield from cells(cc)
                    elif isinstance(o, list):
                        for v in o: yield from cells(v)
                for row in cells(c):
                    if row: res.append({'k': 'p', 'w': row})
    walk(ast['blocks']); return res

# ---------- صفحات PDF ----------
def page_sigs(pdf):
    d = pymupdf.open(pdf); sigs = []
    for p in d:
        bl = [b for b in p.get_text('blocks') if b[6] == 0]
        H = p.rect.height
        bl.sort(key=lambda b: b[1])
        txt = ''
        for b in bl:
            if b[1] < H * 0.07 and len(N(b[4])) < 6: continue  # رأس الصفحة/الرقم
            txt += N(b[4])
            if len(txt) > 160: break
        full = N(' '.join(b[4] for b in bl))
        sigs.append((txt, full))
    return sigs

def main(docx, pdf, out, start_pdf, offset, start_marker='المقدمة'):
    tmp = '/tmp/_bt.docx'; prep_docx(docx, tmp)
    ast = json.loads(subprocess.run(['pandoc', tmp, '-t', 'json'], capture_output=True, check=True).stdout)
    B = blocks_from(ast)
    # البداية من أول عنوان «المقدمة»
    i0 = next(i for i, b in enumerate(B) if b['k'] == 'h' and start_marker in join([[w[0], w[1], []] for w in b['w']]) ) if start_marker else 0
    B = B[i0:]
    # تيار الكلمات
    toks = []; S = ''; pos = []
    for bi, b in enumerate(B):
        for wi, w in enumerate(b['w']):
            pos.append(len(S)); toks.append((bi, wi)); S += N(w[0])
    sigs = page_sigs(pdf)
    npages = len(sigs)
    bounds = [0]; scores = []
    avg = len(S) / max(1, (npages - start_pdf + 1))
    import bisect
    for pg in range(start_pdf + 1, npages + 1):
        sig = sigs[pg - 1][0][:70]
        if len(sig) < 15: bounds.append(bounds[-1]); scores.append(0); continue
        lo = bounds[-1] + 1; hi = min(len(toks), lo + 400 + int(3 * avg / 4))
        best = (0, lo)
        prev_c = pos[bounds[-1]]
        for ti in range(lo, hi):
            c = pos[ti]
            if c < prev_c + avg * 0.08: continue
            if c > prev_c + avg * 3: break
            r = difflib.SequenceMatcher(None, sig, S[c:c + len(sig)], autojunk=False).ratio()
            if r > best[0]: best = (r, ti)
        bounds.append(best[1]); scores.append(round(best[0], 2))
    bounds.append(len(toks))
    # بناء HTML لكل صفحة
    def esc(s): return html.escape(s, quote=False)
    pages = []
    for k in range(len(bounds) - 1):
        a, b_ = bounds[k], bounds[k + 1]
        segs = []; notes = []; cur_b = None; buf = []; first_b = toks[a][0] if a < len(toks) else None
        def flush():
            if cur_b is None or not buf: return
            blk = B[cur_b]; cont = (cur_b == first_b and toks[a][1] > 0)
            tag = {'h': 'h%d' % min(4, max(2, blk.get('lvl', 2) + 1)), 'p': 'p', 'q': 'blockquote', 'li': 'p'}[blk['k']]
            cls = []
            if cont: cls.append('cont')
            if blk['k'] == 'li': cls.append('li')
            segs.append(f'<{tag}{" class=%s" % chr(34) + " ".join(cls) + chr(34) if cls else ""}>' + ' '.join(buf) + f'</{tag}>')
        for ti in range(a, b_):
            bi, wi = toks[ti]
            if bi != cur_b: flush(); buf = []; cur_b = bi
            w = B[bi]['w'][wi]
            t = esc(w[0])
            if '⁂' in t:
                if t.strip('⁂ ') == '': flush(); buf = []; segs.append('<div class="orn" aria-hidden="true">✽ ✽ ✽</div>'); cur_b = None; continue
                t = t.replace('⁂', '')
            for h in HON:
                if h in t and len(h) > 1: t = t.replace(h, f'<span class="hon">{h}</span>')
            if w[1]: t = f'<b>{t}</b>'
            for n in w[2]:
                notes.append(esc(n)); ref = f'<sup class="fn">({len(notes)})</sup>'
                if '()' in t: t = t.replace('()', ref, 1)
                else: t += ref
            buf.append(t)
        flush()
        pdfp = start_pdf + k
        pages.append({'n': pdfp - offset, 'pdf': pdfp, 'html': ''.join(segs), 'notes': notes})
    json.dump({'pages': pages, 'scores': scores}, open(out, 'w'), ensure_ascii=False)
    print('pages', len(pages), 'words', len(toks), 'min score', min(scores) if scores else None)
    print('low:', [(start_pdf + 1 + i, s) for i, s in enumerate(scores) if s < 0.75])

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
