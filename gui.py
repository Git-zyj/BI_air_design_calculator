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
AIR_EQ_TOKENS = ("mio_cat_eq_all_small_plane", "mio_cat_eq_all_medium_plane",
                 "mio_cat_eq_all_heavy_plane", "mio_cat_eq_only_light_fighter",
                 "mio_cat_eq_all_close_air_support", "mio_cat_eq_all_cv_aircraft",
                 "plane_equipment", "aircraft_organization")
# 对手规则：界面用中文，内部映射到引擎取值
RULE_LABELS = [("当前年份−1", "previous_year"), ("当前年份", "same_year"), ("手动", "manual")]
# 距离目标（= 航程上限）：600 起，每 300 一档，最高 3600；默认 900
DISTANCES = list(range(600, 3601, 300))
DEFAULT_DISTANCE = 900
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


def is_air_mio(org, by_name):
    types = list(org.get("equipment_types") or [])
    for inc in org.get("includes") or []:
        src = by_name.get(inc)
        if src:
            types += list(src.get("equipment_types") or [])
    joined = " ".join(types)
    return any(tok in joined for tok in AIR_EQ_TOKENS)


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
        """累计标签按卡片实际宽度换行：只有文本快超出时才折行。"""
        def on_conf(event):
            width = max(event.width - WRAP_RESERVE, 240)
            try:
                cur = int(label.cget("wraplength"))
            except (TypeError, ValueError):
                cur = -1
            if cur != width:
                label.configure(wraplength=width)
        container.bind("<Configure>", on_conf, add="+")

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
        for i, (key, label) in enumerate(ROLE_CHOICES):
            v = tk.BooleanVar(value=key in cur_roles)
            self.role_vars[key] = v
            ttk.Checkbutton(box, text=label, variable=v,
                            command=self._on_roles_changed).grid(
                row=0, column=1 + i, sticky="w", padx=(0, PADX), pady=PADY)
        ttk.Label(box, text="用途").grid(row=0, column=0, sticky="e", padx=(PADX, 4), pady=PADY)
        ttk.Label(box, text="距离目标").grid(row=0, column=5, sticky="e", padx=(PADX, 4))
        self.var_distance = tk.StringVar(
            value=str(int(self.inputs.get("range_cap") or DEFAULT_DISTANCE)))
        dbox = ttk.Combobox(box, textvariable=self.var_distance, width=8, state="readonly",
                            values=DISTANCES)
        dbox.grid(row=0, column=6, sticky="w")
        dbox.bind("<<ComboboxSelected>>", lambda e: self._refresh_totals())
        ttk.Label(box, text="（= 航程上限，600 起每 300 一档）").grid(row=0, column=7, sticky="w")
        row += 1

        # ② 年份 + 所选国家与主要对手（先定国家和年份，后面才谈前置科技）
        box = self._card(row, "② 年份 + 所选国家与主要对手")
        self.var_year = tk.IntVar(value=self.inputs["current_year"])
        self.var_tech = tk.IntVar(value=self.inputs["tech_year"])
        ttk.Label(box, text="当前年份").grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
        ttk.Spinbox(box, from_=1936, to=1948, textvariable=self.var_year, width=6,
                    command=self._refresh_enemy).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="（决定对手机型）").grid(row=0, column=2, sticky="w")
        ttk.Label(box, text="飞机科技年份").grid(row=0, column=3, sticky="e", padx=PADX)
        ttk.Spinbox(box, from_=1936, to=1948, textvariable=self.var_tech, width=6,
                    command=self._on_tech_year_changed).grid(row=0, column=4, sticky="w")
        ttk.Label(box, text="（决定我方可用机身，可超前研究）").grid(row=0, column=5, sticky="w")

        ttk.Label(box, text="所选国家 tag").grid(row=1, column=0, sticky="e",
                                               padx=(PADX, 4), pady=PADY)
        self.var_tag = tk.StringVar(value=self.inputs.get("country") or "SOV")
        cb = ttk.Combobox(box, textvariable=self.var_tag, width=10,
                          state="readonly")
        cb.grid(row=1, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_country())
        cb.configure(values=[self._tag_labels[t] for t in self.tags])
        self.var_tag.set(self._tag_labels.get(self.inputs.get("country") or "SOV", "苏联"))
        ttk.Label(box, text="对手国别").grid(row=1, column=2, sticky="e", padx=(PADX, 4))
        enemy = self.inputs.get("enemy") or {}
        self.var_enemy_tag = tk.StringVar(value=enemy.get("country", "GER"))
        eb = ttk.Combobox(box, textvariable=self.var_enemy_tag, width=10,
                          state="readonly")
        eb.grid(row=1, column=3, sticky="w")
        eb.bind("<<ComboboxSelected>>", lambda e: self._refresh_enemy())
        eb.configure(values=[self._tag_labels[t] for t in self.tags])
        self.var_enemy_tag.set(self._tag_labels.get(enemy.get("country", "GER"), "德国"))
        ttk.Label(box, text="选取规则").grid(row=1, column=4, sticky="e", padx=(PADX, 4))
        cur_rule = dict(RULE_LABELS).get(enemy.get("rule", "previous_year"), "当前年份−1")
        self.var_rule = tk.StringVar(value=cur_rule)
        rb = ttk.Combobox(box, textvariable=self.var_rule, values=[l for l, _ in RULE_LABELS],
                          width=12, state="readonly")
        rb.grid(row=1, column=5, sticky="w")
        rb.bind("<<ComboboxSelected>>", lambda e: self._sync_rule())

        self.frm_manual_plane = ttk.Frame(box)
        self.frm_manual_plane.grid(row=2, column=0, columnspan=6, sticky="w")
        ttk.Label(self.frm_manual_plane, text="手动指定机型 key").grid(row=0, column=0, sticky="e",
                                                                      padx=(PADX, 4))
        self.var_override = tk.StringVar(value=enemy.get("override_key") or "")
        ov = ttk.Entry(self.frm_manual_plane, textvariable=self.var_override, width=46)
        ov.grid(row=0, column=1, sticky="w")
        ov.bind("<FocusOut>", lambda e: self._refresh_enemy())

        self.lbl_enemy = ttk.Label(box, text="", foreground=ACCENT, font=(self.family, BODY, "bold"))
        self.lbl_enemy.grid(row=3, column=0, columnspan=6, sticky="w", padx=PADX, pady=(0, PADY))
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
        ttk.Label(card, text="等级").grid(row=1, column=2, sticky="e", padx=(PADX, 4))
        self.spin_level = ttk.Spinbox(card, from_=0, to=14, textvariable=self.var_level, width=6,
                                      command=self._on_level_changed)
        self.spin_level.grid(row=1, column=3, sticky="w")
        ttk.Label(card, text="方针").grid(row=2, column=0, sticky="e", padx=(PADX, 4))
        self.var_policy = tk.StringVar(value="（不选）")
        self.cb_policy = ttk.Combobox(card, textvariable=self.var_policy, width=26, state="readonly")
        self.cb_policy.grid(row=2, column=1, sticky="w")
        self.cb_policy.bind("<<ComboboxSelected>>", lambda e: self._on_policy_change())
        self.lbl_policy = ttk.Label(card, text="", foreground="#5A6472",
                                    font=(self.family, BODY - 2), justify="left")
        self.lbl_policy.grid(row=2, column=2, columnspan=4, sticky="w", padx=PADX)
        self.lbl_mio_route = ttk.Label(card, text="", foreground="#5A6472",
                                       font=(self.family, BODY - 2), justify="left")
        self.lbl_mio_route.grid(row=3, column=0, columnspan=6, sticky="w", padx=PADX)
        ttk.Button(card, text="预览军工组织总加成", command=self.on_preview).grid(
            row=1, column=4, sticky="w",
                                                                      padx=PADX)
        self.lbl_mio_total = ttk.Label(card, text="", foreground=ACCENT,
                                       font=(self.family, BODY, "bold"), justify="left")
        self.lbl_mio_total.grid(row=1, column=5, sticky="w", padx=PADX)
        self._wrap_to_card(self.lbl_mio_total, card)

        self.tree_mio = ttk.Treeview(card, columns=("lvl", "trait", "bonus"),
                                     show="headings", height=5)
        for cid, text, w, anchor in (("lvl", "等级", 60, "center"), ("trait", "特质", 340, "w"),
                                     ("bonus", "该特质加成", 420, "w")):
            self.tree_mio.heading(cid, text=text)
            self.tree_mio.column(cid, width=w, anchor=anchor)
        self.tree_mio.grid(row=4, column=0, columnspan=6, sticky="ew", padx=PADX, pady=(0, PADY))

        self.frm_traits = ttk.Frame(card)
        self.frm_traits.grid(row=5, column=0, columnspan=6, sticky="ew", padx=PADX, pady=(0, PADY))
        self.lbl_traits_hint = ttk.Label(
            self.frm_traits, text="点击行勾选/取消（初始特质已默认计入，不需要勾）")
        self.lbl_traits_hint.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.tree_traits = ttk.Treeview(self.frm_traits,
                                        columns=("sel", "trait", "bonus", "req"),
                                        show="headings", height=6)
        for cid, text, w, anchor in (("sel", "选中", 50, "center"), ("trait", "特质", 300, "w"),
                                     ("bonus", "加成", 360, "w"), ("req", "前提 / 互斥", 330, "w")):
            self.tree_traits.heading(cid, text=text)
            self.tree_traits.column(cid, width=w, anchor=anchor)
        self.tree_traits.grid(row=1, column=0, sticky="ew")
        self.tree_traits.bind("<Button-1>", self._on_trait_click)
        sb = ttk.Scrollbar(self.frm_traits, orient="vertical", command=self.tree_traits.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.tree_traits.configure(yscrollcommand=sb.set)
        row += 1

        # ⑤ 国家精神加成
        box = self._card(row, "⑤ 国家精神加成")
        ttk.Label(box, text="国家精神（逗号分隔，可空）").grid(row=0, column=0, sticky="e",
                                                              padx=(PADX, 4), pady=PADY)
        self.var_spirits = tk.StringVar(value=",".join(self.inputs.get("national_spirits") or []))
        ttk.Entry(box, textvariable=self.var_spirits, width=64).grid(row=0, column=1, sticky="w")
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
        ttk.Button(bar, text="计算", command=self.on_calculate).pack(side="left")
        ttk.Button(bar, text="导出 Excel", command=self.on_export).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="输出：%s" % run.DEFAULT_OUT).pack(side="left", padx=PADX)
        ttk.Label(bar, text="　帕累托图").pack(side="left", padx=(PADX, 4))
        ttk.Label(bar, text="X 轴").pack(side="left")
        self.var_axis_x = tk.StringVar(value=AXIS_LABELS.get(self.inputs.get("pareto_x") or "cost",
                                                            AXIS_LABELS["cost"]))
        ttk.Combobox(bar, textvariable=self.var_axis_x, width=18, state="readonly",
                     values=[label for _k, label in AXIS_CHOICES]).pack(side="left", padx=4)
        ttk.Label(bar, text="Y 轴").pack(side="left", padx=(PADX, 0))
        self.var_axis_y = tk.StringVar(value=AXIS_LABELS.get(self.inputs.get("pareto_y") or "score",
                                                            AXIS_LABELS["score"]))
        ttk.Combobox(bar, textvariable=self.var_axis_y, width=18, state="readonly",
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
        # 表格单元格不能换行，所以选中行时在下方用可换行标签显示完整改装
        self.lbl_design = ttk.Label(card, text="", foreground="#333333", justify="left",
                                    font=(self.family, BODY - 1))
        self.lbl_design.grid(row=4, column=0, sticky="w", padx=PADX, pady=(0, 2))
        self._wrap_to_card(self.lbl_design, card)
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
                if not self._has_design_bonus(pol):
                    continue          # 只给生产加成的方针不产生设计需求，其科技也不必列
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
        saved = self.inputs.get("unlocked_techs")
        if saved is None:
            # 没存过就按"当前年份为止已完成"给默认（示例默认 1939 → 勾到 1939 的科技）
            years = self.data.get("tech_years") or {}
            year = int(self.inputs.get("current_year") or 1939)
            unlocked = {t for t in self._relevant_techs()
                        if (years.get(t) or 9999) <= year}
        else:
            unlocked = set(saved)
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
            if not self._has_design_bonus(pol):
                continue          # 无设计侧加成的方针不进用途标注
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
                float(inputs.get("range_cap") or 0),
                json.dumps(inputs.get("experience") or {}, sort_keys=True),
                inputs.get("country"))

    def _policies_for_org(self, org, techs):
        """该军工组织可用且科技已满足的方针。"""
        types = self._policy_types(org)
        out = [None]                       # None = 不选方针
        for pol in self.data.get("policies") or []:
            if not self._has_design_bonus(pol):
                continue              # 只给生产加成的方针（如模块化装配、推进系统实验组）不列
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
    def _has_design_bonus(pol):
        """方针是否带"设计侧"装备加成——只有生产产出花费、或干脆没加成的方针不列。"""
        if not pol:
            return False
        return any(v for k, v in (pol.get("equipment_bonus") or {}).items()
                   if k != "production_cost_factor")

    def _plan_context(self, inputs):
        """(参考机型, upgrade_map, 对手机动速度, 事故系数, score_key)——算一次给多处用。"""
        upgrade_map = engine.upgrades_by_key(self.data["upgrades"])
        pool = run.candidate_pool(inputs, self.data)
        if not pool:
            return None
        ref = max(pool, key=lambda a: (a.get("year") or 0))
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
        """满级 + 最佳方针下的配点路线（带缓存，界面只是读取）。

        先用"参考机型无改装"的分数挑方针（便宜），再为选中的方针跑一次贪心拿路线。
        """
        key = self._plan_key(inputs)
        cache = self._plans.setdefault(key, {})
        if org["organization"] in cache:
            return cache[org["organization"]]
        plan = None
        ctx = self._plan_context(inputs)
        _dbg("MIO 路线：%s（方针候选 %d 个，缓存%s）"
             % (org["organization"], len(self._policies_for_org(org, set(inputs.get("unlocked_techs") or []))),
                "命中" if org["organization"] in cache else "未命中"))
        if ctx:
            ref, upgrade_map, enemy_values, acc, score_key, tokens = ctx
            techs = set(inputs.get("unlocked_techs") or [])
            ini = org.get("initial_trait")
            ini_mods = engine.combine_modifiers(ini.get("bonuses") if ini else {})
            best = None
            for pol in self._policies_for_org(org, techs):
                start = engine.combine_modifiers(ini_mods, self._policy_bonus(pol))
                score = engine.evaluate(ref, {t: 0 for t in tokens}, upgrade_map, start,
                                        enemy_values, inputs.get("range_cap"),
                                        inputs.get("experience"),
                                        accident_factor=acc)[2][score_key]
                if best is None or score > best[0]:
                    best = (score, pol, start)
            if best:
                _proxy, pol, start = best
                # 满级配点用穷举求全局最优（贪心会陷局部最优），再取前 level 步
                _chosen, mods, log = engine.pick_mio_traits_exact(
                    org, engine.MIO_MAX_LEVEL, ref, upgrade_map, start, enemy_values,
                    inputs["roles"], inputs.get("range_cap"), inputs.get("experience"),
                    techs=inputs.get("unlocked_techs") or [])
                score = engine.evaluate(ref, {t: 0 for t in tokens}, upgrade_map, mods,
                                        enemy_values, inputs.get("range_cap"),
                                        inputs.get("experience"),
                                        accident_factor=acc)[2][score_key]
                plan = {"score": score, "policy": pol["token"] if pol else None,
                        "mods": mods, "start": start, "log": log,
                        "route": [item["token"] for item in log]}
        cache[org["organization"]] = plan
        return plan

    def _recommend_org(self):
        """"满级 + 方针"下比较各军工组织，把最优的设为默认。"""
        try:
            inputs = self.collect()
        except (Exception, SystemExit):  # noqa: BLE001
            return
        orgs = self._air_orgs()[0]
        scored = []
        for org in orgs:
            plan = self._org_plan(org, inputs)
            if plan:
                scored.append((org, plan))
        scored.sort(key=lambda item: -item[1]["score"])
        if scored:
            best, best_plan = scored[0]
            label = next((l for l, k in self._org_keys.items() if k == best["organization"]), None)
            if label:
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
        else:
            self.lbl_org_rec.configure(text="推荐：（暂无可比较的军工组织）")
        self._on_org_change()

    def _air_orgs(self):
        """能用于战斗机的军工组织：优先本国独特 MIO；本国没有才回退默认 MIO。"""
        tag = self._tag()
        own = [o for o in self.data["mio"]
               if os.path.basename(o.get("file", "")).upper().startswith(tag + "_")
               and is_air_mio(o, self.by_name)]
        own.sort(key=lambda o: o["organization"])
        if own:
            return own, False
        generic = [o for o in self.data["mio"]
                   if os.path.basename(o.get("file", "")) == "00_generic_organization.txt"
                   and is_air_mio(o, self.by_name)]
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

    def _policy_types(self, org):
        types = set(org.get("equipment_types") or [])
        for inc in org.get("includes") or []:
            src = self.by_name.get(inc)
            if src:
                types |= set(src.get("equipment_types") or [])
        return types

    def _available_policies(self):
        """按**装备类型**筛出能选的方针；无设计侧加成的方针不列（等级/科技只标注不隐藏）。"""
        org = self._org()
        if not org:
            return []
        types = self._policy_types(org)
        out = []
        for pol in self.data.get("policies") or []:
            if not self._has_design_bonus(pol):
                continue          # 只给生产加成的方针（模块化装配等）对设计无用，不列
            if pol.get("allowed_all"):
                out.append(pol)
                continue
            if not pol.get("equipment_types"):
                continue          # 空的 OR 条件 = 谁都选不了（例如条件被注释掉的海军方针）
            if not (set(pol["equipment_types"]) & types):
                continue
            out.append(pol)
        return out

    def _refresh_policies(self):
        self._policy_map = {"（不选）": None}
        labels = ["（不选）"]
        for pol in self._available_policies():
            name = zh(self.loc, pol["token"]) or pol["token"]
            if name in self._policy_map:
                name = "%s [%s]" % (name, pol["token"])
            self._policy_map[name] = pol
            labels.append(name)
        self.cb_policy.configure(values=labels)
        # 默认选"满级 + 方针"路线里那个方针；取不到再退回逐个试算
        want = None
        org = self._org()
        if org:
            try:
                want = (self._org_plan(org, self.collect()) or {}).get("policy")
            except (Exception, SystemExit):  # noqa: BLE001
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

    def _policy_ready(self, pol):
        """门槛（等级 + 科技）是否满足。"""
        if int(self.var_level.get()) < (pol.get("min_size") or 0):
            return False
        techs = set(self.inputs.get("unlocked_techs") or [])
        return all(t in techs for t in (pol.get("requires_techs") or []))

    def _policy_desc(self, pol):
        """右侧说明：前置要求 + 预计加成。"""
        level = int(self.var_level.get())
        techs = set(self.inputs.get("unlocked_techs") or [])
        need = []
        if pol.get("min_size"):
            need.append("%d 级%s" % (pol["min_size"], "✓" if level >= pol["min_size"] else "✗"))
        for tech in pol.get("requires_techs") or []:
            need.append("%s%s" % (tech, "✓" if tech in techs else "✗"))
        bonus = {k: v for k, v in (pol.get("equipment_bonus") or {}).items()
                 if k != "production_cost_factor" and v}
        parts = ["前置：" + ("、".join(need) if need else "无"),
                 "加成：" + (fmt_mods(bonus) if bonus else "无装备修正")]
        prod = (pol.get("equipment_bonus") or {}).get("production_cost_factor")
        if prod is not None:
            parts.append("生产产出花费 %+.0f%%（只作用于生产，不计入）" % (prod * 100))
        org_mod = pol.get("organization_modifier") or {}
        if org_mod:
            parts.append("组织：" + "、".join("%s %+.0f%%" % (k, v * 100)
                                            for k, v in org_mod.items() if v))
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
            avail = len(self._available_policies())
            self.lbl_policy.configure(
                text=("（本组织可选 %d 个方针，默认已选预计最优的那个）" % avail) if avail else
                     "（本组织无对应装备类型的方针）")
        else:
            self.lbl_policy.configure(text=self._policy_desc(pol))
        self._refresh_totals()

    def _fill_traits(self):
        self.tree_traits.delete(*self.tree_traits.get_children())
        org = self._org()
        if not org:
            return
        unlocked = {t for t, v in self.tech_vars.items() if v.get()}
        hidden = 0
        for trait in org.get("traits", []):
            token = trait.get("token")
            if not token:
                continue
            need = trait.get("requires_techs") or []
            if any(t not in unlocked for t in need):
                hidden += 1          # 科技没解锁的特质游戏里也点不了，直接隐藏
                continue
            self.tree_traits.insert("", "end", iid=token, values=(
                "☐", zh(self.loc, token), fmt_mods(trait.get("bonuses") or {}),
                self._trait_req(trait)))
        base = "点击行勾选/取消（初始特质已默认计入，不需要勾）"
        self.lbl_traits_hint.configure(
            text=base + ("　另有 %d 个特质需前置科技，已隐藏" % hidden if hidden else ""))

    def _trait_req(self, trait):
        parts = []
        for kind, parents in trait.get("parents") or []:
            names = "、".join(zh(self.loc, p) for p in parents)
            parts.append(("需 " if kind == "all_parents" else "任一 ") + names)
        mx = trait.get("mutually_exclusive") or []
        if mx:
            parts.append("互斥 " + "、".join(zh(self.loc, m) for m in mx))
        return "；".join(parts) or "—"

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
            self.chosen_traits.add(token)
            order = getattr(self, "_trait_order", [])
            order.append(token)
            self._trait_order = order
            _dbg("操作：勾选特质「%s」，依次为 %s"
                 % (zh(self.loc, token), "→".join(zh(self.loc, x) for x in order)))
        vals = list(self.tree_traits.item(token)["values"])
        vals[0] = "☑" if token in self.chosen_traits else "☐"
        self.tree_traits.item(token, values=vals)
        self._refresh_totals()

    def _sync_alloc(self):
        if self.var_alloc.get() == "pick":
            self.tree_mio.grid_remove()
            self.frm_traits.grid()
            self.spin_level.configure(state="disabled")
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

    def _refresh_enemy(self):
        """对手按用途分别取：舰载用途是舰载对手（无经验加成），其余是陆基战斗机。"""
        cfg = self._enemy_cfg()
        year = int(self.var_year.get())
        roles = [k for k, v in self.role_vars.items() if v.get()] or ["air_far"]
        picked = {r: engine.pick_enemy_values(self.data["airframes_all"], cfg, r, year)
                  for r in roles}
        keys = {e["key"] for e, _v in picked.values() if e}
        parts = []
        for role in roles:
            e, v = picked[role]
            name = zh(self.loc, e["key"]) or e["name"] if e else "（该规则下找不到机型）"
            body = name if not v else "%s 机动 %.2f 速度 %.2f" % (name, v["agility"], v["speed"])
            parts.append(body if len(keys) <= 1 else "%s：%s" % (ROLE_SHORT.get(role, role), body))
        self.lbl_enemy.configure(text="对手：" + "\u3000｜\u3000".join(parts))

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
            "mio": {"organization": self._org_key(),
                    "level": int(self.var_level.get()),
                    "policy": ((getattr(self, "_policy_map", {}).get(self.var_policy.get())
                                or {}).get("token") if policy is _UNSET else policy),
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
            inputs = self.collect()
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
        ini = org.get("initial_trait")
        if ini:
            mods = engine.combine_modifiers(mods, ini.get("bonuses") or {})
            self.tree_mio.insert("", "end", values=("初始", zh(self.loc, ini.get("token")),
                                                    fmt_mods(ini.get("bonuses") or {})))
        pol = getattr(self, "_policy_map", {}).get(self.var_policy.get())
        if pol:
            bonus = self._policy_bonus(pol)
            mods = engine.combine_modifiers(mods, bonus)
            self.tree_mio.insert("", "end", values=("方针", zh(self.loc, pol["token"]),
                                                    fmt_mods(bonus)))
        if self.var_alloc.get() == "pick":
            for trait in org.get("traits", []):
                if trait.get("token") in self.chosen_traits:
                    mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
                    self.tree_mio.insert("", "end", values=(
                        "勾选", zh(self.loc, trait.get("token")),
                        fmt_mods(trait.get("bonuses") or {})))
            self.lbl_mio_route.configure(text="")
        else:
            level = int(self.var_level.get())
            plan = self._org_plan(org, inputs)
            if plan:
                shown = plan["log"][:level]
                for i, item in enumerate(shown, 1):
                    mods = engine.combine_modifiers(mods, item.get("bonuses") or {})
                    self.tree_mio.insert("", "end", values=("%d 级" % i, zh(self.loc, item["token"]),
                                                            fmt_mods(item.get("bonuses") or {})))
                self.lbl_mio_route.configure(
                    text="满级最优路线共 %d 级，当前按前 %d 级分配（低级时是满级路线的前缀）"
                         % (len(plan["log"]), len(shown)))
        self.lbl_mio_total.configure(text=fmt_mods(mods))

    def on_calculate(self):
        """只计算并在界面里展示（不写文件）。"""
        try:
            inputs = self.collect()
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
                           (self.var_override, "改手动机型")):
            watch(var, label)
        for key, rv in self.role_vars.items():
            watch(rv, "勾选用途 %s" % ROLE_SHORT.get(key, key))
        for var, label in ((self.var_filter, "改机型筛选"), (self.var_f_year, "改年份筛选"),
                           (self.var_f_role, "改用途筛选"), (self.var_f_pareto, "改帕累托筛选"),
                           (self.var_axis_x, "改 X 轴"), (self.var_axis_y, "改 Y 轴")):
            watch(var, label)

    def _sort_by(self, cid):
        if getattr(self, "_sort_key", None) == cid:
            self._sort_desc = not getattr(self, "_sort_desc", True)
        else:
            self._sort_key, self._sort_desc = cid, True
        _dbg("排序：按 %s %s" % (cid, "降序" if self._sort_desc else "升序"))
        self._render_rows()

    def _show_design(self):
        """在表格下方用可换行标签显示选中行的完整推荐改装。"""
        sel = self.tree_out.selection()
        if not sel:
            self.lbl_design.configure(text="")
            return
        values = self.tree_out.item(sel[0])["values"]
        if not values:
            return
        self.lbl_design.configure(text="推荐改装（%s）：%s" % (values[3], values[-1]))

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
        for row in view:
            self.tree_out.insert("", "end", values=(
                "%s@%d" % (ROLE_SHORT.get(row["role"], ROLE_LABELS[row["role"]]), dist), row["rank"],
                "★" if row.get("pareto") else "",
                self._row_name(row),
                "{:,.2f}".format(row["score"]),
                "{:,.1f}".format(row["score"] * row["effective_cost"]),
                "%.2f" % row["effective_cost"],
                row["airframe"].get("year", ""),
                "{:,.2f}（装配 {}）".format(row["weighted"],
                                           row["airframe"].get("air_production", 0)),
                row["design"]))
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
