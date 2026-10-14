/*
 * HTL — Script dàn trang tự động cho Adobe InDesign (ExtendScript, CC 2019 trở lên).
 *
 * KHÔNG chạy trực tiếp file này. Chạy file `run_in_indesign.jsx` trong thư mục
 * gói dựng (do lệnh `htl build` tạo ra); file đó nạp cấu hình HTL_JOB rồi gọi script này.
 *
 * Các bước:
 *   1. Mở file mẫu .indt (hoặc tự tạo tài liệu theo thông số mẫu).
 *   2. Đặt hệ màu (CMYK profile của nhà in), tạo style còn thiếu.
 *   3. Với mỗi chương: tạo trang mới (chương bắt đầu trang lẻ nếu cấu hình),
 *      đặt file ICML, thay mốc ảnh bằng ảnh thật, gộp ô bảng, rồi tự thêm trang
 *      cho đến khi hết chữ (không còn overset).
 *   4. Kiểm tra: chữ tràn, mốc ảnh còn sót, font thiếu, link ảnh hỏng, số bảng/
 *      chú thích/hình khớp bản thảo.
 *   5. Lưu .indd và xuất PDF/X (CMYK, không nén mất dữ liệu, không giảm độ phân giải ảnh).
 *
 * Lưu ý: ExtendScript là JavaScript ES3 — không dùng let/const, arrow function, JSON...
 */

(function () {
    if (typeof HTL_JOB === "undefined") {
        alert("Hãy chạy file run_in_indesign.jsx trong thư mục gói dựng, không chạy trực tiếp htl_build.jsx.");
        return;
    }

    var JOB = HTL_JOB;
    var T = JOB.template;
    var JOB_DIR = File($.fileName).parent.fsName;
    var MM = 72 / 25.4;
    var LOG = { errors: [], warnings: [], infos: [], chapters: [] };
    var BODY_MASTER = null;
    var FIG_COUNT = 0;

    function err(m) { LOG.errors.push(m); }
    function warn(m) { LOG.warnings.push(m); }
    function info(m) { LOG.infos.push(m); }

    function trySet(obj, prop, value, label) {
        try {
            obj[prop] = value;
            return true;
        } catch (e) {
            warn("Không đặt được " + (label || prop) + ": " + e);
            return false;
        }
    }

    function hasKey(o, k) { return o && o.hasOwnProperty(k) && o[k] !== null; }

    // ------------------------------------------------------------------
    // JSON (ES3 không có sẵn)
    // ------------------------------------------------------------------
    function jsonStr(s) {
        s = String(s);
        var out = "\"";
        for (var i = 0; i < s.length; i++) {
            var c = s.charAt(i), code = s.charCodeAt(i);
            if (c === "\"" || c === "\\") out += "\\" + c;
            else if (code < 32 || code > 126) {
                var h = code.toString(16);
                while (h.length < 4) h = "0" + h;
                out += "\\u" + h;
            } else out += c;
        }
        return out + "\"";
    }

    function toJSON(v, indent) {
        indent = indent || "";
        var next = indent + "  ";
        if (v === null || v === undefined) return "null";
        if (typeof v === "number" || typeof v === "boolean") return String(v);
        if (typeof v === "string") return jsonStr(v);
        var parts = [], k;
        if (v instanceof Array) {
            for (k = 0; k < v.length; k++) parts.push(next + toJSON(v[k], next));
            return parts.length ? "[\n" + parts.join(",\n") + "\n" + indent + "]" : "[]";
        }
        for (k in v) if (v.hasOwnProperty(k)) parts.push(next + jsonStr(k) + ": " + toJSON(v[k], next));
        return parts.length ? "{\n" + parts.join(",\n") + "\n" + indent + "}" : "{}";
    }

    function writeText(path, text) {
        var f = File(path);
        f.encoding = "UTF-8";
        f.lineFeed = "Unix";
        f.open("w");
        f.write(text);
        f.close();
    }

    // ------------------------------------------------------------------
    // Tài liệu
    // ------------------------------------------------------------------
    function marginBounds(page) {
        var b = page.bounds, mp = page.marginPreferences, x1, x2;
        if (page.side == PageSideOptions.LEFT_HAND) {
            x1 = b[1] + mp.right;   // lề ngoài
            x2 = b[3] - mp.left;    // lề trong (gáy)
        } else {
            x1 = b[1] + mp.left;
            x2 = b[3] - mp.right;
        }
        return [b[0] + mp.top, x1, b[2] - mp.bottom, x2];
    }

    function setMargins(target) {
        var m = T.margins_mm;
        var mp = target.marginPreferences;
        trySet(mp, "top", m.top * MM);
        trySet(mp, "bottom", m.bottom * MM);
        trySet(mp, "left", m.inside * MM);
        trySet(mp, "right", m.outside * MM);
        trySet(mp, "columnCount", T.columns.count);
        trySet(mp, "columnGutter", T.columns.gutter_mm * MM);
    }

    function openOrCreate() {
        var doc;
        if (T.indt) {
            var f = File(T.indt);
            if (!f.exists) throw new Error("Không tìm thấy file mẫu .indt: " + T.indt);
            doc = app.open(f, true, OpenOptions.OPEN_COPY);
            info("Dùng file mẫu: " + f.fsName);
        } else {
            doc = app.documents.add(true);
            var dp = doc.documentPreferences;
            dp.facingPages = T.page.facing_pages;
            dp.pageWidth = T.computed.page_w;
            dp.pageHeight = T.computed.page_h;
            dp.documentBleedUniformSize = true;
            dp.documentBleedTopOffset = T.page.bleed_mm * MM;
            dp.pagesPerDocument = 1;
            setMargins(doc);
            for (var s = 0; s < doc.masterSpreads.length; s++) {
                for (var p = 0; p < doc.masterSpreads[s].pages.length; p++) setMargins(doc.masterSpreads[s].pages[p]);
            }
            setMargins(doc.pages[0]);
            info("Chưa có file mẫu .indt — đã tự tạo tài liệu " + T.page.width_mm + "×" + T.page.height_mm + " mm.");
        }
        doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
        BODY_MASTER = doc.masterSpreads[0];
        if (T.body_master) {
            var ms = doc.masterSpreads.itemByName(T.body_master);
            if (ms.isValid) BODY_MASTER = ms;
            else warn("Không có master '" + T.body_master + "', dùng " + BODY_MASTER.name);
        }
        return doc;
    }

    function addFolios(doc) {
        // Chỉ dùng khi tự tạo tài liệu: số trang ở chân trang, phía ngoài.
        var st = paraStyle(doc, "Folio", { font: "sans", size: 8, leading: 10 });
        var pages = BODY_MASTER.pages;
        for (var i = 0; i < pages.length; i++) {
            var pg = pages[i], b = pg.bounds, mp = pg.marginPreferences;
            var mb = marginBounds(pg);
            var y1 = b[2] - mp.bottom + 4 * MM;
            var tf = pg.textFrames.add({ geometricBounds: [y1, mb[1], y1 + 5 * MM, mb[3]] });
            tf.contents = SpecialCharacters.AUTO_PAGE_NUMBER;
            tf.paragraphs[0].appliedParagraphStyle = st;
            tf.paragraphs[0].justification = (pg.side == PageSideOptions.LEFT_HAND) ? Justification.LEFT_ALIGN : Justification.RIGHT_ALIGN;
        }
    }

    // ------------------------------------------------------------------
    // Màu
    // ------------------------------------------------------------------
    function setupColor(doc) {
        var c = T.color;
        if (!trySet(doc, "cmykProfile", c.cmyk_profile, "CMYK profile '" + c.cmyk_profile + "'")) {
            err("CMYK profile '" + c.cmyk_profile + "' chưa cài trên máy này. Cài ICC profile của nhà in (Color Settings) rồi chạy lại.");
        }
        trySet(doc, "rgbProfile", c.rgb_profile, "RGB profile");
        try { doc.transparencyPreferences.blendingSpace = BlendingSpace.CMYK; } catch (e) {}
        for (var name in T.swatches) {
            if (!T.swatches.hasOwnProperty(name)) continue;
            if (!doc.colors.itemByName(name).isValid) {
                doc.colors.add({ name: name, model: ColorModel.PROCESS, space: ColorSpace.CMYK, colorValue: T.swatches[name] });
            }
        }
    }

    // ------------------------------------------------------------------
    // Style
    // ------------------------------------------------------------------
    var JUST = {
        left: "LEFT_ALIGN", right: "RIGHT_ALIGN", center: "CENTER_ALIGN",
        justify: "LEFT_JUSTIFIED", justify_all: "FULLY_JUSTIFIED"
    };

    function fontKeyOf(name, def) {
        var guard = 0;
        while (def && guard++ < 10) {
            if (def.font) return def.font;
            def = def.based_on ? T.paragraph_styles[def.based_on] : null;
        }
        return "serif";
    }

    function applyParaDef(doc, st, def, name) {
        if (def.based_on) {
            var base = doc.paragraphStyles.itemByName(def.based_on);
            if (base.isValid) trySet(st, "basedOn", base, name + ".basedOn");
        }
        if (def.font || def.weight || !def.based_on) {
            var fk = fontKeyOf(name, def);
            var f = T.fonts[fk];
            if (f) {
                trySet(st, "appliedFont", f.family, name + ".font");
                trySet(st, "fontStyle", f[def.weight || "regular"] || f.regular, name + ".fontStyle");
            }
        }
        if (hasKey(def, "size")) trySet(st, "pointSize", def.size);
        if (hasKey(def, "leading")) trySet(st, "leading", def.leading === "auto" ? Leading.AUTO : def.leading);
        if (hasKey(def, "align")) trySet(st, "justification", Justification[JUST[def.align] || "LEFT_ALIGN"]);
        if (hasKey(def, "first_indent_mm")) trySet(st, "firstLineIndent", def.first_indent_mm * MM);
        if (hasKey(def, "left_indent_mm")) trySet(st, "leftIndent", def.left_indent_mm * MM);
        if (hasKey(def, "right_indent_mm")) trySet(st, "rightIndent", def.right_indent_mm * MM);
        if (hasKey(def, "space_before")) trySet(st, "spaceBefore", def.space_before);
        if (hasKey(def, "space_after")) trySet(st, "spaceAfter", def.space_after);
        if (hasKey(def, "keep_with_next")) trySet(st, "keepWithNext", def.keep_with_next);
        if (hasKey(def, "color")) {
            var sw = doc.swatches.itemByName(def.color);
            if (sw.isValid) trySet(st, "fillColor", sw);
        }
        if (def.bullet) trySet(st, "bulletsAndNumberingListType", ListType.BULLET_LIST);
        // Tiếng Việt: tắt ngắt từ (gạch nối) để không chia đôi âm tiết/thuật ngữ.
        trySet(st, "hyphenation", false);
    }

    function paraStyle(doc, name, def) {
        var st = doc.paragraphStyles.itemByName(name);
        if (st.isValid) return st;
        st = doc.paragraphStyles.add({ name: name });
        applyParaDef(doc, st, def || {}, name);
        return st;
    }

    function charStyle(doc, name, fontStyle) {
        var st = doc.characterStyles.itemByName(name);
        if (st.isValid) return st;
        st = doc.characterStyles.add({ name: name });
        trySet(st, "fontStyle", fontStyle);
        return st;
    }

    function ensureStyles(doc) {
        var created = [];
        var names = [], k;
        for (k in T.roles) if (T.roles.hasOwnProperty(k)) names.push(T.roles[k]);
        // Tạo các style gốc trước (based_on) rồi đến style kế thừa.
        var defs = T.paragraph_styles || {};
        var order = [];
        for (k = 0; k < names.length; k++) if (!(defs[names[k]] && defs[names[k]].based_on)) order.push(names[k]);
        for (k = 0; k < names.length; k++) if (defs[names[k]] && defs[names[k]].based_on) order.push(names[k]);
        for (k = 0; k < order.length; k++) {
            var n = order[k];
            if (!doc.paragraphStyles.itemByName(n).isValid) {
                if (defs[n] && defs[n].based_on && !doc.paragraphStyles.itemByName(defs[n].based_on).isValid) {
                    paraStyle(doc, defs[n].based_on, defs[defs[n].based_on]);
                }
                paraStyle(doc, n, defs[n]);
                created.push(n);
            }
        }
        var cs = T.character_styles;
        charStyle(doc, cs.bold, "Bold");
        charStyle(doc, cs.italic, "Italic");
        charStyle(doc, cs.bold_italic, "Bold Italic");

        // Ảnh: đặt kiểu "Above Line" trong một đoạn riêng (style Figure) — chuẩn cho sách.
        var os = doc.objectStyles.itemByName("HTL Figure");
        if (!os.isValid) {
            os = doc.objectStyles.add({ name: "HTL Figure" });
            try {
                os.enableAnchoredObjectOptions = true;
                os.anchoredObjectSettings.anchoredPosition = AnchorPosition.ABOVE_LINE;
                os.anchoredObjectSettings.horizontalAlignment = HorizontalAlignment.CENTER_ALIGN;
                os.enableStroke = true;
                os.strokeWeight = 0;
            } catch (e) { warn("Object style HTL Figure: " + e); }
        }

        // Bảng
        var ts = doc.tableStyles.itemByName(T.table_style);
        if (!ts.isValid) {
            ts = doc.tableStyles.add({ name: T.table_style });
            var cell = doc.cellStyles.itemByName("HTL Cell");
            if (!cell.isValid) {
                cell = doc.cellStyles.add({ name: "HTL Cell" });
                try {
                    cell.topInset = 2; cell.bottomInset = 2; cell.leftInset = 3; cell.rightInset = 3;
                    cell.topEdgeStrokeWeight = 0.25; cell.bottomEdgeStrokeWeight = 0.25;
                    cell.leftEdgeStrokeWeight = 0; cell.rightEdgeStrokeWeight = 0;
                    cell.appliedParagraphStyle = doc.paragraphStyles.itemByName(T.roles.table_body);
                } catch (e) { warn("Cell style: " + e); }
            }
            var head = doc.cellStyles.itemByName("HTL Head Cell");
            if (!head.isValid) {
                head = doc.cellStyles.add({ name: "HTL Head Cell", basedOn: cell });
                try {
                    head.fillColor = doc.swatches.itemByName("HTL Box Tint").isValid ? doc.swatches.itemByName("HTL Box Tint") : doc.swatches.itemByName("None");
                    head.appliedParagraphStyle = doc.paragraphStyles.itemByName(T.roles.table_head);
                } catch (e) { warn("Header cell style: " + e); }
            }
            try {
                ts.bodyRegionCellStyle = cell;
                ts.headerRegionCellStyle = head;
                ts.topBorderStrokeWeight = 0.75; ts.bottomBorderStrokeWeight = 0.75;
                ts.leftBorderStrokeWeight = 0; ts.rightBorderStrokeWeight = 0;
            } catch (e) { warn("Table style: " + e); }
        }

        try {
            doc.footnoteOptions.footnoteTextStyle = doc.paragraphStyles.itemByName(T.roles.footnote);
        } catch (e) {}

        if (created.length) {
            (T.indt ? warn : info)("Đã tạo style chưa có trong mẫu: " + created.join(", "));
        }
    }

    // ------------------------------------------------------------------
    // Đặt nội dung
    // ------------------------------------------------------------------
    function makeFrame(page) {
        var tf = page.textFrames.add({ geometricBounds: marginBounds(page) });
        tf.textFramePreferences.textColumnCount = T.columns.count;
        tf.textFramePreferences.textColumnGutter = T.columns.gutter_mm * MM;
        return tf;
    }

    function unlinkStoryLinks(doc) {
        for (var i = doc.links.length - 1; i >= 0; i--) {
            var l = doc.links[i];
            if (/\.icml$/i.test(l.name)) {
                try { l.unlink(); } catch (e) { warn("Không bỏ liên kết ICML " + l.name + ": " + e); }
            }
        }
    }

    function resetFind() {
        app.findGrepPreferences = NothingEnum.NOTHING;
        app.changeGrepPreferences = NothingEnum.NOTHING;
        try {
            app.findChangeGrepOptions.includeFootnotes = true;
            app.findChangeGrepOptions.includeHiddenLayers = true;
            app.findChangeGrepOptions.includeLockedLayersForFind = true;
            app.findChangeGrepOptions.includeLockedStoriesForFind = true;
            app.findChangeGrepOptions.includeMasterPages = false;
        } catch (e) {}
    }

    function placeFigures(doc, story, ch) {
        var os = doc.objectStyles.itemByName("HTL Figure");
        var placed = 0;
        for (var k = ch.figures.length - 1; k >= 0; k--) {
            var marker = ch.figures[k];
            var spec = JOB.figures[marker];
            resetFind();
            app.findGrepPreferences.findWhat = marker;
            var found = story.findGrep();
            if (found.length != 1) {
                err(ch.id + ": tìm thấy " + found.length + " mốc " + marker + " (cần đúng 1).");
                continue;
            }
            if (!spec) { err(ch.id + ": thiếu thông tin ảnh cho " + marker); continue; }
            var file = File(JOB_DIR + "/images/" + spec.file);
            if (!file.exists) { err(ch.id + ": không có file ảnh " + file.fsName); continue; }
            var ip = found[0].insertionPoints[-1];
            var res;
            try {
                res = ip.place(file);
            } catch (e) {
                err(ch.id + ": không đặt được ảnh " + spec.file + ": " + e);
                continue;
            }
            var g = res[0];
            var rect = g.parent;
            try {
                if (os.isValid) rect.appliedObjectStyle = os;
                rect.anchoredObjectSettings.anchoredPosition = AnchorPosition.ABOVE_LINE;
                rect.anchoredObjectSettings.horizontalAlignment = HorizontalAlignment.CENTER_ALIGN;
            } catch (e) { warn(ch.id + ": thiết lập neo ảnh " + spec.file + ": " + e); }
            // Kích thước: rộng w_pt, cao theo đúng tỉ lệ ảnh gốc
            var gb = g.geometricBounds;
            var gw = gb[3] - gb[1], gh = gb[2] - gb[0];
            var w = spec.w_pt, h = gw > 0 ? w * gh / gw : spec.h_pt;
            var maxH = T.computed.text_h * T.images.max_height_ratio;
            if (h > maxH) { w = w * maxH / h; h = maxH; }
            var rb = rect.geometricBounds;
            rect.geometricBounds = [rb[0], rb[1], rb[0] + h, rb[1] + w];
            rect.fit(FitOptions.FILL_PROPORTIONALLY);
            rect.fit(FitOptions.CENTER_CONTENT);
            try {
                var ppi = g.effectivePpi;
                var minPpi = Math.min(ppi[0], ppi[1]);
                if (minPpi < T.images.min_ppi - 0.5) warn(ch.id + ": ảnh " + spec.file + " chỉ đạt " + Math.round(minPpi) + " ppi hiệu dụng.");
            } catch (e) {}
            // Xóa mốc chữ
            resetFind();
            app.findGrepPreferences.findWhat = marker;
            app.changeGrepPreferences.changeTo = "";
            story.changeGrep();
            placed++;
        }
        FIG_COUNT += placed;
        return placed;
    }

    function fixTables(doc, story, ch) {
        var tables = story.tables;
        if (tables.length != ch.tables.length) {
            err(ch.id + ": số bảng trong InDesign (" + tables.length + ") khác bản thảo (" + ch.tables.length + ").");
        }
        for (var i = 0; i < tables.length && i < ch.tables.length; i++) {
            var t = tables[i], spec = ch.tables[i];
            for (var k = spec.merges.length - 1; k >= 0; k--) {
                var m = spec.merges[k];
                try {
                    var a = t.cells.itemByName(m[0] + ":" + m[1]);
                    var b = t.cells.itemByName((m[0] + m[2] - 1) + ":" + (m[1] + m[3] - 1));
                    a.merge(b);
                } catch (e) {
                    err(ch.id + ": bảng " + (i + 1) + " không gộp được ô " + m.join(",") + ": " + e);
                }
            }
            try {
                t.appliedTableStyle = doc.tableStyles.itemByName(T.table_style);
                t.clearTableStyleOverrides();
            } catch (e) {}
        }
    }

    function flow(doc, frame) {
        var guard = 0;
        frame.parentStory.recompose();
        while (frame.overflows) {
            if (++guard > 3000) { err("Một chương vượt 3000 trang — dừng tự thêm trang."); break; }
            var page = doc.pages.add(LocationOptions.AFTER, frame.parentPage);
            page.appliedMaster = BODY_MASTER;
            var nf = makeFrame(page);
            frame.nextTextFrame = nf;
            nf.parentStory.recompose();
            if (nf.characters.length === 0 && nf.overflows) {
                err("Có đối tượng không vừa khung chữ (ảnh/hàng bảng quá cao?) ở trang " + page.name + ".");
                break;
            }
            frame = nf;
        }
        return frame;
    }

    function placeChapter(doc, ch, idx) {
        var page;
        var fresh = (idx === 0 && doc.pages.length === 1 && doc.pages[0].pageItems.length === 0);
        if (fresh) {
            page = doc.pages[0];
        } else {
            page = doc.pages.add(LocationOptions.AT_END);
            if (T.chapter_start === "recto" && page.side == PageSideOptions.LEFT_HAND) {
                page.appliedMaster = NothingEnum.NOTHING; // trang trắng trước chương mới
                page = doc.pages.add(LocationOptions.AT_END);
            }
        }
        page.appliedMaster = BODY_MASTER;
        var startPage = page.name;
        var frame = makeFrame(page);
        var f = File(JOB_DIR + "/" + ch.icml);
        if (!f.exists) throw new Error("Không có file " + f.fsName);
        frame.place(f);
        unlinkStoryLinks(doc);
        var story = frame.parentStory;
        var nFig = placeFigures(doc, story, ch);
        fixTables(doc, story, ch);
        var last = flow(doc, frame);
        var rec = {
            id: ch.id, title: ch.title, start_page: startPage, end_page: last.parentPage.name,
            figures_expected: ch.figures.length, figures_placed: nFig,
            tables_expected: ch.tables.length, tables_found: story.tables.length,
            footnotes_expected: ch.footnotes, footnotes_found: story.footnotes.length
        };
        if (story.footnotes.length != ch.footnotes) {
            err(ch.id + ": số chú thích chân trang (" + story.footnotes.length + ") khác bản thảo (" + ch.footnotes + ").");
        }
        if (nFig != ch.figures.length) err(ch.id + ": đặt được " + nFig + "/" + ch.figures.length + " hình.");
        LOG.chapters.push(rec);
    }

    // ------------------------------------------------------------------
    // Kiểm tra sau dàn trang
    // ------------------------------------------------------------------
    function checkDocument(doc) {
        for (var i = 0; i < doc.stories.length; i++) {
            if (doc.stories[i].overflows) err("Còn chữ tràn (overset) trong story #" + (i + 1) + " — nội dung bị khuất.");
        }
        resetFind();
        app.findGrepPreferences.findWhat = "##HTLFIG\\d+##";
        var left = doc.findGrep();
        if (left.length) err("Còn " + left.length + " mốc ảnh chưa được thay bằng ảnh.");
        resetFind();
        for (var f = 0; f < doc.fonts.length; f++) {
            var font = doc.fonts[f];
            if (font.status != FontStatus.INSTALLED) err("Thiếu font: " + font.name + " (" + font.status + ")");
        }
        for (var l = 0; l < doc.links.length; l++) {
            var ln = doc.links[l];
            if (ln.status == LinkStatus.LINK_MISSING) err("Mất liên kết ảnh: " + ln.name);
            else if (ln.status == LinkStatus.LINK_OUT_OF_DATE) warn("Ảnh đã thay đổi, cần cập nhật: " + ln.name);
        }
        info("Tổng số trang: " + doc.pages.length + "; số hình đã đặt: " + FIG_COUNT);
        if (doc.pages.length % 4) warn("Số trang " + doc.pages.length + " không chia hết cho 4.");
    }

    // ------------------------------------------------------------------
    // Xuất PDF/X
    // ------------------------------------------------------------------
    function pdfPreset() {
        var P = T.pdf;
        var p = app.pdfExportPresets.itemByName(P.preset_name);
        if (!p.isValid) p = app.pdfExportPresets.add({ name: P.preset_name });
        var x1a = (String(P.standard).toUpperCase() === "PDFX1A");
        if (x1a) {
            trySet(p, "standardsCompliance", PDFXStandards.PDFX1A2001_STANDARD, "chuẩn PDF/X-1a");
            trySet(p, "acrobatCompatibility", AcrobatCompatibility.ACROBAT_4);
        } else {
            var ok = false;
            try { p.standardsCompliance = PDFXStandards.PDFX42010_STANDARD; ok = true; } catch (e) {}
            if (!ok) trySet(p, "standardsCompliance", PDFXStandards.PDFX42008_STANDARD, "chuẩn PDF/X-4");
            trySet(p, "acrobatCompatibility", AcrobatCompatibility.ACROBAT_7);
        }
        // Chất lượng cao nhất: không giảm độ phân giải, nén không mất dữ liệu
        trySet(p, "colorBitmapSampling", Sampling.NONE);
        trySet(p, "grayscaleBitmapSampling", Sampling.NONE);
        trySet(p, "monochromeBitmapSampling", Sampling.NONE);
        trySet(p, "colorBitmapCompression", BitmapCompression.ZIP);
        trySet(p, "grayscaleBitmapCompression", BitmapCompression.ZIP);
        trySet(p, "monochromeBitmapCompression", MonoBitmapCompression.CCIT4);
        trySet(p, "compressTextAndLineArt", true);
        trySet(p, "cropImagesToFrames", true);
        trySet(p, "subsetFontsBelow", 100);
        // Màu: chuyển về điều kiện in, giữ nguyên số CMYK có sẵn (chữ đen 100K không bị tách 4 màu)
        trySet(p, "pdfColorSpace", PDFColorSpace.REPURPOSE_CMYK, "Convert to Destination (Preserve Numbers)");
        trySet(p, "pdfDestinationProfile", T.color.cmyk_profile, "destination profile");
        trySet(p, "pdfXProfile", T.color.cmyk_profile, "output intent profile");
        // Bleed & dấu cắt
        trySet(p, "useDocumentBleedWithPDF", true);
        trySet(p, "cropMarks", !!P.crop_marks);
        trySet(p, "registrationMarks", !!P.registration_marks);
        trySet(p, "pageInformationMarks", !!P.page_information_marks);
        trySet(p, "bleedMarks", false);
        trySet(p, "colorBars", false);
        trySet(p, "pageMarksOffset", P.marks_offset_mm * MM);
        // Không có nội dung tương tác trong file in
        trySet(p, "exportReaderSpreads", false);
        trySet(p, "includeBookmarks", false);
        trySet(p, "includeHyperlinks", false);
        trySet(p, "includeStructure", false);
        trySet(p, "exportLayers", false);
        trySet(p, "exportGuidesAndGrids", false);
        trySet(p, "exportNonprintingObjects", false);
        trySet(p, "generateThumbnails", false);
        trySet(p, "optimizePDF", false);
        trySet(p, "includeSlugWithPDF", false);
        return p;
    }

    // ------------------------------------------------------------------
    function main() {
        var doc = openOrCreate();
        setupColor(doc);
        ensureStyles(doc);
        if (!T.indt) addFolios(doc);
        for (var i = 0; i < JOB.chapters.length; i++) {
            placeChapter(doc, JOB.chapters[i], i);
        }
        checkDocument(doc);
        var outFolder = Folder(JOB_DIR + "/output");
        if (!outFolder.exists) outFolder.create();
        doc.save(File(JOB_DIR + "/" + JOB.output.indd));
        info("Đã lưu " + JOB.output.indd);
        if (LOG.errors.length === 0) {
            doc.exportFile(ExportFormat.PDF_TYPE, File(JOB_DIR + "/" + JOB.output.pdf), false, pdfPreset());
            info("Đã xuất " + JOB.output.pdf);
        } else {
            warn("Có lỗi nên CHƯA xuất PDF. Sửa lỗi (hoặc designer xử lý trong file .indd) rồi xuất bằng preset '" + T.pdf.preset_name + "'.");
            pdfPreset();
        }
    }

    // ------------------------------------------------------------------
    if (JOB.build_errors > 0) {
        if (!confirm("Bước dựng (htl build) báo " + JOB.build_errors + " lỗi — xem report.md.\nVẫn tiếp tục dàn trang?")) return;
    }
    var saved = {
        units: app.scriptPreferences.measurementUnit,
        ui: app.scriptPreferences.userInteractionLevel,
        redraw: app.scriptPreferences.enableRedraw
    };
    app.scriptPreferences.measurementUnit = MeasurementUnits.POINTS;
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    app.scriptPreferences.enableRedraw = false;
    var t0 = new Date().getTime();
    try {
        main();
    } catch (e) {
        err("Lỗi script: " + e + (e.line ? " (dòng " + e.line + ")" : ""));
    } finally {
        app.scriptPreferences.measurementUnit = saved.units;
        app.scriptPreferences.userInteractionLevel = saved.ui;
        app.scriptPreferences.enableRedraw = saved.redraw;
        LOG.seconds = Math.round((new Date().getTime() - t0) / 1000);
        try { writeText(JOB_DIR + "/" + JOB.output.report, toJSON(LOG)); } catch (e2) {}
    }
    var msg = "HTL: xong trong " + LOG.seconds + " giây.\nLỗi: " + LOG.errors.length + " — Cảnh báo: " + LOG.warnings.length;
    for (var i = 0; i < LOG.errors.length && i < 10; i++) msg += "\n• " + LOG.errors[i];
    msg += "\n\nChi tiết: " + JOB.output.report;
    alert(msg);
})();
