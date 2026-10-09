#!/usr/bin/env python3
r"""BI_SOV 飞机选型：读输入 → 计算 → 输出工作簿（B3）

用法：
    python run.py                          # 用 inputs.json（不存在则用默认值）
    python run.py --year 1944 --tech-year 1944 --roles air_near,air_far
    python run.py --out ..\BI_SOV_选型输出.xlsx

输出：新工作簿（默认 tools/BI_SOV_选型输出.xlsx），含两张表
   「选型」     —— 每个「机型 × 用途」一行：基础值 / 推荐改装 / 改装后数值 / 对手 / 分数 / 排名
   「参数与口径」—— 本次输入的输入项与所有生效常量（可追溯）
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """程序目录：打包成 exe 后是 exe 所在目录，开发时是脚本目录。

    输出表与 inputs.json 都放这里——用户要能找到导出的文件。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return HERE


DEFAULT_OUT = os.path.abspath(os.path.join(app_dir(), "output", "BI_SOV_选型输出.xlsx"))
INPUTS = os.path.join(app_dir(), "inputs.json")

# 改装 token → 表内短名（与 BI_SOV.xlsx 的 14 行一一对应）
UPGRADE_NAMES = {
    "plane_gun_upgrade": "弹药",
    "plane_engine_upgrade": "发动机",
    "plane_range_upgrade": "燃料",
    "plane_reliability_upgrade": "维护",
    "plane_naval_upgrade": "反舰(naval)",
    "plane_fighter_bomb_upgrade": "火箭弹炸弹",
    "plane_drop_tank_upgrade": "副油箱",
    "plane_light_cannons_upgrade": "对空火力",
    "plane_anti_air_rocket_upgrade": "空对空火箭",
    "plane_bubble_canopy_upgrade": "舱盖",
    "plane_turret_defence_upgrade": "自卫炮塔",
    "plane_airframe_upgrade": "机身",
    "plane_heavy_cannons_upgrade": "航炮对地",
    "plane_cas_upgrade": "反舰(cas)",
    "plane_radar_upgrade": "雷达",
}

_LOC_ZH = None


def loc_zh():
    """汉化表（懒加载）。改装名优先用游戏里的中文全称，取不到才退回短名。"""
    global _LOC_ZH
    if _LOC_ZH is None:
        path = os.path.join(engine.DATA_DIR, "loc_zh.json")
        _LOC_ZH = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    return _LOC_ZH


def upgrade_label(token):
    """改装显示名：优先汉化全称（如 升级发动机），否则退回表内短名。"""
    full = loc_zh().get(token)
    return full or UPGRADE_NAMES.get(token, token)

DEFAULT_INPUTS = {
    "country": "SOV",                       # 当前国家 tag（决定候选机身与可用 MIO）
    "current_year": 1939,                   # 示例默认：1939 年起步
    "tech_year": 1939,
    "roles": ["air_far"],                   # 界面不再区分远近，统一按"远"算，距离由 range_cap 决定
    "manufacturer_mode": "manual",          # "manual" = 直接给修正；"traits" = 选 MIO 特质
    "manufacturer_modifiers": {
        "air_attack": 0.09, "air_defence": 0.09, "air_agility": 0.07, "maximum_speed": 0.025,
        "reliability": 0.03, "build_cost_ic": -0.20, "air_range": 0.13,
        "air_ground_attack": 0.04, "naval_strike_attack": 0.02
    },
    "national_spirits": ["SOV_improved_designs", "SOV_USA_aid_air"],   # 示例默认：苏联的两个
    "extra_modifiers": {},
    "unlocked_techs": ["advanced_machine_tools", "computing_machine"],  # 1939 年前完成的科技
    "unlocked_flags": [],
    "experience": {"air_agility": 0.20, "maximum_speed": 0.05, "air_attack": 0.10,
                   "air_defence": 0.10, "air_ground_attack": 0.10,
                   "naval_strike_attack": 0.10, "naval_strike_targetting": 0.15},
    "enemy": {"country": "GER", "rule": "previous_year", "override_key": None,
              "modifiers": {"air_agility": 0.04, "maximum_speed": 0.015},
              "experience": {"air_agility": 0.20, "maximum_speed": 0.05}},
    "range_cap": 900.0,                     # 距离目标（航程上限）默认 900；600 起每 300 一档
    "pareto_x": "cost",                     # 帕累托图默认 X = 造价
    "pareto_y": "effect",                   # 默认 Y = 性能分数
    "overwrite": False,
}


def load_inputs(args):
    data = dict(DEFAULT_INPUTS)
    if os.path.exists(INPUTS):
        with open(INPUTS, encoding="utf-8") as fh:
            data.update(json.load(fh))
    if args.year:
        data["current_year"] = args.year
    if args.tech_year:
        data["tech_year"] = args.tech_year
    if args.roles:
        data["roles"] = [r.strip() for r in args.roles.split(",") if r.strip()]
    return data


# 帕累托可选轴：(显示名, 取值函数, 越大越好?)
AXIS_DEFS = {
    "effect": ("性能分数", lambda r: r["score"] * r["effective_cost"], True),
    "score": ("总分数（性能/造价）", lambda r: r["score"], True),
    "cost": ("有效造价（IC）", lambda r: r["effective_cost"], False),
    "year": ("年份", lambda r: r["airframe"].get("year") or 0, False),
}
DEFAULT_AXES = ("cost", "score")          # X = 造价，Y = 性能，最直观的取值平面


def pareto_front(rows, x_key="cost", y_key="score"):
    """给每行打上 pareto 标记（**同一用途内**比较，方向按 AXIS_DEFS）。

    若存在另一行"两轴都不差、且至少一轴严格更好"，本行即被支配。
    """
    def val(row, key):
        _name, getter, better_high = AXIS_DEFS[key]
        v = getter(row)
        return v if better_high else -v        # 统一成"越大越好"

    groups = {}
    for row in rows:
        groups.setdefault(row["role"], []).append(row)
    for group in groups.values():
        pts = [(r, val(r, x_key), val(r, y_key)) for r in group]
        for row, x, y in pts:
            row["pareto"] = not any(
                ox >= x and oy >= y and (ox > x or oy > y)
                for other, ox, oy in pts if other is not row)
    return rows


def candidate_pool(inputs, data):
    """候选机身 = 当前国家 + 科技年份以内 + 本次用途对应的机种（archetype）。

    用途只决定"能用哪一类飞机"：对空挑战斗机族、对地挑 CAS 族、对海挑海军轰炸机族、
    侦察/运输挑侦察机与运输机。这样对地不会再选出一架多用途战斗机。
    """
    archetypes = engine.role_archetypes(inputs["roles"])
    return [a for a in data["airframes_all"]
            if a.get("country") == inputs.get("country")
            and (a.get("year") or 0) <= inputs["tech_year"]
            and a.get("archetype") in archetypes]


def build_rows(inputs, data):
    # 「手动输入」就是最终值：不叠加军工组织与国家精神
    if inputs.get("modifier_source") == "manual":
        inputs = dict(inputs)
        inputs["manufacturer_mode"] = "manual"
    upgrade_map = engine.upgrades_by_key(data["upgrades"])
    candidates = candidate_pool(inputs, data)
    mfr_mods, mfr_info = resolve_manufacturer(inputs, data, upgrade_map, candidates)
    # 国家精神按装备类别识别：只有落在本次用途对应类别里的条目才算数
    source = inputs.get("modifier_source", "mio")
    cats = engine.role_idea_categories(inputs["roles"])
    spirit_mods = ({} if source == "manual" else
                   engine.spirit_modifiers(data["national_ideas"],
                                           inputs.get("national_spirits") or [],
                                           categories=cats))
    player_mods = engine.combine_modifiers(
        mfr_mods, spirit_mods, inputs.get("extra_modifiers") or {})
    # 对手按用途分别取：舰载用途用舰载对手且不吃经验加成，其余用陆基战斗机
    enemy_cfg = inputs.get("enemy") or {}
    enemy_by_role = {}
    for role in inputs["roles"]:
        enemy_by_role[role] = engine.pick_enemy_values(
            data["airframes_all"], enemy_cfg, role, inputs["current_year"])
    primary_role = inputs["roles"][0]
    enemy, enemy_values = enemy_by_role.get(primary_role, (None, None))

    rows = []
    role_arch = {r: set(engine.MISSION_ARCHETYPES.get(engine.ROLE_MISSION.get(r, ""), ()))
                 for r in inputs["roles"]}
    for airframe in candidates:
        tokens = engine.available_upgrades(
            airframe["category"], data,
            techs=inputs.get("unlocked_techs") or [],
            flags=inputs.get("unlocked_flags") or [],
            archetype=airframe.get("archetype"),
        )[0]
        for role in inputs["roles"]:
            if airframe.get("archetype") not in role_arch[role]:
                continue
            role_enemy, role_enemy_values = enemy_by_role.get(role, (None, None))
            score_key = engine.score_role(role)
            # 舰载用途停在航母上，事故率要乘 ACCIDENT_CHANCE_CARRIER_MULT
            acc_f = engine.accident_factor(role in engine.CARRIER_ROLES)
            result = engine.optimize(airframe, upgrade_map, player_mods, role_enemy_values,
                                     score_key,
                                     available=tokens, range_cap=inputs.get("range_cap"),
                                     experience=inputs.get("experience"), accident_f=acc_f)
            weighted = engine.resource_weighted(result["scores"], airframe)
            design = " ".join(
                "%s×%d" % (upgrade_label(t), n)
                for t, n in result["levels"].items() if n
            )
            rows.append({
                "role": role,
                "role_name": engine.ROLES[role],
                "score": result["scores"][score_key],
                "weighted": weighted.get(score_key, 0.0),
                "enemy": role_enemy,
                "enemy_values": role_enemy_values,
                "airframe": airframe,
                "design": design or "（无需改装）",
                "upgrade_count": sum(result["levels"].values()),
                "values": result["values"],
                "effective_cost": result["effective_cost"],
            })
    rows.sort(key=lambda r: (r["role"], -r["score"]))
    rank = {}
    for row in rows:
        rank[row["role"]] = rank.get(row["role"], 0) + 1
        row["rank"] = rank[row["role"]]
    return rows, player_mods, enemy, enemy_values, mfr_info


def mio_organizations(data):
    """可选 MIO 组织（只保留能用于战斗机的，且去重按名称排序）。"""
    out = []
    for org in data["mio"]:
        types = org.get("equipment_types") or []
        if types and not any("all_small_plane" in t or "all_medium_plane" in t
                             or "multi_role" in t or "air" in t for t in types):
            continue
        out.append(org)
    return out


def resolve_manufacturer(inputs, data, upgrade_map, candidates):
    """按 manufacturer_mode 解析制造商修正。

    mode = "manual"：直接用 manufacturer_modifiers
    mode = "traits"：指定 MIO 组织
        manual_traits 为 None → 按 level 用 ai_will_do × 收益贪心自动配
        manual_traits 为列表（可为空）→ 按手工勾选的清单取，空列表即只用初始特质
    返回 (修正 dict, 说明 dict)
    """
    mode = inputs.get("manufacturer_mode", "manual")
    if mode != "traits":
        return dict(inputs.get("manufacturer_modifiers") or {}), {"mode": "manual"}
    cfg = inputs.get("mio") or {}
    name = cfg.get("organization")
    org = next((o for o in data["mio"] if o["organization"] == name), None)
    if not org:
        raise SystemExit("找不到 MIO 组织：%s（可用：%s）"
                         % (name, ", ".join(o["organization"] for o in mio_organizations(data)[:8]) + " …"))
    mods = {}
    info = {"mode": "traits", "organization": name, "initial_trait": None, "traits": []}
    ini = org.get("initial_trait")
    if ini:
        mods = engine.combine_modifiers(mods, ini.get("bonuses") or {})
        info["initial_trait"] = ini.get("token")
    manual = cfg.get("manual_traits")
    if manual is not None:
        tech_set = set(inputs.get("unlocked_techs") or [])
        for trait in org.get("traits", []):
            # 科技没解锁的特质游戏里点不了，手工清单同样跳过
            if any(t not in tech_set for t in (trait.get("requires_techs") or [])):
                continue
            if trait.get("token") in manual:
                mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
                info["traits"].append({"token": trait.get("token"), "bonuses": trait.get("bonuses")})
        info["manual"] = True
    else:
        level = int(cfg.get("level") or 0)
        if level and candidates:
            ref = max(candidates, key=lambda a: (a.get("year") or 0))
            # 按"满级最优路线"取前 level 步，而不是每级单独跑一遍贪心
            _chosen, mods, log = engine.mio_route(
                org, level, ref, upgrade_map, mods, None, inputs["roles"],
                inputs.get("range_cap"), inputs.get("experience"),
                techs=inputs.get("unlocked_techs") or [])
            info["traits"] = log
            info["level"] = level

    # MIO 方针（6 级起可选）：只计入"设计侧"的装备修正
    policy = cfg.get("policy")
    if policy:
        pol = next((p for p in (data.get("policies") or []) if p["token"] == policy), None)
        if pol:
            bonuses = dict(pol.get("equipment_bonus") or {})
            # production_cost_factor = **生产产出花费**（只作用于生产、可在生产中规避），
            # 与设计无关 → 不计入造价；设计侧的花费修正是 build_cost_ic，那个会正常计入。
            prod = bonuses.pop("production_cost_factor", None)
            mods = engine.combine_modifiers(mods, bonuses)
            info["policy"] = {"token": policy, "bonuses": bonuses,
                              "production_cost_factor_ignored": prod,
                              "organization_modifier": pol.get("organization_modifier") or {}}
    return mods, info


def _enemy_summary(rows):
    """把每行自带的对手汇总成「用途=机型(机动/速度)」形式。"""
    seen = {}
    for row in rows:
        key = row["role"]
        if key in seen:
            continue
        e, v = row.get("enemy"), row.get("enemy_values")
        seen[key] = "%s %s%s" % (
            engine.ROLES[key], e["name"] if e else "（无）",
            "" if not v else "（%.2f/%.2f）" % (v["agility"], v["speed"]))
    return "；".join(seen.values())


def write_workbook(path, inputs, rows, player_mods, enemy, enemy_values, mfr_info=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "选型"
    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True)

    ws["A1"] = "BI_SOV 飞机选型输出"
    ws["A1"].font = Font(bold=True, size=14)
    info = [
        ("当前年份", inputs["current_year"], "科技年份", inputs["tech_year"]),
        ("用途", "、".join(engine.ROLES[r] for r in inputs["roles"]), "", ""),
        ("国别", inputs.get("country", ""), "对手（按用途）", _enemy_summary(rows)),
        ("首个用途的对手", enemy["name"] if enemy else "（无）",
         "对手机动/速度",
         "" if not enemy_values else "%.2f / %.2f" % (enemy_values["agility"], enemy_values["speed"])),
        ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M"), "", ""),
    ]
    r = 3
    for a, b, c, d in info:
        ws.cell(r, 1, a).font = Font(bold=True)
        ws.cell(r, 2, b)
        if c:
            ws.cell(r, 5, c).font = Font(bold=True)
            ws.cell(r, 6, d)
        r += 1

    columns = [
        ("用途", 10), ("排名", 6), ("机型", 22), ("类别", 12), ("年份", 6),
        ("基础半径", 8), ("基础防御", 8), ("基础攻击", 8), ("基础机动", 8), ("基础对地", 8),
        ("基础速度", 8), ("基础可靠", 8), ("基础造价", 8),
        ("推荐改装", 40), ("改装数", 6),
        ("半径", 8), ("防御", 8), ("攻击", 8), ("机动", 8), ("对地", 8), ("速度", 8),
        ("可靠", 8), ("造价", 8), ("有效造价（IC）", 13),
        ("对手", 20), ("对手机动", 9), ("对手速度", 9),
        ("总分数（性能/造价）", 18), ("性能分数", 14), ("科技年份", 9),
        ("飞机装配资源加权分（总分数/资源开销）", 26),
        ("帕累托最优", 10),
    ]
    header_row = r + 1
    for idx, (name, width) in enumerate(columns, start=1):
        cell = ws.cell(header_row, idx, name)
        cell.fill = head_fill
        cell.font = head_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width

    row_no = header_row + 1
    for row in rows:
        a = row["airframe"]
        v = row["values"]
        values = [
            row["role_name"], row["rank"], a["name"], a["category"], a["year"],
            a["range"], a["defence"], a["attack"], a["agility"], a["ground_attack"],
            a["speed"], a["reliability"], a["cost"],
            row["design"], row["upgrade_count"],
            round(v["range"], 2), round(v["defence"], 2), round(v["attack"], 2),
            round(v["agility"], 2), round(v["ground_attack"], 2), round(v["speed"], 2),
            round(v["reliability"], 4), round(v["cost"], 2), round(row["effective_cost"], 2),
            (row.get("enemy") or {}).get("name", ""),
            round(row["enemy_values"]["agility"], 2) if row.get("enemy_values") else "",
            round(row["enemy_values"]["speed"], 2) if row.get("enemy_values") else "",
            round(row["score"], 6), round(row["score"] * row["effective_cost"], 2),
            row["airframe"].get("year"),
            round(row["weighted"], 6),
            "★" if row.get("pareto") else "",
        ]
        for idx, value in enumerate(values, start=1):
            ws.cell(row_no, idx, value)
        row_no += 1
    for col in ("F", "G", "H", "I", "J", "K", "L", "M", "P", "Q", "R", "S", "T", "U",
                "V", "W", "X", "Z", "AA", "AB", "AC"):
        for rr in range(header_row + 1, row_no):
            ws["%s%d" % (col, rr)].number_format = "0.####"
    ws.freeze_panes = ws.cell(header_row + 1, 1)

    ws2 = wb.create_sheet("参数与口径")
    ws2["A1"] = "本次输入与生效常量"
    ws2["A1"].font = Font(bold=True, size=13)
    lines = [
        ("当前年份", inputs["current_year"]),
        ("科技年份（可造机型 year ≤ 此值）", inputs["tech_year"]),
        ("用途", "、".join(engine.ROLES[r] for r in inputs["roles"])),
        ("修正来源", "手动输入（最终值）" if inputs.get("modifier_source") == "manual"
         else "军工组织（MIO）+ 国家精神"),
        ("国家精神类别（按用途）", json.dumps(sorted(engine.role_idea_categories(inputs["roles"])),
                                             ensure_ascii=False)),
        ("制造商修正（含国家精神/手填）", json.dumps(player_mods, ensure_ascii=False)),
        ("制造商来源", json.dumps(mfr_info or {}, ensure_ascii=False)),
        ("国家精神", json.dumps(inputs.get("national_spirits") or [], ensure_ascii=False)),
        ("解锁科技", json.dumps(inputs.get("unlocked_techs") or [], ensure_ascii=False)),
        ("解锁国家标识", json.dumps(inputs.get("unlocked_flags") or [], ensure_ascii=False)),
        ("经验加成", json.dumps(inputs.get("experience") or {}, ensure_ascii=False)),
        ("对手选取规则", (inputs.get("enemy") or {}).get("rule", "previous_year")),
        ("对手", (enemy or {}).get("name", "（无）")),
        ("对手最终机动/速度", "" if not enemy_values else "%.2f / %.2f" % (enemy_values["agility"], enemy_values["speed"])),
        ("航程上限", inputs.get("range_cap")),
        ("事故年损失率 f", engine.ACCIDENT_FACTOR),
        ("事故年损失率 f（舰载，× ACCIDENT_CHANCE_CARRIER_MULT）",
         "%.6f（= %.6f × %.2f）" % (engine.ACCIDENT_FACTOR_CARRIER, engine.ACCIDENT_FACTOR,
                                    engine.ACCIDENT_CHANCE_CARRIER_MULT)),
        ("事故口径", engine.ACCIDENT_MODE),
        ("空战伤害项地板（排名用）", engine.COMBAT_FACTOR_FLOOR),
        ("对地/对海防御指数", engine.NON_AIR_DEFENCE_EXPONENT),
        ("效果指数表 EFFECT_EXPONENTS", json.dumps(engine.EFFECT_EXPONENTS, ensure_ascii=False)),
        ("帕累托轴", "X = %s，Y = %s（同一用途内比较；★ = 未被支配）"
         % (AXIS_DEFS.get(inputs.get("pareto_x", DEFAULT_AXES[0]), ("?",))[0],
            AXIS_DEFS.get(inputs.get("pareto_y", DEFAULT_AXES[1]), ("?",))[0])),
        ("空战机动/速度系数", "%s / %s，封顶 %s / %s"
         % (engine.COMBAT_AGILITY_DAMAGE_REDUCTION, engine.COMBAT_SPEED_DAMAGE_INCREASE,
            engine.BIGGEST_AGILITY_FACTOR_DIFF, engine.BIGGEST_SPEED_FACTOR_DIFF)),
        ("数据来源", json.dumps(
            {"game_dir": _manifest().get("game_dir"),
             "generated_at": _manifest().get("generated_at")}, ensure_ascii=False)),
    ]
    for i, (k, val) in enumerate(lines, start=3):
        ws2.cell(i, 1, k).font = Font(bold=True)
        ws2.cell(i, 2, val)
    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 90

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)


def _manifest():
    path = os.path.join(engine.DATA_DIR, "manifest.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


# 验收锚点：表内口径下「对空 + 距离 900」时 Yak-9U @1944 的分数与对手数值。
# 自包含：不读 inputs.json，避免用户的存档状态影响校验结果。
ANCHOR = {
    "year": 1944,
    "tech_year": 1944,
    "role": "air_far",
    "range_cap": 900.0,
    "plane": "Yakovlev 9U",
    "score": 15540.543552,
    "enemy_agility": 86.112,
    "enemy_speed": 708.72375,
    "manufacturer_modifiers": {
        "air_attack": 0.09, "air_defence": 0.09, "air_agility": 0.07, "maximum_speed": 0.025,
        "reliability": 0.03, "build_cost_ic": -0.20, "air_range": 0.13,
        "air_ground_attack": 0.04, "naval_strike_attack": 0.02,
    },
    "national_spirits": [],
    "experience": {},
    "unlocked_techs": ["assembly_line_production", "Ltaircraft_industry3",
                       "chemical_industry_iii", "improved_centimetric_radar",
                       "advanced_centimetric_radar"],
    "unlocked_flags": ["unlock_plane_anti_air_rocket_upgrade"],
    "enemy": {"country": "GER", "rule": "previous_year", "override_key": None,
              "modifiers": {"air_agility": 0.04, "maximum_speed": 0.015},
              "experience": {"air_agility": 0.20, "maximum_speed": 0.05}},
}


def anchor_check(tol=1e-3):
    """锚点校验（2026-10-09 定为验收口径）：对空 + 距离 900。

    用 inputs.json 的制造商手填值（= 表内那套），检查
      Yak-9U@1944 的对空远分数 = 15540.543552
      对手 Bf 109 G-14 的最终机动/速度 = 86.112 / 708.72375
    """
    inputs = dict(DEFAULT_INPUTS)
    inputs.update({
        "country": "SOV",
        "current_year": ANCHOR["year"],
        "tech_year": ANCHOR["tech_year"],
        "roles": [ANCHOR["role"]],
        "range_cap": ANCHOR["range_cap"],
        "modifier_source": "manual",
        "manufacturer_mode": "manual",
        "manufacturer_modifiers": dict(ANCHOR["manufacturer_modifiers"]),
        "national_spirits": list(ANCHOR["national_spirits"]),
        "experience": dict(ANCHOR["experience"]),
        "unlocked_techs": list(ANCHOR["unlocked_techs"]),
        "unlocked_flags": list(ANCHOR["unlocked_flags"]),
        "enemy": dict(ANCHOR["enemy"]),
    })
    data = engine.load_data()
    rows, _mods, enemy, enemy_values, _info = build_rows(inputs, data)
    top = next((r for r in rows if r["role"] == ANCHOR["role"]), None)
    print("锚点校验：对空 + 距离 %.0f（当前年份/科技年份 %d）" % (ANCHOR["range_cap"], ANCHOR["year"]))
    print("  对手          %s" % (enemy["name"] if enemy else "（无）"))
    if enemy_values:
        print("  对手机动/速度  %.5f / %.5f（期望 %.5f / %.5f）"
              % (enemy_values["agility"], enemy_values["speed"],
                 ANCHOR["enemy_agility"], ANCHOR["enemy_speed"]))
    ok = True
    if enemy_values:
        ok &= abs(enemy_values["agility"] - ANCHOR["enemy_agility"]) < tol
        ok &= abs(enemy_values["speed"] - ANCHOR["enemy_speed"]) < tol
    if not top:
        print("  找不到候选行 ✗")
        return 1
    print("  第一名        %s  纯 %.6f（期望 %.6f）"
          % (top["airframe"]["name"], top["score"], ANCHOR["score"]))
    print("  推荐改装      %s" % top["design"])
    ok &= abs(top["score"] - ANCHOR["score"]) < tol
    print("锚点校验：%s" % ("通过 ✓" if ok else "未通过 ✗"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, help="当前年份（决定敌方）")
    ap.add_argument("--tech-year", type=int, help="飞机科技年份（决定我方可用机身）")
    ap.add_argument("--roles", help="用途，逗号分隔：%s" % ",".join(engine.ROLES))
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--anchor", action="store_true", help="只跑锚点校验（对空 + 距离 900）")
    args = ap.parse_args()

    if args.anchor:
        sys.exit(anchor_check())

    inputs = load_inputs(args)
    data = engine.load_data()
    rows, player_mods, enemy, enemy_values, mfr_info = build_rows(inputs, data)
    pareto_front(rows, inputs.get("pareto_x", DEFAULT_AXES[0]), inputs.get("pareto_y", DEFAULT_AXES[1]))

    if os.path.exists(args.out) and not inputs.get("overwrite"):
        base, ext = os.path.splitext(args.out)
        args.out = "%s_%s%s" % (base, datetime.now().strftime("%Y%m%d-%H%M%S"), ext)
        print("输出已存在且 overwrite=false，改存为：%s" % os.path.basename(args.out))

    write_workbook(args.out, inputs, rows, player_mods, enemy, enemy_values, mfr_info)
    print("候选 %d 个「机型 × 用途」组合，写入：%s" % (len(rows), args.out))
    for role in inputs["roles"]:
        top = [r for r in rows if r["role"] == role][:3]
        print("  %s 前三：" % engine.ROLES[role])
        for r in top:
            print("    %-22s 纯 %.4f  加权 %.4f  %s" % (
                r["airframe"]["name"], r["score"], r["weighted"], r["design"]))


if __name__ == "__main__":
    main()
