# -*- coding: utf-8 -*-
"""界面自检（要能开窗口的环境）：把新用户会走的流程走一遍。

    python selftest_ui.py            # 常规（约 20~40 秒）
    python selftest_ui.py --full     # 额外跑全量离线表覆盖（约 2 分钟）

检查项见 TESTING.md「阶段 2」。窗口会自己起来再关掉，中途不要动它。
⚠️ 不能在打包用的沙箱里跑（沙箱里开不了窗口）。
"""
import argparse
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run  # noqa: E402
import gui  # noqa: E402

if getattr(sys, "stdout", None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  %s %s%s" % ("PASS" if ok else "FAIL", name,
                         ("　— " + detail) if detail else ""))
    return ok


def pump(app, seconds=1.0):
    """跑事件循环（Tk 的 after/防抖/异步推荐都靠它推进）。"""
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            app.update()
        except Exception:                    # noqa: BLE001
            break
        time.sleep(0.02)


def new_app():
    gui.App._pop_to_front = lambda self: None        # 自检时不要抢前台
    gui.messagebox.showerror = lambda *a, **k: print("[showerror]", a)
    app = gui.App()
    pump(app, 1.2)
    return app


# --------------------------------------------------------------- 1. 启动状态
def t_startup(app):
    print("[1] 启动状态（新用户第一眼）")
    ok = check("标题带版本号", "黑冰" in app.title() and "v" in app.title(), app.title())
    ok &= check("首屏已自动算过（表格非空）", len(app.tree_out.get_children()) > 0,
                "%d 行" % len(app.tree_out.get_children()))
    # 状态行要么是"已计算 N 行…"，要么是"⚠ 全飞不到"这句提示
    hint = app.lbl_hint.cget("text")
    ok &= check("状态行给出下一步提示",
                "已计算" in hint or "已重算" in hint or "⚠" in hint, repr(hint))
    ok &= check("字体信息单独成行（没占状态行）", "字体" not in app.lbl_hint.cget("text"),
                repr(app.lbl_font.cget("text")))
    ok &= check("窗口不超过屏幕", app.winfo_height() <= app.winfo_screenheight() - 60,
                "%dx%d（屏 %dx%d）" % (app.winfo_width(), app.winfo_height(),
                                      app.winfo_screenwidth(), app.winfo_screenheight()))
    # 首屏自动算可能还在跑（冷启动要搜路线）——显式算一次再验状态行，避免误判
    app.on_calculate()
    pump(app, 1.0)
    hint2 = app.lbl_hint.cget("text")
    ok &= check("点计算后状态行有反馈",
                "已计算" in hint2 or "已重算" in hint2 or "⚠" in hint2, repr(hint2))
    return ok


# --------------------------------------------------- 2. 键入飞机科技年份刷新
def t_type_tech_year(app):
    print("[2] 键入飞机科技年份 → 参考机型随之变")
    def ref_text():
        return app.lbl_org_rec.cget("text").split("｜")[0]
    seen = []
    for year in (1939, 1941, 1944):
        app.var_tech.set(year)
        pump(app, 1.2)
        seen.append((year, ref_text()))
    ok = check("三次参考机型文本都不同", len({t for _y, t in seen}) == 3,
               " / ".join("%d:%s" % (y, t.replace("参考机型：", "")) for y, t in seen))
    ok &= check("① 的前置清单也重建过（组数 > 0）", len(app.group_vars) > 0,
                "%d 组" % len(app.group_vars))
    return ok


# ------------------------------------------------------- 3. 手动指定对手机型
def t_manual_plane(app):
    print("[3] 手动指定机型 → ② 对手行刷新")
    # 先把当前年份放在 1942（自动口径会挑一架更老的德国机），
    # 再把 1944 的 G-14 key 填进去 —— 这样才能看出"填了到底有没有生效"
    app.var_year.set(1942)
    app.var_rule.set("手动")
    pump(app, 0.6)
    before = app.lbl_enemy.cget("text").split("\n")[0]
    app.var_override.set("me_109_late_fighter_equipment_4")
    pump(app, 1.2)                       # 等 400ms 防抖
    after = app.lbl_enemy.cget("text").split("\n")[0]
    ok = check("对手行跟着变", before != after, "%s → %s" % (before[:34], after[:34]))
    ok &= check("换成了目标机型（G-14 / 86.11）", "G-14" in after and "86.1" in after, after[:60])
    app.var_rule.set("当前年份−1")
    app.var_override.set("")
    app.var_year.set(1944)
    pump(app, 0.6)
    return ok


# ----------------------------------------------------- 4. 默认口径跟随推荐
def t_alloc_follows(app):
    print("[4] 配点口径：没手动选过 → 自动跟随推荐")
    pump(app, 1.5)
    rec = app.lbl_alloc_rec.cget("text")
    current = app.var_alloc_mode.get()
    short = rec.split("推荐：")[-1].split("（")[0]
    ok = check("当前口径 = 推荐口径", short and current.startswith(short),
               "当前「%s」/ %s" % (current, rec))
    # 手动选一次之后就不该再被推荐劫持
    other = [l for _k, l in gui.ALLOC_MODES if not l.startswith(short)][0]
    app.var_alloc_mode.set(other)
    app._on_alloc_mode_picked()
    pump(app, 1.5)
    ok &= check("手动选过之后不被劫持", app.var_alloc_mode.get() == other,
                app.var_alloc_mode.get())
    return ok


# ------------------------------------------------- 5 / 6. 计算后滚动、双击明细
def t_scroll(app):
    print("[5] 点「计算」→ 结果区滚进视野")
    app.canvas.yview_moveto(0.0)
    pump(app, 0.4)
    app.on_calculate(view_result=True)
    pump(app, 1.2)
    y0 = app.canvas.yview()[0]
    vis = app.card_result.winfo_rooty() - app.canvas.winfo_rooty()
    ok = check("视口已下移", y0 > 0, "yview=%.3f" % y0)
    ok &= check("结果区进入可视范围", 0 <= vis < app.canvas.winfo_height(),
                "结果区 top=%d，视口高 %d" % (vis, app.canvas.winfo_height()))
    print("[6] 双击一行 → 明细区滚进视野")
    items = app.tree_out.get_children()
    app.tree_out.selection_set(items[0])
    app._show_design(scroll=True)
    pump(app, 0.6)
    dtop = app.frm_design.winfo_rooty() - app.canvas.winfo_rooty()
    ok &= check("明细区进入可视范围", 0 <= dtop < app.canvas.winfo_height(),
                "明细 top=%d" % dtop)
    ok &= check("明细有内容（推荐改装 + 公式）", len(app.frm_design.winfo_children()) > 3,
                "%d 个块" % len(app.frm_design.winfo_children()))
    return ok


# ---------------------------------------------------------------- 7. 导出
def t_export(app):
    print("[7] 导出 Excel（文件名带国家/年份/用途）")
    app.var_tag.set("苏联")
    pump(app, 0.8)
    app.on_calculate(view_result=False)
    pump(app, 0.8)
    inputs = app._last[0]
    path = run.output_path(inputs)
    if os.path.exists(path):
        os.remove(path)
    app.on_export()
    pump(app, 0.8)
    ok = check("导出文件按新命名生成", os.path.exists(path), os.path.basename(path))
    ok &= check("状态行显示导出结果", "导出" in app.lbl_hint.cget("text"),
                repr(app.lbl_hint.cget("text")))
    if os.path.exists(path):
        os.remove(path)                     # 自检不留垃圾
    return ok


# ------------------------------------------------------------ 8. 记住上次输入
def t_memory():
    print("[8] 记住上次输入 / 重置为默认")
    tmp = os.path.join(tempfile.gettempdir(), "_selftest_ui_last.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    orig = run.last_inputs_path
    run.last_inputs_path = lambda: tmp
    try:
        app = new_app()
        ok = check("干净环境下用示例默认（苏联/1941，科技 1942）",
                   app.var_tag.get() == "苏联" and int(app.var_year.get()) == 1941
                   and int(app.var_tech.get()) == 1942,
                   "%s / %s / 科技 %s" % (app.var_tag.get(), app.var_year.get(),
                                          app.var_tech.get()))
        app.var_tag.set("德国")
        app.var_year.set(1944)
        pump(app, 0.8)
        app._on_close()                      # 关窗 = 记住这次输入
        ok &= check("生成了记忆文件", os.path.exists(tmp), tmp)
        app2 = new_app()
        ok &= check("重开后回到上次输入（德国/1944）",
                    app2.var_tag.get() == "德国" and int(app2.var_year.get()) == 1944,
                    "%s / %s" % (app2.var_tag.get(), app2.var_year.get()))
        app2._reset_to_default()
        pump(app2, 1.2)
        ok &= check("「重置为默认」立刻回到苏联/1941（不用重启）",
                    app2.var_tag.get() == "苏联" and int(app2.var_year.get()) == 1941,
                    "%s / %s" % (app2.var_tag.get(), app2.var_year.get()))
        ok &= check("「重置为默认」清掉了记忆文件", not os.path.exists(tmp))
        app2.destroy()
        return ok
    finally:
        run.last_inputs_path = orig
        if os.path.exists(tmp):
            os.remove(tmp)


# -------------------------------------------------------- 9. 小屏 / 小窗口
def t_small_window(app):
    print("[9] 小窗口（1000x650）仍然可用")
    app.geometry("1000x650")
    pump(app, 0.6)
    total = app.canvas.bbox("all")[3]
    ok = check("内容比视口高 → 靠滚动查看", total > app.canvas.winfo_height(),
               "内容 %d / 视口 %d" % (total, app.canvas.winfo_height()))
    app._scroll_to(app.card_result)
    pump(app, 0.4)
    vis = app.card_result.winfo_rooty() - app.canvas.winfo_rooty()
    ok &= check("滚动后能看到结果区", 0 <= vis < app.canvas.winfo_height(),
                "结果区 top=%d" % vis)
    app.geometry("1280x980")
    pump(app, 0.4)
    return ok


# ------------------------------------------------ 11. 长文本换行（不越界/不留空）
def t_wrapping(app):
    print("[11] 长文本换行：不越界、宽度跟着窗口走")
    labels = (("lbl_enemy_src", "②数值来源"), ("lbl_enemy", "②对手"),
              ("lbl_policy", "④方针说明"), ("lbl_org_rec", "④参考机型"),
              ("lbl_alloc_rec", "④口径推荐"), ("lbl_mio_total", "④累计"),
              ("lbl_prod", "④生产侧"), ("lbl_mio_route", "④路线说明"))
    ok = True
    for size, min_wrap in (("1280x980", 1100), ("1000x650", 850), ("1600x977", 1400)):
        app.geometry(size)
        pump(app, 0.8)
        cw = app.canvas.winfo_width()
        for name, label in labels:
            w = getattr(app, name, None)
            if w is None:
                continue
            right = (w.winfo_rootx() - app.inner.winfo_rootx()) + w.winfo_width()
            ok &= check("%s @%s 不越右缘" % (label, size), right <= cw + 2,
                        "右缘 %d / 画布 %d" % (right, cw))
        wrap = int(float(app.lbl_policy.cget("wraplength") or 0))
        ok &= check("换行宽跟着窗口走（%s → %d px）" % (size, wrap), wrap >= min_wrap,
                    "期望 ≥ %d" % min_wrap)
    ok &= check("② 数值来源按语义分两行",
                app.lbl_enemy_src.cget("text").count("\n") == 1,
                repr(app.lbl_enemy_src.cget("text"))[:60])
    # ④ 方针说明：**不写死换行**，宽的时候要并成一行（窄了才在段与段之间折）
    txt = app.lbl_policy.cget("text")
    ok &= check("④ 方针说明没有写死换行", "\n" not in txt, repr(txt)[:90])
    app.geometry("1600x977")
    pump(app, 0.8)
    ok &= check("④ 方针说明宽屏下并成一行", app.lbl_policy.winfo_height() <= 26,
                "高度 %dpx（单行 ≈21）" % app.lbl_policy.winfo_height())
    # ④ 的行序：军工组织 → 参考机型 → 方针 → 前置/加成/组织
    ys = [(name, getattr(app, attr).winfo_rooty())
          for name, attr in (("军工组织", "cb_org"), ("参考机型", "lbl_org_rec"),
                             ("方针", "cb_policy"), ("前置/加成", "lbl_policy"))]
    ok &= check("④ 行序 = 军工组织→参考机型→方针→前置",
                all(ys[i][1] < ys[i + 1][1] for i in range(len(ys) - 1)),
                " < ".join("%s(y=%d)" % (n, y) for n, y in ys))
    app.geometry("1280x980")
    pump(app, 0.4)
    return ok


# ----------------------------------------------------- 10. 离线表覆盖（抽样）
def t_card4_layout(app):
    """④ 卡片的排版一致性：字段名左对齐 + 行距一致（用户 2026-10-12 反馈）。"""
    print("[12] ④ 排版：字段名对齐 + 行距一致")
    app.geometry("1280x980")
    pump(app, 0.8)
    card = app.lbl_policy.master
    texts = {}
    stack = [card]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            texts[str(w.cget("text"))] = w
        except Exception:                    # noqa: BLE001
            pass
    texts_top = {}
    rows = {}
    for child in card.winfo_children():
        gi = child.grid_info()
        if not gi:
            continue
        r = int(gi["row"])
        rows[r] = min(rows.get(r, 10 ** 6), child.winfo_y())
    xs = [texts[t].winfo_rootx() for t in ("配点方式", "军工组织", "方针", "等级")
          if t in texts]
    ok = check("四个字段名左对齐（同一个 x）", len(xs) == 4 and len(set(xs)) == 1, str(xs))
    # 标签 → 控件 的间距要像 ①② 那样贴在一起（用户 2026-10-12 口径）
    gaps = []
    for rowf in card.winfo_children():
        if rowf.winfo_class() != "TFrame":
            continue
        kids = sorted([c for c in rowf.winfo_children() if c.grid_info()],
                      key=lambda c: int(c.grid_info()["column"]))
        if len(kids) < 2:
            continue
        lab, ctl = kids[0], kids[1]
        if lab.winfo_class() not in ("TLabel", "Label"):
            continue
        if str(lab.cget("text")) not in ("配点方式", "军工组织", "方针", "等级",
                                         "配点口径", "当前效率上限"):
            continue                          # 只量"字段块"，别把表/按钮那些框算进来
        gaps.append(ctl.winfo_x() - (lab.winfo_x() + lab.winfo_width()))
    ok &= check("④ 标签与控件的间距和 ①② 一样（6px）",
                gaps and max(gaps) <= 8 and min(gaps) >= 0, "间距 %s" % gaps)
    # 行距用**单元格**量（grid_bbox）：子控件在不同行高里会被垂直居中，
    # 拿子控件的 y 去比会假抖动 ±3px（实测 35~40），单元格才是真正的排版节奏。
    heights = []
    for r in range(0, 9):
        try:
            _x, _y, _w, h = card.grid_bbox(0, r)
        except Exception:                    # noqa: BLE001
            h = -1
        heights.append(h)
    ok &= check("前 9 行行高完全一致", len(set(heights)) == 1 and heights[0] > 0,
                "行高 %s" % heights)
    # 生产折算那一行必须仍是"一行两对"、且 "%" 紧跟在输入框后面（不能被挤到别的列）
    kids = app.frm_prod.winfo_children()
    prod = [(c.winfo_class(), c.winfo_rootx(), c.winfo_width()) for c in kids]
    rowys = {c.winfo_rooty() for c in kids}
    gaps = [prod[2][1] - (prod[1][1] + prod[1][2]), prod[5][1] - (prod[4][1] + prod[4][2])]
    ok &= check("生产折算是一行两对、% 紧跟输入框", len(rowys) == 1 and max(gaps) <= 6,
                "同一行=%s，%% 间距=%s" % (len(rowys) == 1, gaps))
    # 「生产伙伴」为空时不该占一行（以前"生产侧"和"满级最优路线"之间空一大块）。
    # 兼顾口径下这行一定是空的 —— 正好用来验证"空行被隐藏"。
    app.var_alloc_mode.set(dict(gui.ALLOC_MODES)["balanced"])
    app._alloc_user_picked = True
    app._on_alloc_mode_change()
    pump(app, 1.2)
    gap = app.lbl_mio_route.winfo_y() - (app.lbl_prod.winfo_y() + app.lbl_prod.winfo_height())
    ok &= check("空的生产伙伴不占行（兼顾口径）", not app.lbl_partner.winfo_ismapped()
                and gap <= 24, "间距 %dpx，生产伙伴 %s" % (
                    gap, "可见" if app.lbl_partner.winfo_ismapped() else "已隐藏"))
    return ok


# ----------------------------------------------------- 10. 离线表覆盖（抽样）
def t_style(app):
    """全局视觉规范：卡片不越界、字段名对齐、同类控件同宽、字体/颜色只用规范里的。"""
    print("[13] 视觉规范（字体 / 颜色 / 对齐 / 控件宽度）")
    ok = True
    for size in ("1280x980", "1000x650", "1600x977"):
        app.geometry(size)
        pump(app, 0.8)
        cw = app.canvas.winfo_width()
        worst = []
        for card in app.inner.winfo_children():
            try:
                title = card.cget("text").strip()
            except Exception:                # noqa: BLE001
                continue
            right = 0
            for child in card.winfo_children():
                right = max(right, child.winfo_rootx() - app.inner.winfo_rootx()
                            + child.winfo_width())
            worst.append((title[:5], right))
        bad = [(t, r) for t, r in worst if r > cw + 2]
        ok &= check("所有卡片不越右缘（%s）" % size, not bad,
                    "右缘 %s / 画布 %d" % (", ".join("%s=%d" % (t, r) for t, r in worst), cw))

    # 字段名左对齐：同一个 x
    # 所有"独立成行"的字段名都要在同一条竖线上（② 的五个、④ 的"配点口径"正是
    # 用户 2026-10-12 抓出来的漏检项）
    labels = ("用途", "最远目标距离", "目标距离差",
              "当前年份", "飞机科技年份", "所选国家", "对手国别", "选取规则",
              "配点方式", "军工组织", "方针", "等级", "配点口径",
              "国家精神（逗号分隔，可空）", "合计")
    xs = {}
    fonts, colors = set(), set()
    stack = [app]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            txt = w.cget("text")
            if txt in labels:
                # 字段名的"对齐键" = 从它自己往上到卡片为止，每一层的 grid 列号。
                # ② 的字段挂在各自的块里 → 键 (0,0,0)/(0,1,0)/(0,2,0)；
                # 其它卡片直接挂在卡片上 → 键 (0,)。
                card = w.master
                while card is not None and card.winfo_class() not in ("TLabelframe",
                                                                     "Labelframe"):
                    card = card.master
                key, node = [], w
                while node is not None and node is not card:
                    gi = node.grid_info()
                    key.append(int(gi.get("column", 0)) if gi else 0)
                    node = node.master
                # 分组键里带上**卡片本身**：① 和 ② 都有"(0,1,0)"这样的列链，
                # 不带卡片就会把两张卡的字段名混到一组里比（实测 266 vs 277）
                xs[txt] = (w.winfo_rootx() - app.inner.winfo_rootx(),
                           (str(card), tuple(key)))
        except Exception:                    # noqa: BLE001
            pass
        try:
            f = w.cget("font")
            if f:
                if isinstance(f, str):       # Tk 返回 "{Microsoft YaHei UI} 11 bold" 这种字符串
                    tokens = f.replace("{", " ").replace("}", " ").split()
                    size = next((int(t) for t in tokens if t.lstrip("-").isdigit()), None)
                else:
                    size = int(tuple(f)[1])
                if size:
                    fonts.add(size)
        except Exception:                    # noqa: BLE001
            pass
        for opt in ("foreground", "background"):
            try:
                v = str(w.cget(opt))
            except Exception:                # noqa: BLE001
                continue
            if v.startswith("#"):
                colors.add(v)
    missing = [t for t in labels if t not in xs]
    ok &= check("字段名一个不漏", not missing, "缺 %s" % missing)
    # 版式规矩：同一列（同一条 grid 路径）的字段名首字对齐；最左边那一列固定 x=25
    # （② 是两行并排：第 1 列"当前年份/所选国家"、第 2 列"飞机科技年份/对手国别"、第 3 列"选取规则"）
    groups = {}
    for text, (x, key) in xs.items():
        groups.setdefault(key, set()).add(x)
    ok &= check("同列字段名首字对齐", all(len(v) == 1 for v in groups.values()),
                "各列 x = %s" % {k: sorted(v) for k, v in sorted(groups.items())})
    left_x = min(min(v) for v in groups.values()) if groups else None
    ok &= check("最左一列在 x=25", left_x == 25, "最左 x=%s" % left_x)
    # ttk 控件多数走 style，字体在 style 里 —— 一并核对
    style = gui.ttk.Style(app)
    style_fonts = {}
    for name, expect in (("TLabelframe.Label", gui.FONT_CARD), ("Treeview", gui.FONT_NOTE),
                         ("Treeview.Heading", gui.FONT_CARD)):
        spec = str(style.lookup(name, "font"))
        tokens = spec.replace("{", " ").replace("}", " ").split()
        size = next((int(t) for t in tokens if t.lstrip("-").isdigit()), None)
        style_fonts[name] = (size, expect)
    sizes = sorted(fonts)
    ok &= check("字号只允许规范里的几档", all(s in (gui.FONT_TITLE, gui.FONT_CARD,
                                                 gui.FONT_FIELD, gui.FONT_NOTE) for s in sizes),
                "%d 个控件用到的字号 %s（规范 %s）" % (len(fonts), sizes,
                                              sorted({gui.FONT_TITLE, gui.FONT_CARD,
                                                      gui.FONT_FIELD, gui.FONT_NOTE})))
    ok &= check("样式表字体也合规范",
                all(size == expect for size, expect in style_fonts.values()),
                ", ".join("%s=%s(期望 %s)" % (n, s, e) for n, (s, e) in style_fonts.items()))
    palette = {gui.ACCENT, gui.MUTED, gui.INFO, gui.PROD, gui.INK, gui.DISABLED,
               gui.BANNER_SUB, gui.BANNER_FG, gui.PAGE_BG, gui.CARD_BG, gui.GRID, gui.LINE,
               gui.DOT, "#FFFFFF", "#ffffff"}
    stray = sorted(c for c in colors if c.upper() not in {p.upper() for p in palette})
    ok &= check("颜色只用调色板里的", not stray,
                "扫到 %d 种颜色，越界 %s" % (len(colors), stray))
    widths = (app.cb_org.cget("width"), app.cb_policy.cget("width"),
              app.cb_alloc_mode.cget("width"))
    ok &= check("同类下拉同宽（军工组织/方针/配点口径）", len(set(widths)) == 1, str(widths))
    app.geometry("1280x980")
    pump(app, 0.4)
    return ok


def t_distance_choices(app):
    """最远目标距离的挡位按用途分档（用户口径 2026-10-12）：
    舰载 1500 / 对海（陆基）3000 / 其余 2100；超出上限要自动收到上限。"""
    print("[14] 最远目标距离挡位按用途分档")
    ok = True
    cases = (("air_cv", "对空舰载", 1500), ("naval_cv", "对海舰载", 1500),
             ("naval_far", "对海", 3000), ("air_far", "对空", 2100),
             ("ground_far", "对地", 2100), ("recon", "侦察/运输", 2100))
    for key, label, cap in cases:
        for k, v in app.role_vars.items():
            v.set(k == key)
        app._on_roles_changed()
        pump(app, 0.8)
        vals = list(app.cb_distance.cget("values"))
        ok &= check("%s → 600…%d" % (label, cap),
                    vals[0] == "600" and vals[-1] == str(cap), "挡位 %s…%s（%d 档）"
                    % (vals[0], vals[-1], len(vals)))
    # 超上限自动收回：先在对海把距离拉到 3000，再切回对空 → 应收到 2100
    for k, v in app.role_vars.items():
        v.set(k == "naval_far")
    app._on_roles_changed()
    pump(app, 0.8)
    app.var_distance.set("3000")
    pump(app, 0.6)
    for k, v in app.role_vars.items():
        v.set(k == "air_far")
    app._on_roles_changed()
    pump(app, 0.8)
    ok &= check("超出上限自动收到 2100", int(float(app.var_distance.get())) == 2100,
                app.var_distance.get())
    return ok


def t_table_coverage(full=False):
    print("[10] 离线表覆盖（方案键命中率）")
    app = new_app()
    misses = []
    orig = app._lookup_plan

    def counting(dkey):
        rec = orig(dkey)
        if rec is None:
            misses.append(dkey)
        return rec

    app._lookup_plan = counting
    years = range(1939, 1949) if full else (1939, 1943, 1947)
    techs = range(1939, 1949) if full else (1939, 1944, 1948)
    groups = 0
    # 2026-10-12：算法版本升到 v7 后按用户口径**只重跑了苏德**，
    # 其余四国的分片还是 v6 键（用起来会现算并写进本机缓存，结果一样、就是慢一点）。
    # 所以这里对苏德严格断言 0 缺失，其余国家只报告缺失数（不当失败）。
    strict = ("SOV", "GER")
    misses_by_country = {}
    for country in ("SOV", "GER", "USA", "Commonwealth", "JAP", "ITA"):
        misses_by_country[country] = len(misses)
        label = app._tag_labels.get(country)
        if not label:
            continue
        app.var_tag.set(label)
        app._refresh_country()
        for role in ("air_far", "air_cv"):
            for k, v in app.role_vars.items():
                v.set(k == role)
            app._on_roles_changed()
            app.var_enemy_tag.set(app._tag_labels.get("GER" if country != "GER" else "SOV", ""))
            app._on_enemy_change()
            for ty in techs:
                app.var_tech.set(ty)
                app._on_tech_year_changed()
                for y in years:
                    app.var_year.set(y)
                    app._build_tech_checks()
                    for alloc in ("split", "balanced"):
                        app.var_alloc_mode.set(dict(gui.ALLOC_MODES)[alloc])
                        app._alloc_user_picked = True       # 别让自动跟随推荐改掉口径
                        job = getattr(app, "_plan_job", None)
                        if job:
                            app.after_cancel(job)
                            app._plan_job = None
                        inputs = app.collect()
                        for org in app._air_orgs()[0]:
                            app._org_plan(org, inputs)
                        groups += 1
    app.destroy()
    strict_miss = sum(1 for m in misses if m.split("|")[3] in strict)
    other = len(misses) - strict_miss
    ok = check("离线表命中：苏德缺 %d 个" % strict_miss, strict_miss == 0,
               "走了 %d 组%s；其余四国缺 %d 个（分片还是 v6 键，运行时现算+本机缓存）"
               % (groups, "（全量）" if full else "（抽样）", other))
    for m in misses[:3]:
        print("     缺：%s" % m[:130])
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    app = new_app()
    t_startup(app)
    t_type_tech_year(app)
    t_manual_plane(app)
    t_alloc_follows(app)
    t_scroll(app)
    t_export(app)
    t_small_window(app)
    t_wrapping(app)
    t_card4_layout(app)
    t_style(app)
    t_distance_choices(app)
    app.destroy()
    t_memory()
    t_table_coverage(args.full)
    bad = [n for n, ok, _d in RESULTS if not ok]
    print("\n合计 %d 项，失败 %d 项，用时 %.1fs" % (len(RESULTS), len(bad), time.time() - t0))
    if bad:
        print("失败：" + "；".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
