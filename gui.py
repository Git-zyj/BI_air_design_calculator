#!/usr/bin/env python3
r"""BI_SOV 飞机选型 —— 图形界面（B4）

    bash gui.sh          # 推荐：bisov 环境（Tk 带 Xft），中文显示微软雅黑
    python gui.py        # base 环境也能跑；若当前 Python 的 Tk 不支持 TrueType 中文，
                         # 会自动切换到 bisov 环境重开

① 用途 ② 年份 ③ 当前国家与主要对手 ④ 军工组织加成 ⑤ 国家精神加成
⑥ 总体累计（二选一） ⑦ 最终结果展示。
用途放最前，因为它决定国家精神按哪个装备类别识别。
界面只收集输入，计算与写表复用 run.py。

字体依赖见 PLAN.md §11；标题栏右侧显示实际选中的字体族名，便于自检。
"""

import json
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402
import run  # noqa: E402

# ---------- 外观常量（换字体只改 FONT_PREFS 顺序） ----------
FONT_PREFS = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Noto Sans CJK SC",
              "Source Han Sans SC", "WenQuanYi Micro Hei", "Droid Sans Fallback",
              "FangSong", "仿宋", "SimSun", "Times New Roman", "DejaVu Sans"]
# 出现其中任一，说明 Tk 真的能渲染 TTF 中文（= 链接了 Xft 且装了 CJK 字体）；
# 否则就是退回 X 核心位图字体（WSLg 下只有仿宋体），中文会变成仿宋。
CJK_OK_FONTS = {"Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Noto Sans CJK SC",
                "Source Han Sans SC", "WenQuanYi Micro Hei", "Droid Sans Fallback"}
BISOV_PY = os.path.expanduser("~/miniconda3/envs/bisov/bin/python")
REEXEC_ENV = "BI_SOV_REEXEC"

BODY = 11
PADX, PADY = 12, 8
ACCENT = "#1F4E79"
CARD_BG = "#F7F7F7"
WRAP_RESERVE = 110         # 累计标签换行时给按钮/边距留的宽度

ROLE_LABELS = engine.ROLES
MOD_ZH = {
    "air_attack": "对空攻击", "air_defence": "空中防御", "air_agility": "机动",
    "maximum_speed": "最大速度", "reliability": "可靠性", "build_cost_ic": "造价",
    "air_range": "航程", "air_ground_attack": "对地攻击",
    "naval_strike_attack": "对海攻击", "naval_strike_targetting": "对海瞄准",
    # 原版简中 modifiers 文件里没有条目的，手工补齐（能出现在本工具界面上的）
    "air_bombing": "对地轰炸", "reliability_factor": "可靠性",
    "fuel_consumption_factor": "燃料消耗", "fuel_consumption": "燃料消耗",
    "production_cost_factor": "生产产出花费", "production_capacity_factor": "生产能力",
    "naval_range": "海军航程", "naval_speed": "海军速度",
    "naval_weather_penalty_factor": "海军天气惩罚",
    "military_industrial_organization_research_bonus": "军工组织研究加成",
    "military_industrial_organization_funds_gain": "军工组织资金获取",
}
MOD_FIELDS = [("air_attack", "对空"), ("air_defence", "防御"), ("air_agility", "机动"),
              ("maximum_speed", "速度"), ("reliability", "可靠"), ("build_cost_ic", "造价"),
              ("air_range", "航程"), ("air_ground_attack", "对地"),
              ("naval_strike_attack", "对海"), ("naval_strike_targetting", "瞄准")]
# 对手规则：界面用中文，内部映射到引擎取值
RULE_LABELS = [("当前年份−1", "previous_year"), ("当前年份", "same_year"), ("手动", "manual")]
# 距离目标（= 航程上限）：600 起，每 300 一档，最高 3600；默认 900
DISTANCES = list(range(600, 3601, 300))
DEFAULT_DISTANCE = 900
# 自动配点的口径：
#   design   只按设计分挑路线（生产侧顺带拿到的算白赚）
#   balanced 兼顾：同一条路线里最大化"折算后总分数"（生产特质与设计链并存）
#   split    设计 / 生产分离：本 MIO 只做设计，生产交给另一家 MIO（界面会列出那家与它的特质）
ALLOC_MODES = [("split", "分离（设计最优 + 生产另算）"),
               ("balanced", "兼顾（同一 MIO 一条路线）")]
# 「分离」= 本 MIO 走**设计最优路线**，生产取"本 MIO 这条路线顺带的"与"另一家 MIO 只求产量"
# 里更好的那个 —— 所以它把原来的「设计最优」并了进来（没有更优的生产家时就是这个行为）。
# 生产侧修正的中文名（按游戏官方汉化：production_capacity_factor = **产量**）
# 注意区分两个词：**产量**是修正名（= production_capacity_factor）；
#                  **产能**是折算出来的等效产出倍率（"⇒ 产能 ×1.0167"）。
PROD_ZH = {"production_capacity_factor": "产量",
           "production_cost_factor": "生产产出花费",
           "production_efficiency_cap_factor": "生产效率上限",
           "production_efficiency_gain_factor": "生产效率增长",
           "production_resource_need_factor": "生产资源需求",
           "production_resource_penalty_factor": "生产资源惩罚",
           "production_conversion_speed_factor": "生产转换速度",
           # 生产侧"可靠"与设计侧同效（都是百分比修正装备当前可靠性）→ 已并进有效造价
           "reliability": "可靠性"}
# 明细行里"设计数值"要展示的属性（顺序即显示顺序）
DESIGN_SHOW = ("air_attack", "air_defence", "air_agility", "maximum_speed", "air_range",
               "reliability", "build_cost_ic", "air_ground_attack",
               "naval_strike_attack", "naval_strike_targetting")
# 任务类型：不分远近，统一走各自的"远"口径
ROLE_CHOICES = [("air_far", "对空"), ("ground_far", "对地"),
                ("naval_far", "对海"), ("recon", "侦察/运输"),
                ("air_cv", "对空（舰载）"), ("naval_cv", "对海（舰载）")]
ROLE_SHORT = dict(ROLE_CHOICES)
# 界面上的国家显示名：优先用这个覆盖，其次查汉化，最后退回 tag。
# （原版简中把 SOV 写成"俄罗斯"，BIX 里是苏联；ENG/CHI 汉化里没有条目）
COUNTRY_ZH_OVERRIDE = {"SOV": "苏联", "ENG": "英国", "CHI": "中国", "Commonwealth": "英联邦"}
_UNSET = object()          # collect(policy=...) 的"未指定"哨兵（None 表示明确不选方针）
# 帕累托图可选轴：界面用中文，内部映射到 run.AXIS_DEFS
AXIS_CHOICES = [("effect", "性能分数"), ("score", "总分数（性能/造价）"),
                ("cost", "有效造价（IC）"), ("year", "年份")]
AXIS_LABELS = dict(AXIS_CHOICES)


def load_loc():
    path = os.path.join(engine.DATA_DIR, "loc_zh.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def zh(loc, key, depth=0):
    if not key:
        return ""
    val = loc.get(key) or key
    if depth < 3 and isinstance(val, str) and val.startswith("$") and val.endswith("$"):
        return zh(loc, val.strip("$"), depth + 1)
    return val


_ZH_LOC = {}          # 由 App 初始化时填 loc_zh，供 fmt_mods 兜底查修正名


def fmt_mods(mods, loc=None):
    if not mods:
        return "—"
    base = _ZH_LOC if loc is None else loc

    def name(key):
        return MOD_ZH.get(key) or zh(base, key) or key
    return "，".join("%s %+.2f%%" % (name(k), v * 100)
                     for k, v in sorted(mods.items()) if v)


def _tk_has_cjk_font():
    root = tk.Tk()
    root.withdraw()
    try:
        return any(name in set(tkfont.families()) for name in CJK_OK_FONTS)
    finally:
        root.destroy()


def _maybe_reexec():
    """base 环境的 Tk 没链接 libXft，中文只能是仿宋位图；自动切到 bisov 环境重开。"""
    if os.name == "nt":
        return          # Windows 原生 Tk 本来就支持 TrueType 中文，不需要切环境
    if os.environ.get(REEXEC_ENV) == "1":
        return
    try:
        if _tk_has_cjk_font():
            return
    except tk.TclError:
        return
    if not os.path.exists(BISOV_PY):
        return
    if os.path.realpath(sys.executable) == os.path.realpath(BISOV_PY):
        return
    os.environ[REEXEC_ENV] = "1"
    if getattr(sys, "stdout", None) is not None:
        print("当前 Python 的 Tk 不支持 TrueType 中文（会退回仿宋位图），自动切换到：%s" % BISOV_PY)
        sys.stdout.flush()
    os.execv(BISOV_PY, [BISOV_PY, os.path.abspath(__file__)] + sys.argv[1:])


def _say(text):
    """启动阶段提示（打印到终端，方便"窗口没弹出来"时定位卡在哪一步）。"""
    if getattr(sys, "stdout", None) is None:
        return          # 打包成 --windowed 的 exe 时没有控制台
    print("[BI_SOV] %s" % text)
    sys.stdout.flush()


DEBUG = bool(getattr(sys, "stdout", None)) or ("-v" in sys.argv)


def _dbg(text):
    """调试信息：只有带控制台（调试版 exe / 命令行）时才打印，发行版静默。"""
    if DEBUG and getattr(sys, "stdout", None) is not None:
        print("[DEBUG] %s" % text)
        sys.stdout.flush()


class App(tk.Tk):
    def __init__(self):
        global _ZH_LOC
        super().__init__()
        available = set(tkfont.families())
        picked = next((n for n in FONT_PREFS if n in available), None)
        self.font_ok = picked in CJK_OK_FONTS
        self.family = picked or tkfont.nametofont("TkDefaultFont").actual("family")
        self._apply_style()
        self.title("BI_SOV 飞机选型")
        # 给一个明确坐标，避免窗口被放到可视区之外（WSLg 偶尔会这样）
        self.geometry("1280x980+60+40")
        self.data = engine.load_data()
        self.by_name = {o["organization"]: o for o in self.data["mio"]}
        self.loc = load_loc()
        _ZH_LOC = self.loc          # fmt_mods 用它兜底查修正名
        self.inputs = dict(run.DEFAULT_INPUTS)
        if os.path.exists(run.INPUTS):
            with open(run.INPUTS, encoding="utf-8") as fh:
                self.inputs.update(json.load(fh))
        self.tags = sorted({a.get("country") for a in self.data["airframes_all"] if a.get("country")})
        self._tag_labels = {t: self._country_label(t) for t in self.tags}
        self._label_to_tag = {v: k for k, v in self._tag_labels.items()}
        self.chosen_traits = set()
        self.rows = []
        self._sort_key, self._sort_desc = "pure", True      # 默认按总分数从高到低
        self._plans = {}             # 满级+方针的配点路线缓存（供推荐与展示只读）
        # 离线表（随包发布）+ 本机缓存（新算的写这里），键相同
        self._plan_table = {}        # 离线表按 (国家, 用途) 分片，用到哪片读哪片
        self._plan_runtime = run.load_plan_cache()
        self._plan_cache_saved = len(self._plan_runtime)
        self._org_keys = {}          # 中文显示名 → MIO key
        self._build()
        _say("界面构建完成，正在计算推荐…")
        self._refresh_country()
        self._sync_alloc()
        self._sync_source()
        self._sync_rule()
        self._refresh_enemy()
        self._refresh_totals()
        self._watch_inputs()          # 调试：输入项一变就打一行日志
        self._bind_live_refresh()     # 年份直接键入时也要重算 ② 的对手
        _say("准备就绪，正在显示窗口…")
        self.after(80, self._pop_to_front)

    def _pop_to_front(self):
        """把窗口顶到最前——WSLg 开的新窗口常常落在其它窗口后面，看起来像"没弹出来"。"""
        try:
            self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
            self.focus_force()
            _say("窗口已显示（标题：BI_SOV 飞机选型）。若仍看不到，检查是否有窗口挡在前面；"
                 "或执行 wsl --shutdown 后重开 WSL 再试。")
        except tk.TclError:
            pass

    # ---------- 外观 ----------
    def _apply_style(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family=self.family, size=BODY)
            except tk.TclError:
                pass
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(self.family, BODY), background=CARD_BG)
        style.configure("TLabelframe", background=CARD_BG, bordercolor="#D0D7E5",
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=CARD_BG, foreground=ACCENT,
                        font=(self.family, BODY, "bold"))
        style.configure("TButton", padding=(10, 5))
        style.configure("Treeview", rowheight=24, font=(self.family, BODY - 1), background="white")
        style.configure("Treeview.Heading", font=(self.family, BODY - 1, "bold"))
        self.configure(background="#EDF1F7")

    def _card(self, row, title, **kw):
        box = ttk.LabelFrame(self.inner, text=" " + title + " ")
        box.grid(row=row, column=0, sticky="ew", padx=PADX, pady=(PADY, 2), **kw)
        return box

    def _bind_wheel(self):
        """整页滚动：鼠标在结果表上时不抢滚轮（交给表格自己滚）。"""
        def scroll(units):
            self.canvas.yview_scroll(units, "units")

        def on_wheel(event):
            if isinstance(event.widget, ttk.Treeview):
                return
            scroll(-1 if event.delta > 0 else 1)

        def on_up(event):
            if not isinstance(event.widget, ttk.Treeview):
                scroll(-1)

        def on_down(event):
            if not isinstance(event.widget, ttk.Treeview):
                scroll(1)

        self.canvas.bind_all("<MouseWheel>", on_wheel)   # Windows / macOS
        self.canvas.bind_all("<Button-4>", on_up)        # X11 向上
        self.canvas.bind_all("<Button-5>", on_down)      # X11 向下

    def _wrap_to_card(self, label, container):
        """让长标签按**画布实际可用宽度**换行（不是按卡片自己的宽度）。

        ⚠️ 别用 event.width（卡片宽度）：长文本会把卡片撑宽，卡片一宽 wraplength 又变大，
        两者互相追着涨，最后整张卡片比窗口还宽、右边直接被画布裁掉——雅科夫列夫满级
        （十几个修正）就是被这个坑撑爆的。这里改成：
            画布可见宽度 − 标签在画布里的横向起点 − 预留
        """
        def abs_x(widget):
            """标签在画布内层里的横向起点（可能嵌在子 Frame 里，要逐级往上加）。"""
            x, node = 0, widget
            while node is not None and node is not self.inner:
                try:
                    x += node.winfo_x()
                    node = node.master
                except Exception:                # noqa: BLE001
                    break
            return x

        def on_conf(_event=None):
            avail = self.canvas.winfo_width()
            if avail <= 1:                       # 还没完成布局
                avail = max(self.winfo_width() - 2 * PADX, 640)
            try:
                x = abs_x(label)
            except Exception:                    # noqa: BLE001
                x = 0
            width = int(max(avail - x - WRAP_RESERVE, 240))
            try:
                cur = int(float(label.cget("wraplength") or 0))
            except (TypeError, ValueError):
                cur = -1
            if cur != width:
                label.configure(wraplength=width)

        # 容器只绑一次（否则每次重建明细都会往同一个容器上叠一个回调）
        if not getattr(container, "_wrap_bound", False):
            container.bind("<Configure>", on_conf, add="+")
            container._wrap_bound = True
        label.bind("<Configure>", on_conf, add="+")
        on_conf()

    # ---------- 界面 ----------
    def _build(self):
        self.columnconfigure(0, weight=1)
        banner = tk.Frame(self, background=ACCENT)
        banner.grid(row=0, column=0, sticky="ew")
        tk.Label(banner, text="BI_SOV 飞机选型", background=ACCENT, foreground="white",
                 font=(self.family, BODY + 4, "bold"), padx=PADX, pady=5).pack(side="left")
        hint = "字体：%s" % self.family
        if not self.font_ok:
            hint += "（当前 Tk 不支持 TTF 中文，请用 gui.sh 启动）"
        self.lbl_hint = tk.Label(banner, text=hint, background=ACCENT, foreground="#C9D8EC",
                                 font=(self.family, BODY - 1), padx=PADX)
        self.lbl_hint.pack(side="right")

        # 整页可上下滚动（卡片多、屏幕矮时不至于看不到底部）
        outer = tk.Frame(self, background="#EDF1F7")
        outer.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)
        self.canvas = tk.Canvas(outer, background="#EDF1F7", highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._inner_id, width=e.width))
        self._bind_wheel()
        row = 1

        # ① 用途（放最前：它决定国家精神按哪个装备类别识别）
        box = self._card(row, "① 用途")
        self.role_vars = {}
        cur_roles = self.inputs.get("roles") or ["air_far"]
        ttk.Label(box, text="用途").grid(row=0, column=0, sticky="e", padx=(PADX, 4), pady=PADY)
        # 六个勾选框放进自己的子框：以前直接排在 box 的第 1..6 列，正好和"距离目标"
        # 那一列撞车 —— 对空（舰载）被标签压掉半截、对海（舰载）被下拉框整个盖住，
        # 看上去就像"有两个对空、少了一个对海"。子框之后，它们不可能再互相覆盖。
        roles_bar = ttk.Frame(box)
        roles_bar.grid(row=0, column=1, sticky="w", pady=PADY)
        for key, label in ROLE_CHOICES:
            v = tk.BooleanVar(value=key in cur_roles)
            self.role_vars[key] = v
            ttk.Checkbutton(roles_bar, text=label, variable=v,
                            command=self._on_roles_changed).pack(side="left", padx=(0, PADX))
        ttk.Label(box, text="距离目标").grid(row=0, column=2, sticky="e", padx=(PADX * 2, 4))
        self.var_distance = tk.StringVar(
            value=str(int(self.inputs.get("range_cap") or DEFAULT_DISTANCE)))
        dbox = ttk.Combobox(box, textvariable=self.var_distance, width=8, state="readonly",
                            values=DISTANCES)
        dbox.grid(row=0, column=3, sticky="w")
        dbox.bind("<<ComboboxSelected>>", lambda e: self._on_inputs_affecting_plan())
        ttk.Label(box, text="（= 航程上限，600 起每 300 一档）").grid(row=0, column=4, sticky="w")
        row += 1

        # ② 年份 + 所选国家与主要对手（先定国家和年份，后面才谈前置科技）
        box = self._card(row, "② 年份 + 所选国家与主要对手")
        # 上半段（年份/国家/对手/规则）单独放一个子框：整张卡片只有一列，
        # 下面那些**长文本行**就不会把这里的列宽撑开、把前两行整体推右。
        # （以前 4 行共用一套 grid 列，换对手时说明文字一变长，前几行就跟着位移。）
        fields = ttk.Frame(box)
        fields.grid(row=0, column=0, sticky="w")
        self.frm_fields = fields          # 供后续核对布局（前两行的列宽只看它自己）
        self.var_year = tk.IntVar(value=self.inputs["current_year"])
        self.var_tech = tk.IntVar(value=self.inputs["tech_year"])
        ttk.Label(fields, text="当前年份").grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
        ttk.Spinbox(fields, from_=1936, to=1948, textvariable=self.var_year, width=6,
                    command=self._refresh_enemy).grid(row=0, column=1, sticky="w")
        ttk.Label(fields, text="（决定对手机型）").grid(row=0, column=2, sticky="w")
        ttk.Label(fields, text="飞机科技年份").grid(row=0, column=3, sticky="e", padx=PADX)
        ttk.Spinbox(fields, from_=1936, to=1948, textvariable=self.var_tech, width=6,
                    command=self._on_tech_year_changed).grid(row=0, column=4, sticky="w")
        ttk.Label(fields, text="（决定我方可用机身，可超前研究）").grid(row=0, column=5, sticky="w")

        ttk.Label(fields, text="所选国家 tag").grid(row=1, column=0, sticky="e",
                                               padx=(PADX, 4), pady=PADY)
        self.var_tag = tk.StringVar(value=self.inputs.get("country") or "SOV")
        cb = ttk.Combobox(fields, textvariable=self.var_tag, width=10,
                          state="readonly")
        cb.grid(row=1, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_country())
        cb.configure(values=[self._tag_labels[t] for t in self.tags])
        self.var_tag.set(self._tag_labels.get(self.inputs.get("country") or "SOV", "苏联"))
        ttk.Label(fields, text="对手国别").grid(row=1, column=2, sticky="e", padx=(PADX, 4))
        enemy = self.inputs.get("enemy") or {}
        self.var_enemy_tag = tk.StringVar(value=enemy.get("country", "GER"))
        eb = ttk.Combobox(fields, textvariable=self.var_enemy_tag, width=10,
                          state="readonly")
        eb.grid(row=1, column=3, sticky="w")
        eb.bind("<<ComboboxSelected>>", lambda e: self._on_enemy_change())
        eb.configure(values=[self._tag_labels[t] for t in self.tags])
        self.var_enemy_tag.set(self._tag_labels.get(enemy.get("country", "GER"), "德国"))
        ttk.Label(fields, text="选取规则").grid(row=1, column=4, sticky="e", padx=(PADX, 4))
        cur_rule = dict(RULE_LABELS).get(enemy.get("rule", "previous_year"), "当前年份−1")
        self.var_rule = tk.StringVar(value=cur_rule)
        rb = ttk.Combobox(fields, textvariable=self.var_rule, values=[l for l, _ in RULE_LABELS],
                          width=12, state="readonly")
        rb.grid(row=1, column=5, sticky="w")
        rb.bind("<<ComboboxSelected>>", lambda e: self._on_rule_change())

        self.frm_manual_plane = ttk.Frame(box)
        self.frm_manual_plane.grid(row=3, column=0, sticky="w")
        ttk.Label(self.frm_manual_plane, text="手动指定机型 key").grid(row=0, column=0, sticky="e",
                                                                      padx=(PADX, 4))
        self.var_override = tk.StringVar(value=enemy.get("override_key") or "")
        ov = ttk.Entry(self.frm_manual_plane, textvariable=self.var_override, width=46)
        ov.grid(row=0, column=1, sticky="w")
        ov.bind("<FocusOut>", lambda e: self._on_enemy_change())

        # 对手（AI）的「设计商修正 + 满经验」：默认按模组 ai_bonus_weights 自动判定
        # （该国 AI 会挑哪家 MIO、点哪些特质），也可在这里手填覆盖
        # （手填值存 inputs.enemy.by_country[该国]，优先于自动判定）。
        # 以前这套值是写死的德国（阿拉多）数值，换成苏联当对手也照样套，分数自然不对。
        self.frm_enemy_mods = ttk.Frame(box)
        self.frm_enemy_mods.grid(row=2, column=0, sticky="w")
        ttk.Label(self.frm_enemy_mods, text="对手设计商加成（机动/速度，%）").grid(
            row=0, column=0, sticky="e", padx=(PADX, 4))
        self.var_enemy_mod_agi = tk.StringVar()
        self.var_enemy_mod_spd = tk.StringVar()
        ttk.Entry(self.frm_enemy_mods, textvariable=self.var_enemy_mod_agi, width=6,
                  justify="right").grid(row=0, column=1, sticky="w")
        ttk.Entry(self.frm_enemy_mods, textvariable=self.var_enemy_mod_spd, width=6,
                  justify="right").grid(row=0, column=2, sticky="w", padx=(2, PADX))
        ttk.Label(self.frm_enemy_mods, text="对手联队经验加成（机动/速度，%）").grid(
            row=0, column=3, sticky="e", padx=(PADX, 4))
        self.var_enemy_exp_agi = tk.StringVar()
        self.var_enemy_exp_spd = tk.StringVar()
        ttk.Entry(self.frm_enemy_mods, textvariable=self.var_enemy_exp_agi, width=6,
                  justify="right").grid(row=0, column=4, sticky="w")
        ttk.Entry(self.frm_enemy_mods, textvariable=self.var_enemy_exp_spd, width=6,
                  justify="right").grid(row=0, column=5, sticky="w", padx=(2, 4))
        ttk.Button(self.frm_enemy_mods, text="恢复 AI 自动值",
                   command=self._reset_enemy_mods).grid(row=0, column=6, sticky="w", padx=PADX)
        self.lbl_enemy_src = ttk.Label(self.frm_enemy_mods, text="", foreground="#44506B")
        self.lbl_enemy_src.grid(row=1, column=0, columnspan=7, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_enemy_src, self.frm_enemy_mods)

        self.lbl_enemy = ttk.Label(box, text="", foreground=ACCENT, font=(self.family, BODY, "bold"))
        self.lbl_enemy.grid(row=4, column=0, sticky="w", padx=PADX, pady=(0, PADY))
        self._wrap_to_card(self.lbl_enemy, box)
        row += 1

        # ③ 改装/方针的前置条件（不看"有什么科技"，只看"条件满没满足"）
        box = self._card(row, "③ 改装 / 方针 / 特质的前置（勾选 = 条件已满足）")
        self.frm_tech = ttk.Frame(box)
        self.frm_tech.grid(row=0, column=0, sticky="w", padx=PADX, pady=(PADY, 2))
        self.tech_vars = {}
        self.flag_vars = {}
        self._build_tech_checks()
        ttk.Label(box, text="（勾上某组 = 这一组前置全部满足，对应改装/方针即可使用；"
                            "只列当前国家用得到的）").grid(
            row=1, column=0, sticky="w", padx=PADX, pady=(0, PADY))
        row += 1

        # ④ 军工组织加成
        card = self._card(row, "④ 军工组织加成")
        self.var_alloc = tk.StringVar(value="auto")
        ttk.Label(card, text="配点方式").grid(row=0, column=0, sticky="e", padx=(PADX, 4), pady=PADY)
        ttk.Radiobutton(card, text="自动配点（按等级）", variable=self.var_alloc,
                        value="auto", command=self._sync_alloc).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(card, text="手动勾选特质", variable=self.var_alloc,
                        value="pick", command=self._sync_alloc).grid(row=0, column=2, sticky="w",
                                                                     padx=PADX)
        self.lbl_org_rec = ttk.Label(card, text="", foreground=ACCENT,
                                     font=(self.family, BODY - 1, "bold"), justify="left")
        self.lbl_org_rec.grid(row=0, column=3, columnspan=3, sticky="w", padx=PADX)

        mio = self.inputs.get("mio") or {}
        self.var_org = tk.StringVar(value="")
        self.var_level = tk.IntVar(value=mio.get("level") or 5)
        ttk.Label(card, text="军工组织").grid(row=1, column=0, sticky="e", padx=(PADX, 4), pady=4)
        self.cb_org = ttk.Combobox(card, textvariable=self.var_org, width=22, state="readonly")
        self.cb_org.grid(row=1, column=1, sticky="w")
        self.cb_org.bind("<<ComboboxSelected>>", lambda e: self._on_org_change())
        ttk.Label(card, text="方针").grid(row=1, column=2, sticky="e", padx=(PADX, 4))
        self.var_policy = tk.StringVar(value="（不选）")
        self.cb_policy = ttk.Combobox(card, textvariable=self.var_policy, width=26, state="readonly")
        self.cb_policy.grid(row=1, column=3, sticky="w")
        self.cb_policy.bind("<<ComboboxSelected>>", lambda e: self._on_policy_change())
        self.lbl_policy = ttk.Label(card, text="", foreground="#5A6472",
                                    font=(self.family, BODY - 2), justify="left")
        self.lbl_policy.grid(row=1, column=4, columnspan=2, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_policy, card)

        # 第 2 行：等级 + 预览按钮
        ttk.Label(card, text="等级").grid(row=2, column=0, sticky="e", padx=(PADX, 4))
        self.spin_level = ttk.Spinbox(card, from_=0, to=14, textvariable=self.var_level, width=6,
                                      command=self._on_level_changed)
        self.spin_level.grid(row=2, column=1, sticky="w")
        ttk.Button(card, text="预览军工组织总加成", command=self.on_preview).grid(
            row=2, column=2, sticky="w", padx=(PADX, 2))
        # 「配点口径 + 推荐」放进一个子框：推荐紧跟在选择框右边，
        # 又不会被卡片左边那几列的宽度变化推着跑（以前塞主网格里就会漂）。
        frm_alloc = ttk.Frame(card)
        frm_alloc.grid(row=2, column=3, columnspan=3, sticky="w")
        ttk.Label(frm_alloc, text="配点口径").grid(row=0, column=0, sticky="e", padx=(PADX, 4))
        self.var_alloc_mode = tk.StringVar(value=ALLOC_MODES[0][1])
        self.cb_alloc_mode = ttk.Combobox(frm_alloc, textvariable=self.var_alloc_mode, width=24,
                                          state="readonly",
                                          values=[label for _k, label in ALLOC_MODES])
        self.cb_alloc_mode.grid(row=0, column=1, sticky="w")
        self.cb_alloc_mode.bind("<<ComboboxSelected>>", lambda e: self._on_alloc_mode_change())
        self.lbl_alloc_rec = ttk.Label(frm_alloc, text="", foreground=ACCENT,
                                       font=(self.family, BODY - 2, "bold"), justify="left")
        self.lbl_alloc_rec.grid(row=0, column=2, sticky="w", padx=PADX)

        # 第 3 行：累计加成单独占一整行——满级十几项修正，挤在右边就会被卡片裁掉
        self.lbl_mio_total = ttk.Label(card, text="", foreground=ACCENT,
                                       font=(self.family, BODY, "bold"), justify="left")
        self.lbl_mio_total.grid(row=4, column=0, columnspan=6, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_mio_total, card)

        # 生产侧（**不参与评分**）：设计槽吃 equipment_bonus，生产槽吃 production_bonus，
        # 但一个 MIO 只有一条特质路线 —— 所以这里把这条路线带来的生产修正如实列出来，
        # 供用户定性判断"值不值得为了生产改路线 / 换一个 MIO 来生产"。
        # 生产折算用的"当前堆叠"——同一个 +5%，在上限 100 和 200 上值多少完全不同。
        # （原来这里还有个"生产折算"标题标签，挪行后和累计行撞在一起，已删；
        #   两个输入各自有"当前效率上限 / 当前产量加成"标签，够清楚。）
        # 列宽一变 "%" 就飘到离输入框很远的地方）
        prod_row = ttk.Frame(card)
        prod_row.grid(row=5, column=0, columnspan=6, sticky="w", padx=PADX, pady=(PADY, 0))
        self.frm_prod = prod_row          # 供布局核对（每个字段自带 %）
        self.var_capacity = tk.IntVar(value=int(self.inputs.get("capacity_bonus_now") or 200))
        self.var_cap = tk.IntVar(value=int(self.inputs.get("efficiency_cap_now") or 100))
        for col, (text, var, lo, hi) in enumerate((
                ("当前效率上限", self.var_cap, 1, 500),
                ("当前产量加成", self.var_capacity, 0, 2000))):
            ttk.Label(prod_row, text=text).grid(row=0, column=col * 3, sticky="e",
                                                padx=(0 if col == 0 else PADX, 4))
            ttk.Spinbox(prod_row, from_=lo, to=hi, textvariable=var, width=5).grid(
                row=0, column=col * 3 + 1, sticky="w")
            ttk.Label(prod_row, text="%").grid(row=0, column=col * 3 + 2, sticky="w", padx=(1, 0))

        self.lbl_prod = ttk.Label(card, text="", foreground="#7A5C1E",
                                  font=(self.family, BODY - 1), justify="left")
        self.lbl_prod.grid(row=6, column=0, columnspan=6, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_prod, card)

        self.lbl_partner = ttk.Label(card, text="", foreground="#7A5C1E",
                                     font=(self.family, BODY - 2), justify="left")
        self.lbl_partner.grid(row=7, column=0, columnspan=6, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_partner, card)

        self.lbl_mio_route = ttk.Label(card, text="", foreground="#5A6472",
                                       font=(self.family, BODY - 2), justify="left")
        self.lbl_mio_route.grid(row=8, column=0, columnspan=6, sticky="w", padx=PADX)

        self.tree_mio = ttk.Treeview(card, columns=("lvl", "trait", "bonus"),
                                     show="headings", height=5)
        for cid, text, w, anchor in (("lvl", "等级", 60, "center"), ("trait", "特质", 340, "w"),
                                     ("bonus", "该特质加成", 420, "w")):
            self.tree_mio.heading(cid, text=text)
            self.tree_mio.column(cid, width=w, anchor=anchor)
        self.tree_mio.grid(row=9, column=0, columnspan=6, sticky="ew", padx=PADX, pady=(0, PADY))

        self.frm_traits = ttk.Frame(card)
        self.frm_traits.grid(row=10, column=0, columnspan=6, sticky="ew", padx=PADX, pady=(0, PADY))
        self.lbl_traits_hint = ttk.Label(
            self.frm_traits, text="点击行勾选/取消（初始特质已默认计入，不需要勾）")
        self.lbl_traits_hint.grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Button(self.frm_traits, text="全不选", command=self._clear_traits).grid(
            row=0, column=2, sticky="e", padx=(PADX, 0))
        ttk.Button(self.frm_traits, text="按满级最优勾选",
                   command=self._seed_traits_from_route).grid(row=0, column=3, sticky="e")
        self.frm_traits.columnconfigure(1, weight=1)      # 中间留白，按钮靠右
        self.tree_traits = ttk.Treeview(self.frm_traits,
                                        columns=("sel", "trait", "bonus", "req"),
                                        show="headings", height=6)
        for cid, text, w, anchor in (("sel", "选中", 50, "center"), ("trait", "特质", 300, "w"),
                                     ("bonus", "加成", 360, "w"), ("req", "前提 / 互斥", 330, "w")):
            self.tree_traits.heading(cid, text=text)
            self.tree_traits.column(cid, width=w, anchor=anchor)
        self.tree_traits.grid(row=1, column=0, sticky="ew")
        self.tree_traits.bind("<Button-1>", self._on_trait_click)
        self.tree_traits.tag_configure("locked", foreground="#A8AEB8")   # 现在点不了的特质
        sb = ttk.Scrollbar(self.frm_traits, orient="vertical", command=self.tree_traits.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.tree_traits.configure(yscrollcommand=sb.set)
        row += 1

        # ⑤ 国家精神加成
        box = self._card(row, "⑤ 国家精神加成")
        ttk.Label(box, text="国家精神（逗号分隔，可空）").grid(row=0, column=0, sticky="e",
                                                              padx=(PADX, 4), pady=PADY)
        self.var_spirits = tk.StringVar(value=",".join(self.inputs.get("national_spirits") or []))
        ent_spirits = ttk.Entry(box, textvariable=self.var_spirits, width=64)
        ent_spirits.grid(row=0, column=1, sticky="w")
        # 国家精神也会影响"哪条路线/哪个方针最优"→ 填完（离开输入框）就重推一次
        ent_spirits.bind("<FocusOut>", lambda e: self._on_inputs_affecting_plan())
        ttk.Button(box, text="预览国家精神总加成", command=self._refresh_totals).grid(
            row=0, column=2, sticky="w", padx=PADX)
        self.lbl_spirit = ttk.Label(box, text="—", foreground=ACCENT,
                                    font=(self.family, BODY, "bold"), justify="left")
        self.lbl_spirit.grid(row=1, column=0, columnspan=3, sticky="w", padx=PADX, pady=(0, PADY))
        self._wrap_to_card(self.lbl_spirit, box)
        row += 1

        # ⑥ 总体累计（二选一）
        card = self._card(row, "⑥ 总体累计（二选一）")
        self.var_source = tk.StringVar(value=self.inputs.get("modifier_source") or "mio")
        ttk.Radiobutton(card, text="军工组织 + 国家精神", variable=self.var_source,
                        value="mio", command=self._sync_source).grid(row=0, column=0, sticky="w",
                                                                     padx=(PADX, 4), pady=PADY)
        ttk.Radiobutton(card, text="手动输入（直接给最终修正，不再叠加）", variable=self.var_source,
                        value="manual", command=self._sync_source).grid(row=0, column=1, sticky="w",
                                                                       padx=PADX)

        self.frame_manual = ttk.Frame(card)
        self.frame_manual.grid(row=1, column=0, columnspan=2, sticky="ew")
        mods = self.inputs.get("manufacturer_modifiers") or {}
        self.mod_vars = {}
        ttk.Label(self.frame_manual, text="单位：%（例 9 = +9%）").grid(row=0, column=8,
                                                                     columnspan=2, sticky="w",
                                                                     padx=PADX)
        for i, (key, label) in enumerate(MOD_FIELDS):
            r, c = 1 + i // 5, (i % 5) * 2          # 2 行 × 5 列
            ttk.Label(self.frame_manual, text=label).grid(row=r, column=c, sticky="e",
                                                          padx=(PADX, 4), pady=2)
            var = tk.StringVar(value=("%g" % (mods.get(key, 0) * 100)))
            self.mod_vars[key] = var
            ttk.Entry(self.frame_manual, textvariable=var, width=7, justify="right").grid(
                row=r, column=c + 1, sticky="w", padx=(0, PADX), pady=2)

        ttk.Label(card, text="合计").grid(row=2, column=0, sticky="e", padx=(PADX, 4),
                                         pady=(0, PADY))
        self.lbl_overall = ttk.Label(card, text="—", foreground=ACCENT,
                                     font=(self.family, BODY, "bold"), justify="left")
        self.lbl_overall.grid(row=2, column=1, sticky="w", pady=(0, PADY))
        self._wrap_to_card(self.lbl_overall, card)
        ttk.Button(card, text="预览总体加成", command=self._refresh_totals).grid(
            row=2, column=2, sticky="w", padx=PADX, pady=(0, PADY))

        row += 1

        # ⑦ 最终结果展示
        card = self._card(row, "⑦ 最终结果展示")
        bar = ttk.Frame(card)
        bar.grid(row=0, column=0, sticky="ew", padx=PADX, pady=(PADY, 2))

        # 第一行：动作 + 输出路径。路径很长，单独占一行，否则会把下面的轴选择挤出框、点不到
        bar_btn = ttk.Frame(bar)
        bar_btn.pack(fill="x")
        ttk.Button(bar_btn, text="计算", command=self.on_calculate).pack(side="left")
        ttk.Button(bar_btn, text="导出 Excel", command=self.on_export).pack(side="left",
                                                                          padx=(6, 0))
        ttk.Label(bar_btn, text="输出：%s" % run.DEFAULT_OUT).pack(side="left", padx=PADX)

        # 第二行：帕累托图轴选择
        bar_axis = ttk.Frame(bar)
        bar_axis.pack(fill="x", pady=(3, 0))
        ttk.Label(bar_axis, text="帕累托图").pack(side="left")
        ttk.Label(bar_axis, text="X 轴").pack(side="left", padx=(PADX, 2))
        self.var_axis_x = tk.StringVar(value=AXIS_LABELS.get(self.inputs.get("pareto_x") or "cost",
                                                            AXIS_LABELS["cost"]))
        ttk.Combobox(bar_axis, textvariable=self.var_axis_x, width=18, state="readonly",
                     values=[label for _k, label in AXIS_CHOICES]).pack(side="left", padx=4)
        ttk.Label(bar_axis, text="Y 轴").pack(side="left", padx=(PADX, 0))
        self.var_axis_y = tk.StringVar(value=AXIS_LABELS.get(self.inputs.get("pareto_y") or "score",
                                                            AXIS_LABELS["score"]))
        ttk.Combobox(bar_axis, textvariable=self.var_axis_y, width=18, state="readonly",
                     values=[label for _k, label in AXIS_CHOICES]).pack(side="left", padx=4)
        for var in (self.var_axis_x, self.var_axis_y):
            var.trace_add("write", lambda *_: self._render_rows())

        # 表头式筛选：按列各给一个控件（用途 / 年份 / 帕累托 / 机型）
        bar2 = ttk.Frame(card)
        bar2.grid(row=1, column=0, sticky="ew", padx=PADX, pady=(0, 2))
        ttk.Label(bar2, text="筛选").pack(side="left", padx=(0, 6))
        self.var_f_role = tk.StringVar(value="全部")
        self.var_f_year = tk.StringVar(value="全部")
        self.var_f_pareto = tk.StringVar(value="全部")
        self.var_filter = tk.StringVar(value="")
        self.cb_f_role = ttk.Combobox(bar2, textvariable=self.var_f_role, width=9, state="readonly")
        self.cb_f_year = ttk.Combobox(bar2, textvariable=self.var_f_year, width=7, state="readonly")
        self.cb_f_pareto = ttk.Combobox(bar2, textvariable=self.var_f_pareto, width=10,
                                        state="readonly", values=["全部", "只看前沿", "只看被支配"])
        for text, widget in (("用途", self.cb_f_role), ("年份", self.cb_f_year),
                             ("帕累托", self.cb_f_pareto)):
            ttk.Label(bar2, text=text).pack(side="left", padx=(PADX, 2))
            widget.pack(side="left")
        ttk.Label(bar2, text="机型").pack(side="left", padx=(PADX, 2))
        ttk.Entry(bar2, textvariable=self.var_filter, width=14).pack(side="left")
        ttk.Label(bar2, text="（点表头排序；右上角下拉选轴）").pack(side="left", padx=PADX)
        for var in (self.var_f_role, self.var_f_year, self.var_f_pareto, self.var_filter):
            var.trace_add("write", lambda *_: self._render_rows())

        self.tree_out = ttk.Treeview(card,
                                     columns=("role", "rank", "pareto", "plane", "pure",
                                              "effect", "cost", "year", "weighted", "design"),
                                     show="headings", height=12)
        for cid, text, w, anchor in (("role", "用途", 110, "w"), ("rank", "#", 36, "center"),
                                     ("pareto", "帕累托", 56, "center"),
                                     ("plane", "机型", 250, "w"),
                                     ("pure", "总分数（性能/造价）", 140, "e"),
                                     ("effect", "性能分数", 96, "e"),
                                     ("cost", "有效造价（IC）", 108, "e"),
                                     ("year", "年份", 52, "center"),
                                     ("weighted", "飞机装配资源加权分（总分数/资源开销）", 210, "e"),
                                     ("design", "推荐改装（全称）", 430, "w")):
            self.tree_out.heading(cid, text=text,
                                  command=lambda c=cid: self._sort_by(c))
            self.tree_out.column(cid, width=w, anchor=anchor)
        self.lbl_pareto = ttk.Label(card, text="", foreground=ACCENT, font=(self.family, BODY - 1))
        self.lbl_pareto.grid(row=3, column=0, sticky="w", padx=PADX, pady=(0, PADY))
        # 表格单元格不能换行，所以选中行时在下方（散点图上方）用**分块标签**显示明细：
        # 左边一栏是块名（推荐改装 / 改装属性 / 设计数值 / 性能分数 / 战斗比值），右边是内容。
        self.frm_design = ttk.Frame(card)
        self.frm_design.grid(row=4, column=0, sticky="ew", padx=PADX, pady=(0, PADY))
        self.frm_design.columnconfigure(1, weight=1)
        self.tree_out.bind("<<TreeviewSelect>>", lambda e: self._show_design())
        self.canvas_plot = tk.Canvas(card, height=300, background="white", highlightthickness=1,
                                     highlightbackground="#D0D7E5")
        self.canvas_plot.grid(row=5, column=0, sticky="ew", padx=PADX, pady=(0, PADY))
        self.canvas_plot.bind("<Configure>", lambda e: self._draw_chart())
        self.tree_out.grid(row=2, column=0, sticky="nsew", padx=PADX, pady=(2, PADY))
        card.columnconfigure(0, weight=1)

    # ---------- 联动 ----------
    def _country_label(self, tag):
        """tag → 界面上的中文国名（覆盖表 → 汉化 → tag）。"""
        return COUNTRY_ZH_OVERRIDE.get(tag) or zh(self.loc, tag) or tag

    def _tag(self):
        """当前国家下拉的中文名 → tag。"""
        return self._label_to_tag.get(self.var_tag.get(), self.var_tag.get())

    def _enemy_tag(self):
        return self._label_to_tag.get(self.var_enemy_tag.get(), self.var_enemy_tag.get())

    def _relevant_techs(self):
        """**当前国家**用得到的前置科技：候选机身的改装前置 + 该国军工组织的方针/特质前置。

        国家换了就只列它相关的科技，避免出现"别国才需要的科技"造成误解。
        """
        techs = set()
        # 该国候选机身的改装前置
        for arch in self._country_archetypes():
            for entry in self.data.get("archetypes") or []:
                if entry["archetype"] != arch:
                    continue
                for key in entry["upgrades"]:
                    up = next((u for u in self.data.get("upgrades") or [] if u["key"] == key), None)
                    if up:
                        techs |= set((up.get("requires") or {}).get("techs") or [])
        # 该国航空军工组织的方针 / 特质前置
        orgs = self._air_orgs()[0] if getattr(self, "_org_keys", None) or True else []
        for org in orgs:
            types = self._policy_types(org)
            for pol in self.data.get("policies") or []:
                if not (pol.get("allowed_all") or (set(pol.get("equipment_types") or []) & types)):
                    continue
                if not self._has_modeled_effect(pol):
                    continue          # 只有研究加成、对数值没影响的方针不必列前置
                techs |= set(pol.get("requires_techs") or [])
            for trait in org.get("traits", []) or []:
                techs |= set(trait.get("requires_techs") or [])
        return sorted(techs)

    def _country_archetypes(self):
        """当前国家 + 当前用途 + 科技年份下的候选机身 archetype 集合。"""
        roles = [k for k, v in self.role_vars.items() if v.get()] or ["air_far"]
        want = set(engine.role_archetypes(roles))
        tag = self._tag()
        year = int(self.var_tech.get())
        return {a.get("archetype") for a in self.data.get("airframes_all") or []
                if a.get("country") == tag and (a.get("year") or 0) <= year
                and a.get("archetype") in want}

    def _relevant_flags(self):
        """兼容旧调用：[(flag, 显示名, 说明)]。"""
        return [(flag, name, "▸ 改装：%s" % label)
                for flag, name, label, _year in self._flag_targets()]

    def _requirement_groups(self):
        """把 ③ 的勾选项按"启用的目标"分组——同一目标的多个前置排在同一行。

        例：大型飞机工厂(1943) 与 化学工业 III(1942) 都是「改装：改良舱盖」的前置，
        会被放成一组。
        """
        years = self.data.get("tech_years") or {}
        groups = {}
        for tech, targets in self._tech_targets().items():
            if not targets:
                continue
            key = tuple("%s：%s" % (kind, name) for kind, name in targets)
            groups.setdefault(key, []).append((("tech", tech), zh(self.loc, tech) or tech,
                                               str(years.get(tech) or ""), "tech"))
        for flag, name, label, year_text in self._flag_targets():
            groups.setdefault(("改装：" + label,), []).append(
                (("flag", flag), name, year_text, "flag"))
        out = []
        for key in sorted(groups, key=lambda kv: (len(kv), kv)):
            items = sorted(groups[key], key=lambda it: (years.get(it[0][1]) or 9999, it[1]))
            out.append((" / ".join(key), items))
        return out

    def _build_tech_checks(self):
        """重建 ③：按"启用的目标"分组，**每组一个勾选框**（勾上=这组前置全部满足），两列排布。"""
        for child in self.frm_tech.winfo_children():
            child.destroy()
        self.tech_vars, self.flag_vars, self.group_vars = {}, {}, {}
        # 默认 = "到**当前年份**为止已完成"（用户口径：只看当前年份，与飞机科技年份无关）；
        # 换年份会刷新；之后手动改的勾选不再保留。
        years = self.data.get("tech_years") or {}
        year = int(self.var_year.get() or 1939)
        self._tech_default_year = year          # 记住这份默认是按哪一年生成的
        unlocked = {t for t in self._relevant_techs() if (years.get(t) or 9999) <= year}
        flags_on = set(self.inputs.get("unlocked_flags") or [])
        self._group_items = {}
        for i, (group_text, items) in enumerate(self._requirement_groups()):
            cell = ttk.Frame(self.frm_tech)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, PADX), pady=1)
            keys = []
            for (kind, key), name, year, _kind in items:
                var = tk.BooleanVar(value=(key in unlocked) if kind == "tech" else (key in flags_on))
                (self.tech_vars if kind == "tech" else self.flag_vars)[key] = var
                keys.append((kind, key))
            need = " + ".join(("%s %s" % (name, year)).strip() for _k, name, year, _kk in items)
            gvar = tk.BooleanVar(value=all(
                (self.tech_vars if kind == "tech" else self.flag_vars)[key].get()
                for kind, key in keys))
            self.group_vars[group_text] = gvar
            self._group_items[group_text] = keys
            ttk.Checkbutton(cell, text=group_text, variable=gvar,
                            command=lambda g=group_text: self._toggle_group(g)).pack(side="left")
            ttk.Label(cell, text="　需 " + need, foreground="#5A6472",
                      font=(self.family, BODY - 2)).pack(side="left")

    def _toggle_group(self, group_text):
        """勾/取消一个分组 = 把这组的前置科技（或特殊工程）一起置为同一状态。"""
        want = self.group_vars[group_text].get()
        _dbg("操作：条件勾选「%s」→ %s（涉及 %s）"
             % (group_text, "打开" if want else "关闭",
                "、".join(k for _kd, k in self._group_items.get(group_text, []))))
        for kind, key in self._group_items.get(group_text, []):
            (self.tech_vars if kind == "tech" else self.flag_vars)[key].set(want)
        self._sync_group_vars()
        self._on_tech_changed()

    def _sync_group_vars(self):
        """任一前置项变化后，同步各分组勾选框的状态（全部满足才打勾）。"""
        for group_text, keys in getattr(self, "_group_items", {}).items():
            var = self.group_vars.get(group_text)
            if var is None:
                continue
            ok = all((self.tech_vars if kind == "tech" else self.flag_vars)[key].get()
                     for kind, key in keys)
            if bool(var.get()) != ok:
                var.set(ok)

    def _on_tech_changed(self):
        self._plans.clear()          # 科技变了，满级路线缓存作废
        self._refresh_policies()
        self._recommend_org()

    def _on_tech_year_changed(self):
        """科技年份变了：候选机身（也就是改装/科技清单）跟着变。"""
        self._plans.clear()
        self._build_tech_checks()
        self._refresh_country()

    def _tech_usage(self):
        """{科技: ["改装：改良舱盖", "方针：完美抛光", ...]}——这项科技能启用什么（全称）。"""
        return {tech: ["%s：%s" % (kind, label) for kind, label in targets]
                for tech, targets in self._tech_targets().items()}

    def _tech_targets(self):
        """{科技: [(类型, 目标名), …]}——改装名用汉化全称，和结果表一致。"""
        targets = {}

        def add(tech, kind, name):
            bucket = targets.setdefault(tech, [])
            if (kind, name) not in bucket:
                bucket.append((kind, name))

        for up in self.data.get("upgrades") or []:
            if str(up.get("key", "")).startswith("cv_"):
                continue
            label = run.upgrade_label(up["key"])          # ← 全称，与结果表一致
            for tech in (up.get("requires") or {}).get("techs") or []:
                add(tech, "改装", label)
        # 方针 / 特质只统计**当前国家**的飞机类军工组织，避免把别国的东西算进来
        orgs = self._air_orgs()[0] if getattr(self, "var_tag", None) else []
        org_types = set()
        for org in orgs:
            org_types |= self._policy_types(org)
        for pol in self.data.get("policies") or []:
            if not (pol.get("allowed_all") or (set(pol.get("equipment_types") or []) & org_types)):
                continue
            if not self._has_modeled_effect(pol):
                continue          # 只有研究加成、对数值没影响的方针不进用途标注
            for tech in pol.get("requires_techs") or []:
                add(tech, "方针", zh(self.loc, pol["token"]) or pol["token"])
        for org in orgs:
            for trait in org.get("traits", []) or []:
                for tech in trait.get("requires_techs") or []:
                    add(tech, "特质", zh(self.loc, trait["token"]) or trait["token"])
        return targets

    def _flag_targets(self):
        """特殊工程授予的国家标识 → (flag, 显示名, 它解锁的改装全称, 年份文字)。

        特殊工程自身没有科技年份，按"工程前置科技里最晚那项 + 1"折算，写成「视同1944」。
        """
        years = self.data.get("tech_years") or {}
        grants = {}
        for proj in self.data.get("special_projects") or []:
            for flag in proj.get("flags") or []:
                grants[flag] = proj
        out = []
        for up in self.data.get("upgrades") or []:
            label = run.upgrade_label(up["key"])
            for flag in (up.get("requires") or {}).get("flags") or []:
                proj = grants.get(flag)
                name = ("%s（特殊工程）" % (zh(self.loc, proj["project"]) or proj["project"])
                        if proj else flag)
                year_text = ""
                if proj:
                    base = [years.get(t) for t in proj.get("requires_techs") or []]
                    base = [y for y in base if y]
                    if base:
                        year_text = "视同%d" % (max(base) + 1)
                out.append((flag, name, label, year_text))
        return out

    def _plan_key(self, inputs):
        return (tuple(inputs["roles"]), inputs["tech_year"], inputs["current_year"],
                tuple(sorted(inputs.get("unlocked_techs") or [])),
                tuple(sorted(inputs.get("unlocked_flags") or [])),
                float(inputs.get("range_cap") or 0),
                json.dumps(inputs.get("experience") or {}, sort_keys=True),
                inputs.get("country"),
                # 对手也进键：对手机动/速度直接参与评分，换对手必须重算路线
                json.dumps(inputs.get("enemy") or {}, sort_keys=True),
                # 口径与生产堆叠也要进键：换了它们，路线与折算都会变
                inputs.get("alloc_mode") or "split",
                int(inputs.get("efficiency_cap_now") or 100),
                int(inputs.get("capacity_bonus_now") or 200))

    def _policies_for_org(self, org, techs):
        """该军工组织可用且科技已满足的方针（含**只有生产侧效果**的，如模块化装配）。"""
        types = self._policy_types(org)
        out = [None]                       # None = 不选方针
        for pol in self.data.get("policies") or []:
            if not self._has_modeled_effect(pol):
                continue              # 只给"军工组织研究加成"之类、对分数没影响的方针不列
            if pol.get("allowed_all"):
                pass
            elif pol.get("equipment_types"):
                if not (set(pol["equipment_types"]) & types):
                    continue
            else:
                continue
            if any(t not in techs for t in pol.get("requires_techs") or []):
                continue
            out.append(pol)
        return out

    @staticmethod
    def _policy_bonus(pol):
        if not pol:
            return {}
        return {k: v for k, v in (pol.get("equipment_bonus") or {}).items()
                if k != "production_cost_factor"}

    @staticmethod
    def _has_modeled_effect(pol):
        """方针是否对**我们建模的东西**有影响：设计侧加成，或生产侧修正（产量/花费…）。

        · 模块化装配：只有 `production_cost_factor` → **要列**（生产折算用得上）；
        · 推进系统实验组 / 不断的工业革命：只有军工组织研究加成 → 不影响飞机数值与分数 → 不列。
        """
        if not pol:
            return False
        return bool(pol.get("equipment_bonus") or pol.get("production_bonus"))

    @staticmethod
    def _has_design_bonus(pol):
        """（用途标注用）方针是否带"设计侧"装备加成。"""
        if not pol:
            return False
        return any(v for k, v in (pol.get("equipment_bonus") or {}).items()
                   if k != "production_cost_factor")

    def _with_route(self, inputs):
        """自动配点模式下，把**界面上显示的那条路线**显式传给计算。

        以前 run.py 会自己再按"不含方针"优化一遍，而 ④ 预览用的是"含方针"的优化
        —— 两条路线可能不同（实测 1939：预览选织物覆盖、计算却用金属覆盖），
        于是"看到的"和"算出来的"对不上。现在统一由界面把路线定下来。

        2026-10-11：**兼顾口径也一起钉**。`_org_plan` 对兼顾用的就是
        `route_best(fold=True)`（每条候选集跑真实管线、含生产折算），和 run.py
        自己搜的是同一套；钉住之后"预览路线 == 计算路线"由结构保证，
        不再依赖两边各自搜出来的结果碰巧一致。
        """
        mio = dict(inputs.get("mio") or {})
        if mio.get("manual_traits") is None:
            org = self._org()
            plan = self._org_plan(org, inputs) if org else None
            if plan and plan.get("route"):
                mio["manual_traits"] = list(plan["route"])
        return dict(inputs, mio=mio)

    def _ref_plane(self):
        """当前输入下的"参考机型"（候选里年份最新的那架）——路线与装备类型过滤都按它。"""
        try:
            inputs = self.collect()
            pool = run.candidate_pool(inputs, self.data)
        except (Exception, SystemExit):      # noqa: BLE001
            return None
        return self._ref_plane_of(inputs, pool)

    def _ref_plane_of(self, inputs, pool):
        """参考机型 = 该用途下"空修正"分数最高的候选（与 run.build_rows 口径一致）。"""
        enemy_by_role = {
            r: engine.pick_enemy_values(self.data["airframes_all"],
                                        inputs.get("enemy") or {}, r,
                                        inputs["current_year"])
            for r in inputs["roles"]}
        return run.pick_reference_plane(pool, inputs, self.data,
                                        engine.upgrades_by_key(self.data["upgrades"]),
                                        enemy_by_role)

    def _plan_context(self, inputs):
        """(参考机型, upgrade_map, 对手机动速度, 事故系数, score_key)——算一次给多处用。"""
        upgrade_map = engine.upgrades_by_key(self.data["upgrades"])
        pool = run.candidate_pool(inputs, self.data)
        if not pool:
            return None
        ref = self._ref_plane_of(inputs, pool)
        role = inputs["roles"][0]
        _enemy, enemy_values = engine.pick_enemy_values(
            self.data["airframes_all"], inputs.get("enemy") or {}, role, inputs["current_year"])
        return (ref, upgrade_map, enemy_values, engine.accident_factor(role in engine.CARRIER_ROLES),
                engine.score_role(role),
                engine.available_upgrades(ref["category"], self.data,
                                          techs=inputs.get("unlocked_techs") or [],
                                          flags=inputs.get("unlocked_flags") or [],
                                          archetype=ref.get("archetype"))[0])

    def _org_plan(self, org, inputs):
        """满级 + 最佳方针下的配点路线（方针 × 路线 **联合穷举**，带表/缓存）。

        方针在这里被当成"等级前置、不占特质点数、彼此互斥"的伪特质，
        和特质一起穷举（每个方针各跑一次真实管线），不再"先用廉价分挑方针"。
        结果先查离线表（data/route_table.json），再查本机缓存（route_cache.json），
        都没有才算一次并写进缓存。
        """
        key = self._plan_key(inputs)
        cache = self._plans.setdefault(key, {})
        if org["organization"] in cache:
            return cache[org["organization"]]
        plan = None
        ctx = self._plan_context(inputs)
        if ctx:
            ref, upgrade_map, enemy_values, acc, score_key, tokens = ctx
            ini = org.get("initial_trait")
            ini_mods = engine.combine_modifiers(ini.get("bonuses") if ini else {})
            pols = self._plan_policies(org, inputs)
            fold = (inputs.get("alloc_mode") or "split") == "balanced"
            cap_now = int(inputs.get("efficiency_cap_now") or 100)
            ca_now = int(inputs.get("capacity_bonus_now") or 200)
            dkey = self._disk_plan_key(inputs, org, ref, pols)
            rec = self._lookup_plan(dkey)
            if rec is None:
                pol, _chosen, mods, log, score, gain = engine.route_best_joint(
                    org, engine.MIO_MAX_LEVEL, ref, upgrade_map, ini_mods, enemy_values,
                    inputs["roles"], inputs.get("range_cap"), policies=pols,
                    experience=inputs.get("experience"),
                    techs=inputs.get("unlocked_techs") or [], cap_now=cap_now,
                    capacity_now=ca_now, available=tokens, fold=fold,
                    cache_key=(org["organization"], "plan", fold, cap_now, ca_now,
                               ref.get("key"), key),
                    initial_production=dict(ini.get("production") or {}) if ini else {},
                    score_role_key=score_key)
                # 表里只存"最小记录"（方针 + 路线 token + 分数），读的时候按 MIO 数据重建
                rec = {"policy": (pol.get("token") if pol else None),
                       "route": [item["token"] for item in log],
                       "score": score, "gain": gain}
                self._store_plan(dkey, rec)
            plan = self._plan_from_record(org, rec)
        cache[org["organization"]] = plan
        return plan

    def _plan_from_record(self, org, rec):
        """把表里的最小记录重建成本界面要用的完整方案（含每项特质的加成明细）。"""
        by_token = {t.get("token"): t for t in org.get("traits", [])}
        ini = org.get("initial_trait")
        mods = engine.combine_modifiers(ini.get("bonuses") if ini else {})
        pol = next((p for p in self.data.get("policies") or []
                    if p.get("token") == rec.get("policy")), None)
        mods = engine.combine_modifiers(mods, engine.policy_design_bonus(pol))
        log = []
        for token in rec.get("route") or []:
            trait = by_token.get(token) or {}
            log.append({"token": token, "bonuses": trait.get("bonuses") or {},
                        "production": trait.get("production") or {}})
            mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
        return {"score": rec.get("score"), "policy": rec.get("policy"),
                "gain": rec.get("gain"), "mods": mods, "log": log,
                "route": list(rec.get("route") or [])}

    def _plan_policies(self, org, inputs):
        """该组织在**当前科技 + 当前等级**下可选的方针（不含 None）。"""
        level = int((inputs.get("mio") or {}).get("level") or 0)
        techs = set(inputs.get("unlocked_techs") or [])
        return [p for p in self._policies_for_org(org, techs)
                if p and int(p.get("min_size") or 0) <= level]

    def _disk_plan_key(self, inputs, org, ref, pols):
        """离线表/本机缓存用的键：方案的输入指纹 + 该组织当前可选的方针集合。"""
        base = run.plan_key(inputs, org["organization"], (ref or {}).get("key"))
        return base + "|pol:" + ",".join(sorted(p["token"] for p in pols))

    def _lookup_plan(self, dkey):
        """先查本机缓存，再查随包发布的离线表。"""
        if dkey in self._plan_runtime:
            return self._plan_runtime[dkey]
        plan = None
        if dkey not in self._plan_table:
            # 按当前 (国家, 用途) 读对应的分片（带缓存，只读一次）
            inputs = self.collect()
            role = (inputs.get("roles") or ["air_far"])[0]
            self._plan_table = run.load_plan_table(inputs.get("country"), role)
            self._plan_table.update(run.load_plan_table())      # 兼容旧单文件
        plan = self._plan_table.get(dkey)
        if plan is not None:
            self._plan_runtime[dkey] = plan
        return plan

    def _store_plan(self, dkey, plan):
        """新算出来的方案写进本机缓存（立刻落盘，下次启动直接命中）。"""
        self._plan_runtime[dkey] = plan
        run.save_plan_cache(self._plan_runtime)
        self._plan_cache_saved = len(self._plan_runtime)

    def _recommend_org(self, apply_org=True):
        """"满级 + 方针"下比较各军工组织；apply_org=True 时把最优的设为默认。

        `apply_org=False` 用于"输入变了、只把那行推荐重算一遍"：
        以前换对手/年份只刷新了方针下拉，**推荐那行还是旧状态的**（例如写着"完美抛光"，
        下拉却是"风洞先驱"），因为推荐行只在换国家等少数时机重算。

        **分块**：每家 MIO 算完就 `after(1)` 排下一家 —— 方针×路线联合穷举一家要
        0.5~2.4 秒，三家一起算会让界面僵 2 秒以上；分块之后界面能喘气，
        当前组织的方案照旧由 ④ 预览/结果表那条路径同步算出来。
        """
        try:
            inputs = self.collect()
        except (Exception, SystemExit):  # noqa: BLE001
            return
        import time as _t
        self._rec_inputs = inputs
        self._rec_apply = apply_org
        self._rec_queue = list(self._air_orgs()[0])
        self._rec_done = {}
        self._rec_t0 = _t.time()
        self._rec_seq = getattr(self, "_rec_seq", 0) + 1
        self.after(1, self._recommend_step)

    def _recommend_step(self, seq=None):
        seq = getattr(self, "_rec_seq", -1) if seq is None else seq
        if seq != getattr(self, "_rec_seq", -1):
            return                      # 输入又变了，这一轮作废
        queue = getattr(self, "_rec_queue", [])
        if queue:
            org = queue.pop(0)
            plan = self._org_plan(org, self._rec_inputs)
            if plan and plan.get("score"):
                self._rec_done[org["organization"]] = (org, plan)
            self.after(1, lambda: self._recommend_step(seq))
            return
        self._recommend_finish()

    def _recommend_finish(self):
        import time as _t
        inputs = self._rec_inputs
        orgs = self._air_orgs()[0]
        cache = self._plans.get(self._plan_key(inputs)) or {}
        redo = sum(1 for org in orgs if org["organization"] not in cache)
        spent = _t.time() - self._rec_t0
        scored = sorted(self._rec_done.values(), key=lambda item: -item[1]["score"])
        scored.sort(key=lambda item: -item[1]["score"])
        if scored:
            best, best_plan = scored[0]
            label = next((l for l, k in self._org_keys.items() if k == best["organization"]), None)
            if label and self._rec_apply:
                self.var_org.set(label)
            pol = next((p for p in self.data.get("policies") or []
                        if p["token"] == best_plan.get("policy")), None)
            # 用户只看得懂比较值：给"比次优高多少"，不给绝对分数
            if len(scored) > 1 and scored[1][1]["score"]:
                gap = (best_plan["score"] / scored[1][1]["score"] - 1) * 100
                extra = "，比次优「%s」高 %.1f%%" % (
                    zh(self.loc, scored[1][0]["organization"]), gap)
            else:
                extra = ""
            self.lbl_org_rec.configure(
                text="推荐：%s（满级 + %s%s）"
                     % (zh(self.loc, best["organization"]),
                        zh(self.loc, pol["token"]) if pol else "无方针", extra))
            if len(orgs) <= 1:
                # 只有一家可选时给不出"比次优高多少" —— 说明白，免得被当成"就这么定的"
                self.lbl_org_rec.configure(
                    text=self.lbl_org_rec.cget("text")
                         + "〔该参考机型只适用 1 家 MIO，未作比较〕")
            ref = self._ref_plane()
            if ref:
                self.lbl_org_rec.configure(
                    text="参考机型：%s（%s）｜" % (zh(self.loc, ref["key"]) or ref["name"],
                                              engine.CATEGORY_ZH.get(ref.get("category"),
                                                                      ref.get("category")))
                         + self.lbl_org_rec.cget("text"))
            # 只打一行汇总：以前每个组织打一行，一次操作能刷 5 行
            _dbg("MIO 路线：比较 %d 个组织（重算 %d，缓存命中 %d，用时 %.2fs）"
                 "→ 推荐「%s」，方针「%s」%s"
                 % (len(orgs), redo, len(orgs) - redo, spent,
                    zh(self.loc, best["organization"]),
                    zh(self.loc, pol["token"]) if pol else "无方针", extra))
        else:
            self.lbl_org_rec.configure(text="推荐：（暂无可比较的军工组织）")
            _dbg("MIO 路线：比较 %d 个组织 → 无可比较结果（用时 %.2fs）" % (len(orgs), spent))
        if self._rec_apply:
            self._on_org_change()

    def _air_orgs(self):
        """能用于战斗机的军工组织：优先本国独特 MIO；本国没有才回退默认 MIO。"""
        tag = self._tag()
        # 过滤逻辑与"对手 AI 会用哪家 MIO"共用（engine.country_air_mios）
        own = engine.country_air_mios(self.data["mio"], tag, self._ref_plane(), self.by_name)
        own.sort(key=lambda o: o["organization"])
        if own:
            return own, False
        generic = [o for o in self.data["mio"]
                   if os.path.basename(o.get("file", "")) == "00_generic_organization.txt"
                   and engine.is_air_mio(o, self.by_name)]
        generic.sort(key=lambda o: o["organization"])
        return generic, True

    def _refresh_country(self):
        orgs, _fallback = self._air_orgs()
        self._org_keys = {}
        seen = {}
        for org in orgs:
            name = zh(self.loc, org["organization"]) or org["organization"]
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = "%s（%s）" % (name, org["organization"])
            self._org_keys[name] = org["organization"]
        self.cb_org.configure(values=list(self._org_keys))
        want = ((self.inputs.get("mio") or {}).get("organization") or "")
        cur = next((n for n, k in self._org_keys.items() if k == want), None)
        self.var_org.set(cur or next(iter(self._org_keys), ""))
        self._plans.clear()
        self._build_tech_checks()      # 科技清单随国家变化
        self._recommend_org()          # 默认选"满级 + 方针"下最优的那个军工组织

    def _org_key(self):
        return self._org_keys.get(self.var_org.get(), "")

    def _org(self):
        return self.by_name.get(self._org_key())

    def _on_org_change(self):
        self.chosen_traits = set()
        self._fill_traits()
        self._refresh_policies()
        self.on_preview()
        self._refresh_alloc_recommendation()

    def _policy_types(self, org):
        types = set(org.get("equipment_types") or [])
        for inc in org.get("includes") or []:
            src = self.by_name.get(inc)
            if src:
                types |= set(src.get("equipment_types") or [])
        return types

    def _available_policies(self):
        """当前组织**装备类型匹配**的方针（不管等级/科技），用于下拉与统计。

        含**只有生产侧效果**的方针（模块化装配：生产产出花费 −3%）—— 它在"兼顾"里
        能靠折算提升总分数，在"分离"里也能给生产方当政策；只有"军工组织研究加成"
        （不影响飞机数值与分数）的方针才排除。
        """
        org = self._org()
        if not org:
            return []
        types = self._policy_types(org)
        out = []
        for pol in self.data.get("policies") or []:
            if not self._has_modeled_effect(pol):
                continue          # 研究加成类方针对飞机数值与分数没有影响 → 不列
            if pol.get("allowed_all"):
                out.append(pol)
                continue
            if not pol.get("equipment_types"):
                continue          # 空的 OR 条件 = 谁都选不了（例如条件被注释掉的海军方针）
            if not (set(pol["equipment_types"]) & types):
                continue
            out.append(pol)
        return out

    def _unlocked_techs(self):
        """界面当前勾选的科技（不要读 self.inputs —— 那是启动时的初始值）。"""
        return {t for t, v in getattr(self, "tech_vars", {}).items() if v.get()}

    def _ready_policies(self):
        """**真正能选**的方针：装备类型匹配 + 等级够（方针都是 6 级起）+ 前置科技已勾。

        不满足的不进下拉框——游戏里点不了，工具里也不该能选。
        """
        return [p for p in self._available_policies() if self._policy_ready(p)]

    def _locked_policies(self):
        """装备类型匹配、但等级或科技还没到的方针（用来提示"为什么没得选"）。"""
        return [p for p in self._available_policies() if not self._policy_ready(p)]

    def _policy_gap(self, pol):
        """这个方针还差什么才能选（等级/科技），用于提示文案。"""
        gaps = []
        level = int(self.var_level.get())
        if level < (pol.get("min_size") or 0):
            gaps.append("需 %d 级（当前 %d 级）" % (pol["min_size"], level))
        techs = self._unlocked_techs()
        miss = [t for t in (pol.get("requires_techs") or []) if t not in techs]
        if miss:
            gaps.append("需科技 " + "、".join(zh(self.loc, t) or t for t in miss))
        return "%s（%s）" % (zh(self.loc, pol["token"]) or pol["token"],
                            "；".join(gaps) or "—")

    def _refresh_policies(self):
        self._policy_map = {"（不选）": None}
        labels = ["（不选）"]
        ready = self._ready_policies()
        for pol in ready:
            name = zh(self.loc, pol["token"]) or pol["token"]
            if name in self._policy_map:
                name = "%s [%s]" % (name, pol["token"])
            self._policy_map[name] = pol
            labels.append(name)
        self.cb_policy.configure(values=labels)
        # 默认选"满级 + 方针"路线里那个方针；取不到再退回逐个试算。
        # 关键：只有这个方针**当前可选**（等级/科技都到）时才认它，
        # 否则（例如 1 级时）退回"（不选）"——以前会直接把 6 级方针套上去。
        want = None
        org = self._org()
        if org:
            try:
                want = (self._org_plan(org, self.collect()) or {}).get("policy")
            except (Exception, SystemExit):  # noqa: BLE001
                want = None
        if want and not any(p["token"] == want for p in ready):
            want = None
        best = want or self._best_policy_token()
        target = next((l for l, p in self._policy_map.items() if p and p["token"] == best),
                      "（不选）")
        self.var_policy.set(target)
        self._on_policy_change()

    def _on_level_changed(self):
        """等级改了：方针门槛与"路线前缀"都要重算。"""
        self._refresh_policies()
        self.on_preview()

    def _alloc_mode_key(self):
        """界面上选的配点口径 → design / balanced / split。"""
        for key, label in ALLOC_MODES:
            if label == self.var_alloc_mode.get():
                return key
        return "design"

    def _on_alloc_mode_change(self):
        """改了配点口径：路线、生产折算、结果表全部重算。"""
        _dbg("操作：改配点口径 → %s" % self.var_alloc_mode.get())
        self._refresh_totals()
        self.on_preview()
        if getattr(self, "rows", None):
            self.on_calculate()

    def _refresh_alloc_recommendation(self):
        """比较"分离 / 兼顾"哪个更优，写在配点口径右边（分块算，不阻塞界面）。

        两个口径的计划都走同一套 `_org_plan`（表/缓存命中就瞬间出）。
        """
        self._alloc_rec_seq = getattr(self, "_alloc_rec_seq", 0) + 1
        self.after(1, lambda: self._alloc_rec_step(self._alloc_rec_seq))

    def _alloc_rec_step(self, seq):
        if seq != getattr(self, "_alloc_rec_seq", -1):
            return                       # 输入又变了，这一轮作废
        org = self._org()
        if not org or not getattr(self, "lbl_alloc_rec", None):
            return
        try:
            inputs = self.collect()
        except (Exception, SystemExit):  # noqa: BLE001
            return
        scores = {}
        for mode in ("split", "balanced"):
            probe = dict(inputs)
            probe["alloc_mode"] = mode
            plan = self._org_plan(org, probe)
            if plan and plan.get("score"):
                scores[mode] = plan["score"]
        if len(scores) < 2:
            self.lbl_alloc_rec.configure(text="")
            return
        better = max(scores, key=scores.get)
        worse = min(scores, key=scores.get)
        gap = (scores[better] / scores[worse] - 1) * 100 if scores[worse] else 0.0
        # 不给"持平"这种话：总有一个更高的，把差距直接给出来，用户自己判断
        short = dict(ALLOC_MODES)[better].split("（")[0]
        self.lbl_alloc_rec.configure(text="推荐：%s（比另一种高 %.2f%%）" % (short, gap))

    def _policy_ready(self, pol):
        """门槛（等级 + 科技）是否满足。"""
        if int(self.var_level.get()) < (pol.get("min_size") or 0):
            return False
        techs = self._unlocked_techs()
        return all(t in techs for t in (pol.get("requires_techs") or []))

    def _policy_desc(self, pol):
        """右侧说明：前置要求 + 预计加成。"""
        level = int(self.var_level.get())
        techs = self._unlocked_techs()
        need = []
        if pol.get("min_size"):
            need.append("%d 级%s" % (pol["min_size"], "✓" if level >= pol["min_size"] else "✗"))
        for tech in pol.get("requires_techs") or []:
            need.append("%s%s" % (zh(self.loc, tech) or tech,
                                  "✓" if tech in techs else "✗"))
        bonus = {k: v for k, v in (pol.get("equipment_bonus") or {}).items()
                 if k != "production_cost_factor" and v}
        parts = ["前置：" + ("、".join(need) if need else "无"),
                 "加成：" + (fmt_mods(bonus) if bonus else "无装备修正")]
        # 生产侧：把该方针的生产修正**全部**列出来（含 equipment_bonus 里的生产产出花费）
        prod_mods = {k: v for k, v in engine.policy_production(pol).items() if v}
        if prod_mods:
            parts.append("生产侧（计入折算，不进设计数值）：" + "、".join(
                "%s %+g%%" % (PROD_ZH.get(k, k), round(v * 100, 2))
                for k, v in sorted(prod_mods.items())))
        org_mod = pol.get("organization_modifier") or {}
        if org_mod:
            # 这些是组织级修正（经费/研究），**不影响飞机属性**，说清楚免得误读
            parts.append("组织（不影响飞机属性）：" + fmt_mods(
                {k: v for k, v in org_mod.items() if v}, self.loc))
        return "　".join(parts)

    def _best_policy_token(self):
        """挑"预计加成最优"的方针：用参考机型（当年最新候选）在各方针下的分数取最大。"""
        ready = [p for p in self._available_policies() if self._policy_ready(p)]
        if not ready:
            return None
        try:
            base = self.collect(policy=None)
        except (Exception, SystemExit):  # noqa: BLE001
            return None
        upgrade_map = engine.upgrades_by_key(self.data["upgrades"])
        pool = run.candidate_pool(base, self.data)
        if not pool:
            return None
        ref = max(pool, key=lambda a: (a.get("year") or 0))
        tokens = engine.available_upgrades(ref["category"], self.data,
                                           techs=base.get("unlocked_techs") or [],
                                           flags=base.get("unlocked_flags") or [],
                                           archetype=ref.get("archetype"))[0]
        role = base["roles"][0]
        score_key = engine.score_role(role)
        _enemy, enemy_values = engine.pick_enemy_values(
            self.data["airframes_all"], base.get("enemy") or {}, role, base["current_year"])
        acc_f = engine.accident_factor(role in engine.CARRIER_ROLES)
        best, best_score = None, None
        for pol in ready:
            try:
                mods, _info = run.resolve_manufacturer(self.collect(policy=pol["token"]),
                                                       self.data, upgrade_map, pool)
            except (Exception, SystemExit):  # noqa: BLE001
                continue
            score = engine.evaluate(ref, {t: 0 for t in tokens}, upgrade_map, mods, enemy_values,
                                    base.get("range_cap"), base.get("experience"),
                                    accident_factor=acc_f)[2][score_key]
            if best_score is None or score > best_score:
                best, best_score = pol["token"], score
        return best

    def _on_policy_change(self):
        pol = getattr(self, "_policy_map", {}).get(self.var_policy.get())
        if not pol:
            ready = self._ready_policies()
            locked = self._locked_policies()
            if ready:
                text = "（本组织可选 %d 个方针，默认已选预计最优的那个）" % len(ready)
            elif locked:
                text = "（本组织 %d 个方针现在还选不了：%s）" % (
                    len(locked), "、".join(self._policy_gap(p) for p in locked))
            else:
                text = "（本组织无对应装备类型的方针）"
            self.lbl_policy.configure(text=text)
        else:
            self.lbl_policy.configure(text=self._policy_desc(pol))
        self._refresh_totals()

    def _selected_policy_token(self):
        """下拉框里选中的方针 token；等级/科技没到的一律算"未选"（挡住旧值/程序设置）。"""
        pol = getattr(self, "_policy_map", {}).get(self.var_policy.get())
        if not pol or not self._policy_ready(pol):
            return None
        return pol["token"]

    def _fill_traits(self):
        self.tree_traits.delete(*self.tree_traits.get_children())
        org = self._org()
        if not org:
            return
        unlocked = {t for t, v in self.tech_vars.items() if v.get()}
        ref = self._ref_plane() or {}
        groups = engine.plane_groups(ref.get("archetype"))
        hidden = 0
        hidden_type = 0
        for trait in org.get("traits", []):
            token = trait.get("token")
            if not token:
                continue
            need = trait.get("requires_techs") or []
            if any(t not in unlocked for t in need):
                hidden += 1          # 科技没解锁的特质游戏里也点不了，直接隐藏
                continue
            if groups and not engine.trait_fits(trait, groups, ref.get("archetype")):
                hidden_type += 1     # 只对别的机型生效（如"运输职责"只对运输机）
                continue
            self.tree_traits.insert("", "end", iid=token, values=(
                # ⚠️ 这里要按 chosen_traits 显示勾选状态：以前写死 "☐"，
                # 于是"按满级最优勾选 / 全不选"重填表格后看起来像没勾上（属性却变了）。
                "☑" if token in self.chosen_traits else "☐",
                zh(self.loc, token), fmt_mods(trait.get("bonuses") or {}),
                self._trait_req(trait)))
        base = "点击行勾选/取消（初始特质已默认计入，不需要勾）"
        if hidden:
            base += "　另有 %d 个特质需前置科技，已隐藏" % hidden
        if hidden_type:
            base += "　另有 %d 个特质只适用于其他机型，已隐藏" % hidden_type
        self._traits_hint_base = base
        self.lbl_traits_hint.configure(text=self._traits_hint_base)
        self._refresh_trait_states()

    def _trait_req(self, trait):
        parts = []
        for kind, parents in trait.get("parents") or []:
            names = "、".join(zh(self.loc, p) for p in parents)
            parts.append(("需 " if kind == "all_parents" else "任一 ") + names)
        mx = trait.get("mutually_exclusive") or []
        if mx:
            parts.append("互斥 " + "、".join(zh(self.loc, m) for m in mx))
        return "；".join(parts) or "—"

    def _trait_state(self, trait):
        """这个特质现在能不能点？返回 (能点?, 不能点的原因)。

        规则与游戏一致：前置（all 全要 / any 任一）+ 互斥（不能与已选的同时点）。
        已勾选的特质永远可以取消。
        """
        tok = (trait or {}).get("token")
        if not tok:
            return False, "未知特质"
        if tok in self.chosen_traits:
            return True, ""
        for kind, parents in trait.get("parents") or []:
            hit = [p for p in parents if p in self.chosen_traits]
            if kind == "all_parents" and len(hit) != len(parents):
                miss = [p for p in parents if p not in self.chosen_traits]
                return False, "需要先选 " + "、".join(zh(self.loc, p) for p in miss)
            if kind == "any_parent" and not hit:
                return False, "需要先选其中之一 " + "、".join(zh(self.loc, p) for p in parents)
        for other in trait.get("mutually_exclusive") or []:
            if other in self.chosen_traits:
                return False, "与已选的「%s」互斥" % zh(self.loc, other)
        return True, ""

    def _refresh_trait_states(self):
        """把"现在点不了"的特质置灰：**依旧展示**，但点不进去。"""
        org = self._org()
        if not org:
            return
        for trait in org.get("traits", []):
            tok = trait.get("token")
            if not tok or not self.tree_traits.exists(tok):
                continue
            ok, _why = self._trait_state(trait)
            locked = (not ok) and tok not in self.chosen_traits
            self.tree_traits.item(tok, tags=("locked",) if locked else ())

    def _clear_traits(self):
        """一键清空手动勾选的特质。"""
        self.chosen_traits = set()
        self._trait_order = []
        _dbg("操作：清空手动勾选的特质")
        self._fill_traits()
        self._refresh_after_trait_change()

    def _seed_traits_from_route(self):
        """按"满级最优路线"把所有条目预勾上（手动配点的默认起点，也是清空后的还原按钮）。"""
        org = self._org()
        if not org:
            return
        try:
            plan = self._org_plan(org, self.collect())
        except (Exception, SystemExit):      # noqa: BLE001
            plan = None
        if not plan:
            return
        self._trait_order = [item["token"] for item in plan["log"]]
        self.chosen_traits = set(self._trait_order)
        _dbg("操作：按满级最优路线勾选 %d 项" % len(self._trait_order))
        self._fill_traits()
        self._refresh_after_trait_change()

    def _refresh_after_trait_change(self):
        """勾/清特质之后：④ 的总加成与生产侧清单、⑥ 的总体累计都要重算。

        （以前只调了 `_refresh_totals()`，于是手动勾选后 ④ 那块的"总加成 / 生产侧"不刷新。）
        """
        self._refresh_totals()
        self.on_preview()

    def _on_trait_click(self, event):
        token = self.tree_traits.identify_row(event.y)
        if not token or self.tree_traits.identify_region(event.x, event.y) in ("heading", "separator"):
            return
        self._toggle_trait(token)

    def _toggle_trait(self, token):
        """勾选/取消一个军工组织特质（点行或程序调用都走这里）。"""
        if token in self.chosen_traits:
            self.chosen_traits.discard(token)
            self._trait_order = [x for x in getattr(self, "_trait_order", []) if x != token]
            _dbg("操作：取消勾选特质「%s」，当前依次为 %s"
                 % (zh(self.loc, token),
                    "→".join(zh(self.loc, x) for x in getattr(self, "_trait_order", [])) or "无"))
        else:
            trait = next((t for t in ((self._org() or {}).get("traits") or [])
                          if t.get("token") == token), None)
            ok, why = self._trait_state(trait)
            if not ok:                       # 前置没满足 / 与已选互斥 → 点不进去
                self.lbl_traits_hint.configure(
                    text="不能勾「%s」：%s" % (zh(self.loc, token), why))
                _dbg("操作：拒绝勾选特质「%s」（%s）" % (zh(self.loc, token), why))
                return
            self.chosen_traits.add(token)
            order = getattr(self, "_trait_order", [])
            order.append(token)
            self._trait_order = order
            _dbg("操作：勾选特质「%s」，依次为 %s"
                 % (zh(self.loc, token), "→".join(zh(self.loc, x) for x in order)))
        if getattr(self, "_traits_hint_base", None):
            self.lbl_traits_hint.configure(text=self._traits_hint_base)
        vals = list(self.tree_traits.item(token)["values"])
        vals[0] = "☑" if token in self.chosen_traits else "☐"
        self.tree_traits.item(token, values=vals)
        self._refresh_trait_states()         # 勾/取消之后，解锁与互斥要跟着变
        self._refresh_after_trait_change()

    def _sync_alloc(self):
        if self.var_alloc.get() == "pick":
            self.tree_mio.grid_remove()
            self.frm_traits.grid()
            self.spin_level.configure(state="disabled")
            if not self.chosen_traits:       # 默认起点 = 满级最优路线（可用"全不选"清空）
                self._seed_traits_from_route()
                return                       # _seed 里已经刷新过预览
        else:
            self.frm_traits.grid_remove()
            self.tree_mio.grid()
            self.spin_level.configure(state="normal")
        self.on_preview()

    def _sync_source(self):
        if self.var_source.get() == "manual":
            self.frame_manual.grid()
        else:
            self.frame_manual.grid_remove()
        self._refresh_totals()

    def _sync_rule(self):
        if self.var_rule.get() == "手动":
            self.frm_manual_plane.grid()
        else:
            self.frm_manual_plane.grid_remove()
        self._refresh_enemy()

    def _on_enemy_change(self):
        """换对手国别 / 手填对手机型：对手数值变了，最优路线与方针也可能跟着变。"""
        self._refresh_enemy()
        self._on_inputs_affecting_plan()

    def _on_rule_change(self):
        self._sync_rule()
        self._on_inputs_affecting_plan()

    def _on_inputs_affecting_plan(self, recalc=False):
        """年份 / 距离 / 对手 / 国家精神这类输入变了：重挑方针 + 重算"推荐"那行。

        以前只有"换国家 / 改等级 / 改科技"才会重推，改**当前年份**或**对手**都不会 ——
        于是 ④ 的"推荐：…完美抛光"停在旧状态、下拉/计算却用另一套（实测都对不上）。
        这里做 400ms 防抖：连敲年份（1→19→194→1944）时只算最后一次。
        （计划缓存按输入做键，所以不需要清缓存。）
        """
        job = getattr(self, "_plan_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:                 # noqa: BLE001
                pass
        self._plan_job = self.after(400, lambda: self._apply_inputs_affecting_plan(recalc))

    def _apply_inputs_affecting_plan(self, recalc=False):
        self._plan_job = None
        # 当前年份变了 → ③ 的前置默认要跟着重算（默认 = "到当前年份为止已完成"）；
        # 以前只有换国家/改科技年份才重建，所以"切当前年份"看不到解锁变化。
        try:
            year = int(self.var_year.get())
        except (tk.TclError, ValueError):
            year = None
        if year is not None and year != getattr(self, "_tech_default_year", None):
            self._build_tech_checks()
        try:
            self._refresh_policies()
        except (Exception, SystemExit):       # noqa: BLE001
            pass
        self._recommend_org(apply_org=False)
        self._refresh_totals()
        self._refresh_alloc_recommendation()
        if recalc and getattr(self, "rows", None):
            self.on_calculate()

    def _rule_value(self):
        return dict(RULE_LABELS)[self.var_rule.get()]

    def _on_roles_changed(self):
        self._refresh_enemy()
        self._plans.clear()            # 用途变了，"满级最优"重新比较
        self._recommend_org()

    def _enemy_cfg(self):
        rule = self._rule_value()
        cfg = dict(self.inputs.get("enemy") or {})
        cfg.update({"country": self._enemy_tag(),
                    "rule": "previous_year" if rule == "manual" else rule,
                    "override_key": (self.var_override.get().strip() or None)
                                    if rule == "manual" else None})
        return cfg

    # ---------- 对手（AI）的设计商修正 / 经验 ----------
    def _enemy_auto_design(self, country=None):
        """AI 会用哪家 MIO、点哪些特质（按模组 ai_bonus_weights 自动判定）。"""
        country = country or self._enemy_tag()
        role = next((k for k, v in self.role_vars.items() if v.get()), "air_far")
        try:
            year = int(self.var_year.get())
        except (tk.TclError, ValueError):
            year = self.inputs.get("current_year") or 1939
        return engine.enemy_design(country, role, year, data=self.data)

    def _fill_enemy_mods(self):
        """把当前对手国别的『手填值』或『AI 自动判定值』填进 ② 的输入框。"""
        country = self._enemy_tag()
        hand = ((self.inputs.get("enemy") or {}).get("by_country") or {}).get(country) or {}
        design = self._enemy_auto_design(country)
        src = hand or (design or {})
        mods = src.get("modifiers") or {}
        exp = src.get("experience") or (
            {} if self.var_roles_are_carrier() else engine.ENEMY_EXPERIENCE)

        def pct(d, key):
            return "%g" % round(float(d.get(key, 0.0) or 0.0) * 100, 4)

        self._filling_enemy_mods = True       # 填值不算"用户改过"，别写回 by_country
        self.var_enemy_mod_agi.set(pct(mods, "air_agility"))
        self.var_enemy_mod_spd.set(pct(mods, "maximum_speed"))
        self.var_enemy_exp_agi.set(pct(exp, "air_agility"))
        self.var_enemy_exp_spd.set(pct(exp, "maximum_speed"))
        self._filling_enemy_mods = False
        self._enemy_mods_country = country

    def _enemy_source_text(self, picked, roles, year):
        """对手数值是哪来的：手填 / 按模组 AI 权重自动判定（写明 MIO 与机型）。"""
        country = self._enemy_tag()
        if ((self.inputs.get("enemy") or {}).get("by_country") or {}).get(country):
            return "数值来源：界面手填（优先于 AI 自动判定）｜点『恢复 AI 自动值』回到自动判定值"
        seen = {}
        for role in roles:
            plane = picked.get(role, (None, None))[0]
            design = engine.enemy_design(country, role, year, data=self.data, plane=plane)
            key = None if not design else (design["organization"], design["plane"],
                                           len(design["traits"]), design.get("fallback"))
            seen.setdefault(key, []).append(role)
        parts = []
        for key, rs in seen.items():
            label = "、".join(ROLE_SHORT.get(r, r) for r in rs)
            if key is None:
                parts.append("（%s）找不到该国空军 MIO" % label)
                continue
            org, plane_key, n, fallback = key
            parts.append("%s对手用 %s%s（%s，满级 %d 项特质）"
                         % ("" if len(roles) == 1 else "（%s）" % label,
                            "通用 " if fallback else "",
                            zh(self.loc, org) or org, zh(self.loc, plane_key) or plane_key, n))
        return ("数值来源：按模组 AI 权重自动判定（AI 按「加成总和最大」点特质，不是战斗力最优）｜"
                + "；".join(parts))

    def var_roles_are_carrier(self):
        """当前勾的用途是不是全是舰载（舰载对手不吃经验）。"""
        roles = [k for k, v in self.role_vars.items() if v.get()] or ["air_far"]
        return all(r in engine.CARRIER_ROLES for r in roles)

    def _apply_enemy_mods(self):
        """把 ② 输入框里的百分数写回 inputs.enemy.by_country[该国]。"""
        def num(var):
            try:
                return float((var.get() or "0").strip()) / 100.0
            except ValueError:
                return None                       # 还在输入中（例如只敲了 "-"）

        vals = [num(v) for v in (self.var_enemy_mod_agi, self.var_enemy_mod_spd,
                                 self.var_enemy_exp_agi, self.var_enemy_exp_spd)]
        if any(v is None for v in vals):
            return False
        country = self._enemy_tag()
        enemy = dict(self.inputs.get("enemy") or {})
        by_country = dict(enemy.get("by_country") or {})
        by_country[country] = {
            "modifiers": {"air_agility": vals[0], "maximum_speed": vals[1]},
            "experience": {"air_agility": vals[2], "maximum_speed": vals[3]},
        }
        enemy["by_country"] = by_country
        self.inputs["enemy"] = enemy
        self.lbl_enemy_src.configure(
            text="数值来源：界面手填（优先于自动判定）｜点『恢复 AI 自动值』可回到 %s 的自动判定值" % country)
        return True

    def _reset_enemy_mods(self):
        """丢掉该国的手填值，回到按模组 AI 权重自动判定的值。"""
        country = self._enemy_tag()
        enemy = dict(self.inputs.get("enemy") or {})
        by_country = dict(enemy.get("by_country") or {})
        by_country.pop(country, None)
        enemy["by_country"] = by_country
        self.inputs["enemy"] = enemy
        self._fill_enemy_mods()
        self._refresh_enemy()
        self._refresh_totals()
        if getattr(self, "rows", None):
            self.on_calculate()

    def _refresh_enemy(self):
        """对手按用途分别取：舰载用途是舰载对手（无经验加成），其余是陆基战斗机。"""
        cfg = self._enemy_cfg()
        year = int(self.var_year.get())
        roles = [k for k, v in self.role_vars.items() if v.get()] or ["air_far"]
        if getattr(self, "_enemy_mods_country", None) != self._enemy_tag():
            self._fill_enemy_mods()          # 换对手国别 → 换成该国的 AI 自动判定值
        picked = {r: engine.pick_enemy_values(self.data["airframes_all"], cfg, r, year,
                                              data=self.data)
                  for r in roles}
        keys = {e["key"] for e, _v in picked.values() if e}
        parts = []
        for role in roles:
            e, v = picked[role]
            name = zh(self.loc, e["key"]) or e["name"] if e else "（该规则下找不到机型）"
            body = name if not v else "%s 机动 %.2f 速度 %.2f" % (name, v["agility"], v["speed"])
            parts.append(body if len(keys) <= 1 else "%s：%s" % (ROLE_SHORT.get(role, role), body))
        # 对手数值是怎么来的：说清"设计商（满级特质、无方针）+ 经验"，舰载用途不计经验
        _cats, exp, mods = engine.enemy_spec(roles[0], cfg, year=year, data=self.data)
        exp_used = any((engine.enemy_spec(r, cfg, year=year, data=self.data)[1] or {})
                       for r in roles)

        def pct(source, key):
            return "%+g%%" % round((source or {}).get(key, 0.0) * 100, 2)

        note = ("　数值口径：对手 = 该国设计商修正"
                "（机动 %s / 速度 %s）%s"
                % (pct(mods, "air_agility"), pct(mods, "maximum_speed"),
                   "＋ 对手联队经验（机动 %s / 速度 %s）；「（舰载）」用途不计经验"
                   % (pct(exp, "air_agility"), pct(exp, "maximum_speed"))
                   if exp_used else "，且本用途（舰载）不计经验"))
        self.lbl_enemy_src.configure(text=self._enemy_source_text(picked, roles, year))
        self.lbl_enemy.configure(text="对手：" + "\u3000｜\u3000".join(parts) + "\n" + note)

    # ---------- 计算 ----------
    def collect(self, policy=_UNSET):
        roles = [k for k, v in self.role_vars.items() if v.get()]
        if not roles:
            raise ValueError("至少勾选一个用途")
        mods = {}
        for key, _label in MOD_FIELDS:
            raw = (self.mod_vars[key].get() or "0").strip()
            try:
                mods[key] = float(raw) / 100.0
            except ValueError:
                raise ValueError("「%s」填的不是数字：%s" % (MOD_ZH.get(key, key), raw))
        rule = self._rule_value()
        source = self.var_source.get()
        inputs = dict(self.inputs)
        inputs.update({
            "country": self._tag(),
            "current_year": int(self.var_year.get()),
            "tech_year": int(self.var_tech.get()),
            "roles": roles,
            "range_cap": float(self.var_distance.get()),
            "pareto_x": self._axis_key(self.var_axis_x.get()),
            "pareto_y": self._axis_key(self.var_axis_y.get()),
            "modifier_source": source,
            "manufacturer_mode": "manual" if source == "manual" else "traits",
            "manufacturer_modifiers": {k: v for k, v in mods.items() if v},
            "national_spirits": [s.strip() for s in self.var_spirits.get().split(",") if s.strip()],
            "unlocked_techs": [t for t, v in self.tech_vars.items() if v.get()],
            "unlocked_flags": [f for f, v in getattr(self, "flag_vars", {}).items() if v.get()],
            "efficiency_cap_now": int(self.var_cap.get()),
            "capacity_bonus_now": int(self.var_capacity.get()),
            "alloc_mode": self._alloc_mode_key(),
            "mio": {"organization": self._org_key(),
                    "level": int(self.var_level.get()),
                    "policy": (self._selected_policy_token() if policy is _UNSET else policy),
                    "manual_traits": (sorted(self.chosen_traits)
                                      if self.var_alloc.get() == "pick" else None)},
        })
        enemy = dict(inputs.get("enemy") or {})
        enemy.update({"country": self._enemy_tag(),
                      "rule": "previous_year" if rule == "manual" else rule,
                      "override_key": (self.var_override.get().strip() or None) if rule == "manual" else None})
        inputs["enemy"] = enemy
        return inputs

    def _spirit_mods(self, inputs):
        return engine.spirit_modifiers(
            self.data["national_ideas"], inputs.get("national_spirits") or [],
            categories=engine.role_idea_categories(inputs["roles"]))

    def _refresh_totals(self):
        try:
            inputs = self._with_route(self.collect())
            upgrade_map = engine.upgrades_by_key(self.data["upgrades"])
            cands = run.candidate_pool(inputs, self.data)
            mfr_mods, _info = run.resolve_manufacturer(inputs, self.data, upgrade_map, cands)
            spirit = self._spirit_mods(inputs)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            self.lbl_mio_total.configure(text=str(exc))
            self.lbl_spirit.configure(text=str(exc))
            self.lbl_overall.configure(text=str(exc))
            return
        self.lbl_mio_total.configure(text=fmt_mods(mfr_mods))
        self.lbl_spirit.configure(text=fmt_mods(spirit))
        if self.var_source.get() == "manual":
            total = engine.combine_modifiers(mfr_mods, inputs.get("extra_modifiers") or {})
        else:
            total = engine.combine_modifiers(mfr_mods, spirit,
                                             inputs.get("extra_modifiers") or {})
        self.lbl_overall.configure(text=fmt_mods(total))

    def on_preview(self):
        self.tree_mio.delete(*self.tree_mio.get_children())
        try:
            inputs = self.collect()
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            messagebox.showerror("预览出错", str(exc))
            return
        org = self._org()
        if not org:
            return
        mods = {}
        prod = {}
        override = None
        ini = org.get("initial_trait")
        if ini:
            mods = engine.combine_modifiers(mods, ini.get("bonuses") or {})
            prod = engine.combine_modifiers(prod, ini.get("production") or {})
            self.tree_mio.insert("", "end", values=("初始", zh(self.loc, ini.get("token")),
                                                    fmt_mods(ini.get("bonuses") or {})))
        pol = getattr(self, "_policy_map", {}).get(self.var_policy.get())
        if pol:
            bonus = self._policy_bonus(pol)
            mods = engine.combine_modifiers(mods, bonus)
            # 方针的生产侧有两处：production_bonus，以及 equipment_bonus 里的
            # production_cost_factor（生产产出花费——设计不计、生产要算）
            pol_prod = dict(pol.get("production_bonus") or {})
            pol_cost = (pol.get("equipment_bonus") or {}).get("production_cost_factor")
            if pol_cost:
                pol_prod = engine.combine_modifiers(pol_prod, {"production_cost_factor": pol_cost})
            prod = engine.combine_modifiers(prod, pol_prod)
            self.tree_mio.insert("", "end", values=("方针", zh(self.loc, pol["token"]),
                                                    fmt_mods(bonus)))
        if self.var_alloc.get() == "pick":
            for trait in org.get("traits", []):
                if trait.get("token") in self.chosen_traits:
                    mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
                    prod = engine.combine_modifiers(prod, trait.get("production") or {})
                    self.tree_mio.insert("", "end", values=(
                        "勾选", zh(self.loc, trait.get("token")),
                        fmt_mods(trait.get("bonuses") or {})))
            self.lbl_mio_route.configure(text="")
        else:
            level = int(self.var_level.get())
            plan = self._org_plan(org, inputs)
            if plan:
                # 显示就以**实际计算用的路线**为准（口径可能是设计最优/兼顾/分离）
                override = None
                partner_prod = None
                partner_key = None
                prod_from_calc = False
                try:
                    upgrade_map = engine.upgrades_by_key(self.data["upgrades"])
                    cands = run.candidate_pool(inputs, self.data)
                    _mm, info2 = run.resolve_manufacturer(
                        inputs, self.data, upgrade_map, cands,
                        self._ref_plane_of(inputs, cands) if cands else None)
                    if info2.get("traits"):
                        plan = {"log": info2["traits"], "route": [t["token"] for t in info2["traits"]]}
                    prod = info2.get("production") or {}
                    prod_from_calc = True          # prod 已经是"路线 + 方针"的合计，别再叠加
                    override = info2.get("production_gain_override")
                    partner = info2.get("production_partner")
                    if partner:
                        partner_key = partner.get("organization")
                        partner_prod = self._prod_of_tokens(partner.get("organization"),
                                                            partner.get("tokens") or [])
                except (Exception, SystemExit):      # noqa: BLE001
                    pass
                shown = plan["log"][:level]
                for i, item in enumerate(shown, 1):
                    mods = engine.combine_modifiers(mods, item.get("bonuses") or {})
                    if not prod_from_calc:
                        # 旧 bug：prod 已经含这条路线的生产修正，这里再加一遍 →
                        # 面板会把"表层织物覆盖"的产能 +5% 显示成 +10%（gain 也跟着虚高）。
                        prod = engine.combine_modifiers(prod, item.get("production") or {})
                    self.tree_mio.insert("", "end", values=("%d 级" % i, zh(self.loc, item["token"]),
                                                            fmt_mods(item.get("bonuses") or {})))
                self.lbl_mio_route.configure(
                    text="满级最优路线共 %d 级，当前按前 %d 级分配（低级时是满级路线的前缀）"
                         % (len(plan["log"]), len(shown)))
        self.lbl_mio_total.configure(text=fmt_mods(mods))
        gain, parts = engine.production_gain(prod, inputs.get("efficiency_cap_now", 100),
                                            inputs.get("capacity_bonus_now", 200))
        if override:
            gain, parts = float(override), {}
        if override and partner_prod is not None:
            # 「分离」：本 MIO 只做设计，生产那家才是折算的来源 —— 别把本 MIO 路线的
            # 生产修正（例如"效率增长 +15.5%"）摆在折算旁边，会让人以为它算进去了。
            body = self._prod_text(partner_prod, gain, parts).replace("生产侧：", "", 1)
            self.lbl_prod.configure(text="生产侧：本 MIO 只做设计；生产交给「%s」　%s"
                                         % (zh(self.loc, partner_key) or partner_key or "生产伙伴",
                                            body))
        else:
            self.lbl_prod.configure(text=self._prod_text(prod, gain, parts))
        # 「分离」口径：把生产那家 MIO 与它需要的特质列出来（按卡片宽度换行）
        self.lbl_partner.configure(text="")
        if inputs.get("alloc_mode") == "split":
            ref = self._ref_plane()
            partner = run.best_production_plan(inputs, self.data, ref) if ref else None
            if partner and partner["organization"] != self._org_key():
                self.lbl_partner.configure(
                    text="　生产交给「%s」（满级 %d），需点：%s"
                         % (zh(self.loc, partner["organization"]), partner.get("level", 14),
                            " → ".join(zh(self.loc, t) for t in partner["tokens"])))
            elif partner:
                self.lbl_partner.configure(
                    text="　生产：最优的一家就是本 MIO（换别家都不给产量加成）→ 用「兼顾」更合适")
            else:
                self.lbl_partner.configure(text="　生产：没有 MIO 能给产量加成")

    def _prod_of_tokens(self, org_name, tokens):
        """某 MIO + 指定特质列表的生产侧修正合计（分离口径下显示"生产伙伴"用）。"""
        org = self.by_name.get(org_name or "") or {}
        by_token = {t.get("token"): t for t in org.get("traits", [])}
        prod = {}
        ini = org.get("initial_trait")
        if ini:
            prod = engine.combine_modifiers(prod, ini.get("production") or {})
        for token in tokens:
            trait = by_token.get(token)
            if trait:
                prod = engine.combine_modifiers(prod, trait.get("production") or {})
        return prod

    @staticmethod
    def _prod_text(prod, gain=1.0, parts=None):
        """生产侧清单 + 折算结果：把生产修正换成"等效造价折扣"。

        措辞：修正本身按官方汉化叫**产量**（`production_capacity_factor`），
        折算出来的整体倍率叫**产能**（"⇒ 产能 ×gain"）。
        """
        head = "生产侧："
        if not prod:
            return head + "这条路线没有任何生产修正"
        # 每项后面直接跟它自己的折算倍率，最后给合计 —— 以前"清单 + ［分项倍率］"两遍重说
        items = []
        for key, value in sorted(prod.items()):
            if not value:
                continue
            label = PROD_ZH.get(key, key)
            # 资源需求的"自己的倍率"就是 (1+修正)：−5% ⇒ ×0.95；其余用折算分项
            factor = ((1.0 + value) if key == "production_resource_need_factor"
                      else (parts or {}).get(label, 1.0))
            items.append("%s %+g%%%s" % (label, round(value * 100, 2),
                                         " ⇒ ×%.4f" % factor if abs(factor - 1.0) > 1e-9 else ""))
        text = head + "　".join(items)
        # 合计：产能倍率（产量/效率上限/生产产出花费）与资源消耗倍率（资源需求）分列，
        # 等效造价 = (1 ÷ 合计产能) × 合计资源消耗 —— 不同方针/路线可以直接横向比。
        need_total = 1.0 + float((prod or {}).get("production_resource_need_factor", 0.0) or 0.0)
        text += "　⇒ 合计产能×%.4f，资源消耗×%.4f（等效造价 ×%.4f）" % (
            gain or 1.0, need_total, (1.0 / (gain or 1.0)) * need_total)
        return text

    def on_calculate(self):
        """只计算并在界面里展示（不写文件）。"""
        try:
            inputs = self._with_route(self.collect())
            _dbg("计算：年份 %s/%s｜国家 %s｜用途 %s｜距离 %s｜来源 %s"
                 % (inputs["current_year"], inputs["tech_year"], inputs["country"],
                    ",".join(inputs["roles"]), inputs["range_cap"],
                    inputs.get("modifier_source")))
            _dbg("  解锁科技 %d 项｜国家标识 %d 项｜国家精神 %s"
                 % (len(inputs.get("unlocked_techs") or []),
                    len(inputs.get("unlocked_flags") or []),
                    ",".join(inputs.get("national_spirits") or []) or "（无）"))
            _dbg("  MIO=%s 等级=%s 方针=%s 候选池=%d"
                 % ((inputs.get("mio") or {}).get("organization"),
                    (inputs.get("mio") or {}).get("level"),
                    (inputs.get("mio") or {}).get("policy"),
                    len(run.candidate_pool(inputs, self.data))))
            import time as _t
            _t0 = _t.time()
            rows, player_mods, enemy, enemy_values, mfr_info = run.build_rows(inputs, self.data)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            messagebox.showerror("计算出错", str(exc))
            return
        _dbg("  计算完成：%d 行，用时 %.2fs" % (len(rows), _t.time() - _t0))
        _dbg("  对手=%s（机动 %.2f 速度 %.2f）｜制造商来源=%s"
             % ((enemy or {}).get("name"), (enemy_values or {}).get("agility", 0),
                (enemy_values or {}).get("speed", 0),
                json.dumps(mfr_info, ensure_ascii=False)[:160]))
        for r in rows[:3]:
            _dbg("  第%d名 %s  总分数 %.4f  性能分数 %.1f  造价 %.2f  %s"
                 % (r["rank"], r["airframe"]["name"], r["score"],
                    r["score"] * r["effective_cost"], r["effective_cost"], r["design"]))
        self._last = (inputs, rows, player_mods, enemy, enemy_values, mfr_info)
        self.rows = rows
        self._refresh_totals()
        self.lbl_overall.configure(text=fmt_mods(player_mods))
        self._render_rows()
        self.lbl_hint.configure(text="已计算 %d 行；需要写文件时点「导出 Excel」" % len(rows))

    def on_export(self):
        """把当前结果写成工作簿；没算过就先算一次。"""
        if not getattr(self, "_last", None):
            self.on_calculate()
            if not getattr(self, "_last", None):
                return
        inputs, rows, player_mods, enemy, enemy_values, mfr_info = self._last
        try:
            run.write_workbook(run.DEFAULT_OUT, inputs, rows, player_mods, enemy, enemy_values,
                               mfr_info)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            messagebox.showerror("导出出错", str(exc))
            return
        _dbg("导出：%s（%d 行）" % (run.DEFAULT_OUT, len(rows)))
        self.lbl_hint.configure(text="已导出 → %s" % os.path.basename(run.DEFAULT_OUT))

    def _axis_key(self, label):
        for key, text in AXIS_CHOICES:
            if text == label:
                return key
        return key

    def _row_name(self, row):
        return zh(self.loc, row["airframe"]["key"]) or row["airframe"]["name"]

    def _sort_value(self, row):
        key = getattr(self, "_sort_key", "rank")
        getters = {
            "role": lambda r: r["role"], "rank": lambda r: r["rank"],
            "pareto": lambda r: 1 if r.get("pareto") else 0,
            "plane": self._row_name, "effect": lambda r: r["score"] * r["effective_cost"],
            "pure": lambda r: r["score"], "cost": lambda r: r["effective_cost"],
            "year": lambda r: r["airframe"].get("year") or 0,
            "weighted": lambda r: r["weighted"], "design": lambda r: r["design"],
        }
        return getters.get(key, lambda r: r["rank"])(row)

    def _watch_inputs(self):
        """调试用：任何输入项变化都打一行日志，方便还原用户操作序列。"""
        last = {}

        def watch(var, label):
            def on_change(*_a):
                if getattr(self, "_filling_enemy_mods", False):
                    return          # 预设填值不是用户操作，别记成"操作"
                val = var.get()
                if last.get(label) == val:
                    return          # Tk 写入同值也会触发，这里去重
                last[label] = val
                _dbg("操作：%s → %s" % (label, val))

            last[label] = var.get()
            var.trace_add("write", on_change)

        for var, label in ((self.var_year, "改当前年份"), (self.var_tech, "改飞机科技年份"),
                           (self.var_tag, "改国家"), (self.var_enemy_tag, "改对手国别"),
                           (self.var_rule, "改对手选取规则"), (self.var_distance, "改距离目标"),
                           (self.var_level, "改 MIO 等级"), (self.var_org, "改军工组织"),
                           (self.var_policy, "改方针"), (self.var_source, "改修正来源"),
                           (self.var_alloc, "改配点方式"), (self.var_spirits, "改国家精神"),
                           (self.var_override, "改手动机型"),
                           (self.var_enemy_mod_agi, "改对手设计商机动"),
                           (self.var_enemy_mod_spd, "改对手设计商速度"),
                           (self.var_enemy_exp_agi, "改对手经验机动"),
                           (self.var_enemy_exp_spd, "改对手经验速度")):
            watch(var, label)
        for key, rv in self.role_vars.items():
            watch(rv, "勾选用途 %s" % ROLE_SHORT.get(key, key))
        for var, label in ((self.var_filter, "改机型筛选"), (self.var_f_year, "改年份筛选"),
                           (self.var_f_role, "改用途筛选"), (self.var_f_pareto, "改帕累托筛选"),
                           (self.var_axis_x, "改 X 轴"), (self.var_axis_y, "改 Y 轴")):
            watch(var, label)

    def _bind_live_refresh(self):
        """补齐"改了就立刻生效"的输入。

        Spinbox 的 `command=` 只在按上下箭头时触发，**直接键入年份不会触发**，
        于是出现过：debug 里对手已经是 Bf 109 G-14，② 那行还写着 109 D（旧年份的对手）。
        """
        def on_year(*_a):
            try:
                int(self.var_year.get())
            except (tk.TclError, ValueError):
                return                     # 还在输入中（例如只敲了 "19"）
            self._refresh_enemy()
            self._on_inputs_affecting_plan()   # 年份变了：重推路线与方针，别让下拉停在旧值

        self.var_year.trace_add("write", on_year)

        # 生产折算的两个输入：改了要重算，但**必须防抖** —— 以前每敲一个字符
        # （例如输入 118 时先敲出 "1"）就整套重算，冷路径下要卡 2 秒以上。
        def on_prod(*_a):
            try:
                int(self.var_cap.get())
                int(self.var_capacity.get())
            except (tk.TclError, ValueError):
                return
            self._on_inputs_affecting_plan(recalc=True)   # 带 400ms 防抖

        for var in (self.var_cap, self.var_capacity):
            var.trace_add("write", on_prod)

        # 对手修正/经验：改了立刻写回 by_country 并重算对手（写不进去 = 还在输入中）
        def on_enemy_mods(*_a):
            if getattr(self, "_filling_enemy_mods", False):
                return
            if self._apply_enemy_mods():
                self._refresh_enemy()
                if getattr(self, "rows", None):
                    self.on_calculate()

        for var in (self.var_enemy_mod_agi, self.var_enemy_mod_spd,
                    self.var_enemy_exp_agi, self.var_enemy_exp_spd):
            var.trace_add("write", on_enemy_mods)

    def _sort_by(self, cid):
        if getattr(self, "_sort_key", None) == cid:
            self._sort_desc = not getattr(self, "_sort_desc", True)
        else:
            self._sort_key, self._sort_desc = cid, True
        _dbg("排序：按 %s %s" % (cid, "降序" if self._sort_desc else "升序"))
        self._render_rows()

    def _show_design(self):
        """表格下方（散点图上方）：选中行的明细，按【块】排版，方便扫读。"""
        for child in self.frm_design.winfo_children():
            child.destroy()
        sel = self.tree_out.selection()
        if not sel:
            return
        values = self.tree_out.item(sel[0])["values"]
        if not values:
            return
        row = getattr(self, "_row_by_iid", {}).get(sel[0])
        v = (row or {}).get("values") or {}
        blocks = [("推荐改装", "%s：%s" % (values[3], values[-1]), "normal")]
        if v:
            blocks.extend(self._design_blocks(v))
            blocks.append(("", "", "sep"))
            lines = engine.score_breakdown(row["role"], v, row.get("effective_cost"))
            blocks.append(("性能分数", lines[0].replace("性能分数 ", "", 1), "formula"))
            blocks.extend(("", text.lstrip("　"), "note") for text in lines[1:])
            if row.get("production_gain") and abs(row["production_gain"] - 1.0) > 1e-9:
                blocks.append(("生产折算", "×%.4f　⇒　总分数 %.2f → %.2f（= 性能 ÷ 等效造价 %.2f）"
                               % (row["production_gain"], row.get("score_raw", 0.0),
                                  row["score"],
                                  row.get("effective_cost", 0.0) / row["production_gain"]),
                               "formula"))
            # 资源加权分：把算式摊开（分子 = 纯设计分，分母 = 装配资源 ×(1+资源需求)）
            need = (row.get("production") or {}).get("production_resource_need_factor", 0.0)
            res_cost = (row.get("airframe") or {}).get("air_production") or 0
            if res_cost and row.get("weighted"):
                blocks.append(("资源加权分",
                               "%.4f = 折算后总分数 %.4f ÷ （装配资源 %g × 资源消耗 %.4f）"
                               % (row["weighted"], row.get("score", 0.0), res_cost,
                                  1.0 + float(need or 0.0)),
                               "formula"))
            combat = engine.combat_breakdown(row["role"], v, row.get("enemy_values"))
            if combat:
                blocks.append(("", "", "sep"))
                blocks.append(("战斗比值", combat[0].replace("战斗比值 ", "", 1), "formula"))
                blocks.extend(("", text.lstrip("　"), "note") for text in combat[1:])
        self._render_design_blocks(blocks)

    def _design_blocks(self, v):
        """明细的前两块：① 这些改装改了哪些属性；② 最终**设计数值**（对照游戏「设计」界面）。

        注意：设计数值 = 基础 ×(1+军工组织+国家精神+改装) + 改装增量，
        **不含联队经验与王牌**——所以拿它和游戏「设计」界面比对是能对上的。
        """
        def name(key):
            return MOD_ZH.get(key) or zh(self.loc, key) or key

        out = []
        coef, add = v.get("upgrade_coef") or {}, v.get("upgrade_add") or {}
        parts = []
        for key in DESIGN_SHOW:
            if not (coef.get(key) or add.get(key)):
                continue
            bits = []
            if coef.get(key):
                bits.append("%+.2f%%" % (coef[key] * 100))
            if add.get(key):
                bits.append("%+g" % add[key])
            parts.append("%s %s" % (name(key), " 且 ".join(bits)))
        if parts:
            out.append(("改装属性", " ｜ ".join(parts), "normal"))

        dv, parts = v.get("design_values") or {}, []
        cap = v.get("range_cap")
        for key in DESIGN_SHOW:
            if key not in dv:
                continue
            value = dv[key]
            if key in ("air_ground_attack", "naval_strike_attack",
                       "naval_strike_targetting") and not value:
                continue                      # 这个用途用不上的属性不占地方
            if key == "air_range" and cap and value > cap:
                parts.append("%s %s（设计 %s，按目标截断）"
                             % (name(key), engine.fmt_num(cap), engine.fmt_num(value)))
                continue
            text = engine.fmt_num(value, 4) if abs(value) < 1 else engine.fmt_num(value)
            parts.append("%s %s" % (name(key), text))
        if parts:
            out.append(("设计数值", " ｜ ".join(parts), "normal"))
            out.append(("", "以上都是设计加成（不含经验与王牌），与游戏「设计」界面一致", "note"))
        return out

    def _render_design_blocks(self, blocks):
        """把 (块名, 内容, 样式) 列表画成两栏小表：左列块名（加粗深蓝），右列内容。"""
        styles = {
            "header": dict(foreground=ACCENT, font=(self.family, BODY - 2, "bold")),
            "normal": dict(foreground="#333333", font=(self.family, BODY - 1)),
            "formula": dict(foreground="#1F4E79", font=(self.family, BODY - 1)),
            "note": dict(foreground="#6B7280", font=(self.family, BODY - 2)),
        }
        r = 0
        for header, text, kind in blocks:
            if kind == "sep":
                ttk.Separator(self.frm_design, orient="horizontal").grid(
                    row=r, column=0, columnspan=2, sticky="ew", pady=3)
                r += 1
                continue
            if header:
                ttk.Label(self.frm_design, text=header, anchor="ne",
                          **styles["header"]).grid(row=r, column=0, sticky="ne", padx=(0, 8))
            label = ttk.Label(self.frm_design, text=text, justify="left", anchor="w",
                              **styles.get(kind, styles["normal"]))
            label.grid(row=r, column=1, sticky="w", pady=1)
            self._wrap_to_card(label, self.frm_design)
            r += 1

    def _render_rows(self):
        """按当前 X/Y 轴重算帕累托标记，套用筛选与排序后刷新表格和散点图。

        注意：帕累托是**在全部候选上**判定的（筛选只影响显示，不改变谁被支配）。
        """
        self.tree_out.delete(*self.tree_out.get_children())
        if not self.rows:
            self.lbl_pareto.configure(text="")
            return
        x_key, y_key = self._axis_key(self.var_axis_x.get()), self._axis_key(self.var_axis_y.get())
        run.pareto_front(self.rows, x_key, y_key)

        view = list(self.rows)
        # 年份下拉按当前候选动态生成
        years = sorted({str(r["airframe"].get("year")) for r in self.rows if r["airframe"].get("year")})
        self.cb_f_year.configure(values=["全部"] + years)
        roles = []
        for r in self.rows:
            label = ROLE_SHORT.get(r["role"], r["role"])
            if label not in roles:
                roles.append(label)
        self.cb_f_role.configure(values=["全部"] + roles)

        if self.var_f_role.get() != "全部":
            view = [r for r in view
                    if ROLE_SHORT.get(r["role"], r["role"]) == self.var_f_role.get()]
        if self.var_f_year.get() != "全部":
            view = [r for r in view if str(r["airframe"].get("year")) == self.var_f_year.get()]
        mode = self.var_f_pareto.get()
        if mode == "只看前沿":
            view = [r for r in view if r.get("pareto")]
        elif mode == "只看被支配":
            view = [r for r in view if not r.get("pareto")]
        keyword = (self.var_filter.get() or "").strip().lower()
        if keyword:
            view = [r for r in view
                    if keyword in (self._row_name(r) + " " + r["airframe"]["name"]).lower()]
        view.sort(key=self._sort_value, reverse=getattr(self, "_sort_desc", True))

        dist = int(self.var_distance.get())
        self._row_by_iid = {}
        for row in view:
            iid = self.tree_out.insert("", "end", values=(
                "%s@%d" % (ROLE_SHORT.get(row["role"], ROLE_LABELS[row["role"]]), dist), row["rank"],
                "★" if row.get("pareto") else "",
                self._row_name(row),
                "{:,.2f}".format(row["score"]),
                # 性能分数 = 纯设计分 × 造价（**不乘生产折算**，与明细/设计口径一致）；
                # 生产折算只体现在"总分数"与资源加权分上。
                "{:,.1f}".format(row.get("score_raw", row["score"]) * row["effective_cost"]),
                "%.2f" % row["effective_cost"],
                row["airframe"].get("year", ""),
                "{:,.2f}（装配 {}）".format(row["weighted"],
                                           row["airframe"].get("air_production", 0)),
                row["design"]))
            self._row_by_iid[iid] = row
        star = sum(1 for r in self.rows if r.get("pareto"))
        self.lbl_pareto.configure(
            text="帕累托前沿：%d / %d 架（X = %s，Y = %s，同一用途内比较；● 前沿，○ 被支配）"
                 "　显示 %d 行" % (star, len(self.rows), self.var_axis_x.get(),
                                 self.var_axis_y.get(), len(view)))
        self._show_design()
        self._draw_chart()

    # ---------- 散点图 ----------
    def _draw_chart(self):
        """画当前 X/Y 轴的散点图并高亮帕累托前沿。

        两轴都按**真实数值方向**画（造价不翻转，免得看迷糊），
        方向提示写在轴标题上（← 越小越好 / → 越大越好）。
        """
        cv = getattr(self, "canvas_plot", None)
        if cv is None:
            return
        cv.delete("all")
        if not self.rows:
            return
        width, height = cv.winfo_width(), cv.winfo_height()
        if width < 160 or height < 90:
            return

        x_key = self._axis_key(self.var_axis_x.get())
        y_key = self._axis_key(self.var_axis_y.get())
        xget, xhigh = run.AXIS_DEFS[x_key][1], run.AXIS_DEFS[x_key][2]
        yget, yhigh = run.AXIS_DEFS[y_key][1], run.AXIS_DEFS[y_key][2]
        pts = [(row, xget(row), yget(row)) for row in self.rows]

        def limits(vals):
            lo, hi = min(vals), max(vals)
            if hi - lo < 1e-9:
                lo, hi = lo - 1.0, hi + 1.0
            pad = (hi - lo) * 0.08
            return lo - pad, hi + pad

        x0, x1 = limits([p[1] for p in pts])
        y0, y1 = limits([p[2] for p in pts])
        left, right, top, bottom = 68, 18, 30, 52
        pw, ph = width - left - right, height - top - bottom

        def px(v):
            return left + (v - x0) / (x1 - x0) * pw

        def py(v):
            return height - bottom - (v - y0) / (y1 - y0) * ph

        def tick(value, year_axis):
            """紧凑刻度：年份给整数，大数用「万」，避免挤掉画布。"""
            if year_axis:
                return "%d" % round(value)
            if abs(value) >= 10000:
                return "%.1f万" % (value / 10000.0)
            return "%.0f" % value

        cv.create_line(left, top - 10, left, height - bottom, fill="#8A93A5")
        cv.create_line(left, height - bottom, width - right, height - bottom, fill="#8A93A5")
        x_year, y_year = x_key == "year", y_key == "year"
        cv.create_text((left + width - right) / 2, height - bottom + 30, fill="#5A6472",
                       font=(self.family, BODY - 2), text="%s（%s）"
                       % (self.var_axis_x.get(), "→ 越大越好" if xhigh else "← 越小越好"))
        # 纵轴标题竖排（angle=90）放在最左侧，避免横向挤占绘图区
        cv.create_text(16, (top + height - bottom) / 2, angle=90, fill="#5A6472",
                       font=(self.family, BODY - 2), text="%s（%s）"
                       % (self.var_axis_y.get(), "越高越好 ↑" if yhigh else "越低越好 ↓"))
        for i in range(5):
            fx = x0 + (x1 - x0) * i / 4
            fy = y0 + (y1 - y0) * i / 4
            cv.create_text(px(fx), height - bottom + 11, text=tick(fx, x_year),
                           fill="#5A6472", font=(self.family, BODY - 3))
            cv.create_text(left - 6, py(fy), anchor="e", text=tick(fy, y_year),
                           fill="#5A6472", font=(self.family, BODY - 3))
            cv.create_line(px(fx), height - bottom, px(fx), height - bottom + 3, fill="#8A93A5")
            cv.create_line(left - 3, py(fy), left, py(fy), fill="#8A93A5")

        for i, (row, tx, ty) in enumerate(pts):
            cx, cy = px(tx), py(ty)
            if row.get("pareto"):
                cv.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=ACCENT, outline=ACCENT)
                name = self._row_name(row).split()[-1]
                cv.create_text(cx + 7, cy + (-12 if i % 2 == 0 else 12), anchor="w", text=name,
                               fill=ACCENT, font=(self.family, BODY - 3, "bold"))
            else:
                cv.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#B9C2D0", outline="#B9C2D0")


if __name__ == "__main__":
    if not os.environ.get("DISPLAY") and os.name != "nt":
        print("警告：DISPLAY 为空，图形界面无法显示。若在 WSL 里，请确认 WSLg 正常"
              "（可先试 wsl --shutdown 再重开）。", file=sys.stderr)
    _maybe_reexec()
    _say("启动中…正在加载数据与构建界面")
    App().mainloop()
