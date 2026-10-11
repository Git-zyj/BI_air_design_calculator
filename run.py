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

if getattr(sys, "stdout", None):
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

# ---------- 路线方案（方针 × 特质）的表与缓存 ----------
# 离线预计算表随工具发布（只读）；运行时新算出来的方案写进用户机器上的缓存文件。
# 两者**同一套键**，所以"离线算过"和"现算过"的命中效果一样。
PLAN_TABLE = os.path.join(engine.DATA_DIR, "route_table.json")   # 离线表（随包发布）
PLAN_CACHE = os.path.join(app_dir(), "route_cache.json")         # 运行时缓存（本地生成）
# 算法/口径/方针数据变了就改这里，旧的离线表与本机缓存自动作废：
#   v3 = 方针的 production_bonus 抽全（same_as_mio 嵌套）→ 「不断的工业革命」等
#        现在会把生产资源需求/效率算进来，方针集合与分数都可能变
PLAN_CACHE_VERSION = 3


def plan_key(inputs, org_name, ref_key):
    """方案指纹：凡是影响"方针 + 路线"的输入都要进这个键。"""
    return "|".join([
        "v%d" % PLAN_CACHE_VERSION,
        engine.data_fingerprint(),
        str(inputs.get("country") or ""),
        str(inputs.get("tech_year") or ""),
        str(inputs.get("current_year") or ""),
        ",".join(inputs.get("roles") or []),
        ",".join(sorted(inputs.get("unlocked_techs") or [])),
        ",".join(sorted(inputs.get("unlocked_flags") or [])),
        json.dumps(inputs.get("enemy") or {}, sort_keys=True),
        json.dumps(inputs.get("experience") or {}, sort_keys=True),
        str(inputs.get("range_cap") or ""),
        str(inputs.get("alloc_mode") or "split"),
        # 生产堆叠只影响"兼顾"（分离口径的路线与分数跟堆叠无关）→
        # 分离时用默认值入键，这样改效率上限/产量加成不会把分离那条计划也判失效。
        ("%s|%s" % (inputs.get("efficiency_cap_now") or 100,
                    inputs.get("capacity_bonus_now") or 200)
         if (inputs.get("alloc_mode") or "split") == "balanced"
         else "%s|%s" % (DEFAULT_INPUTS.get("efficiency_cap_now", 100),
                         DEFAULT_INPUTS.get("capacity_bonus_now", 200))),
        str(org_name or ""),
        str(ref_key or ""),
    ])


def _load_plan_file(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (ValueError, OSError):
            pass
    return {}


def load_plan_table():
    """离线预计算表（data/route_table.json）。"""
    return _load_plan_file(PLAN_TABLE)


def load_plan_cache():
    """运行时缓存（程序目录 route_cache.json）。"""
    return _load_plan_file(PLAN_CACHE)


def save_plan_cache(cache):
    try:
        with open(PLAN_CACHE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except OSError:
        pass

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
    # 我方联队经验**不建模**（= 0）：表口径是"设计值"，经验只在对手段单独建模
    # （engine.ENEMY_EXPERIENCE）。留这个键只是为了兼容旧 inputs.json 的写法。
    "experience": {},
    # 对手（AI）的"设计商修正"由 engine.enemy_design() 按模组 ai_bonus_weights 自动判定；
    # 界面手填的值存在 by_country[该国]（优先级高于自动判定）。
    "enemy": {"country": "GER", "rule": "previous_year", "override_key": None,
              "by_country": {}},
    "range_cap": 900.0,                     # 距离目标（航程上限）默认 900；600 起每 300 一档
    "efficiency_cap_now": 100,              # 当前生产效率上限（%）——生产折算用
    "capacity_bonus_now": 200,              # 当前产能加成（%）——生产折算用
    "mio": {"organization": "", "level": 14, "manual_traits": None},   # 军工组织默认满级
    "modifier_source": "mio",               # 修正来源：mio = 军工组织+国家精神；manual = 手填
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


# 舰载机 archetype：陆基用途挑"参考机型"时优先排除它们
CARRIER_ARCHETYPES = ("cv_fighter_equipment", "cv_mr_fighter_equipment",
                      "cv_nav_bomber_equipment", "cv_CAS_equipment")


def pick_reference_plane(pool, inputs, data, upgrade_map, enemy_by_role):
    """路线优化 / 装备类型过滤用的"参考机型"：
    **该用途下"空修正"分数最高的候选**（陆基用途优先非舰载机型）。

    以前直接取 `max(pool, key=year)`：1939 会挑到舰载机 I-153k、1944 会挑到重型战斗机 MiG-5
    —— 按它们的装备组去过滤 MIO，下拉和特质表都会带偏（雅科夫列夫就被误删过）。
    用"谁分最高"当代表，和工具自己的口径一致。
    """
    if not pool:
        return None
    carrier_role = any(r in engine.CARRIER_ROLES for r in (inputs.get("roles") or ()))
    cands = pool if carrier_role else (
        [a for a in pool if a.get("archetype") not in CARRIER_ARCHETYPES] or pool)
    role = (inputs.get("roles") or ["air_far"])[0]
    _enemy, enemy_values = enemy_by_role.get(role, (None, None))
    score_key = engine.score_role(role)
    acc_f = engine.accident_factor(role in engine.CARRIER_ROLES)
    best, best_score = cands[0], None
    for airframe in cands:
        tokens = engine.available_upgrades(
            airframe["category"], data, techs=inputs.get("unlocked_techs") or [],
            flags=inputs.get("unlocked_flags") or [], archetype=airframe.get("archetype"))[0]
        result = engine.optimize(airframe, upgrade_map, {}, enemy_values, score_key,
                                 available=tokens, range_cap=inputs.get("range_cap"),
                                 experience=inputs.get("experience"), accident_f=acc_f)
        value = result["scores"].get(score_key, 0.0)
        if best_score is None or value > best_score:
            best, best_score = airframe, value
    return best


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
    # 对手按用途分别取（参考机型与每行都要用，所以先算）
    enemy_cfg = inputs.get("enemy") or {}
    enemy_by_role = {}
    for role in inputs["roles"]:
        enemy_by_role[role] = engine.pick_enemy_values(
            data["airframes_all"], enemy_cfg, role, inputs["current_year"])
    primary_role = inputs["roles"][0]
    enemy, enemy_values = enemy_by_role.get(primary_role, (None, None))
    ref = pick_reference_plane(candidates, inputs, data, upgrade_map, enemy_by_role)
    mfr_mods, mfr_info = resolve_manufacturer(inputs, data, upgrade_map, candidates, ref)
    # 生产侧折算：把 MIO 的生产修正换成"等效造价折扣"（产能倍率 gain ⇒ 造价 ÷ gain）。
    # 用户填的"当前效率上限 / 产能加成"决定这些加成值多少（+5 在 100 与 200 上完全不同）。
    gain, gain_parts = engine.production_gain(mfr_info.get("production"),
                                             inputs.get("efficiency_cap_now", 100),
                                             inputs.get("capacity_bonus_now", 200))
    if mfr_info.get("production_gain_override"):     # 设计/生产分离：用生产伙伴的倍率
        gain = float(mfr_info["production_gain_override"])
        gain_parts = {}
    mfr_info["production_gain"] = gain
    mfr_info["production_gain_parts"] = gain_parts
    # 国家精神按装备类别识别：只有落在本次用途对应类别里的条目才算数
    source = inputs.get("modifier_source", "mio")
    cats = engine.role_idea_categories(inputs["roles"])
    spirit_mods = ({} if source == "manual" else
                   engine.spirit_modifiers(data["national_ideas"],
                                           inputs.get("national_spirits") or [],
                                           categories=cats))
    player_mods = engine.combine_modifiers(
        mfr_mods, spirit_mods, inputs.get("extra_modifiers") or {})
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
            # 资源加权分：把该路线/方针的"生产资源需求"修正折算进除数
            # （需求 −5% ⇒ 等效资源开销 ×0.95 ⇒ 资源加权分变高）
            _need = (mfr_info.get("production") or {}).get("production_resource_need_factor", 0.0)
            weighted = engine.resource_weighted(result["scores"], airframe, need_factor=_need)
            design = " ".join(
                "%s×%d" % (upgrade_label(t), n)
                for t, n in result["levels"].items() if n
            )
            rows.append({
                "role": role,
                "role_name": engine.ROLES[role],
                "score_raw": result["scores"][score_key],          # 纯设计分（性能÷有效造价）
                "score": result["scores"][score_key] * gain,       # 生产折算后（÷ 等效造价）
                "weighted": weighted.get(score_key, 0.0) * gain,
                "production_gain": gain,
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


def route_value(org, plane, tokens, mods0, upgrade_map, data, inputs, enemy_values, role):
    """一条路线在某机型上的"折算后总分数"（性能 ÷ 等效造价），用于口径比较。"""
    by_token = {t.get("token"): t for t in (org.get("traits") or [])}
    mods, prod = dict(mods0), {}
    for token in tokens:
        trait = by_token.get(token)
        if not trait:
            continue
        mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
        prod = engine.combine_modifiers(prod, trait.get("production") or {})
    avail = engine.available_upgrades(
        plane["category"], data, techs=inputs.get("unlocked_techs") or [],
        flags=inputs.get("unlocked_flags") or [], archetype=plane.get("archetype"))[0]
    key = engine.score_role(role)
    result = engine.optimize(plane, upgrade_map, mods, enemy_values, key, available=avail,
                             range_cap=inputs.get("range_cap"),
                             experience=inputs.get("experience"),
                             accident_f=engine.accident_factor(role in engine.CARRIER_ROLES))
    gain = engine.production_gain(prod, inputs.get("efficiency_cap_now", 100),
                                  inputs.get("capacity_bonus_now", 200))[0]
    return result["scores"].get(key, 0.0) * gain


def best_production_plan(inputs, data, plane):
    """在"覆盖该机型"的本国 MIO 里找生产折算最优的一家。

    返回 {"organization", "tokens", "gain", "level"}（找不到增益 > 1 的返回 None）。
    用于"设计 / 生产分离"口径：设计还是用当前 MIO，生产交给这一家。
    """
    country = inputs.get("country") or ""
    groups = engine.plane_groups((plane or {}).get("archetype"))
    techs = inputs.get("unlocked_techs") or []
    cap = inputs.get("efficiency_cap_now", 100)
    ca = inputs.get("capacity_bonus_now", 200)
    best = None
    for org in data["mio"]:
        if not os.path.basename(org.get("file") or "").upper().startswith(country + "_"):
            continue
        types = set(org.get("equipment_types") or [])
        if groups and not (types & groups):
            continue
        tokens, gain = engine.production_route(org, plane, techs, cap, ca)
        if gain <= 1.0 + 1e-9:
            continue
        better = (best is None or gain > best["gain"] + 1e-9
                  or (abs(gain - best["gain"]) <= 1e-9 and len(tokens) < len(best["tokens"])))
        if better:
            best = {"organization": org["organization"], "tokens": tokens, "gain": gain,
                    "level": engine.MIO_MAX_LEVEL}
    return best


def resolve_manufacturer(inputs, data, upgrade_map, candidates, ref=None):
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
    prod = {}                       # 生产侧修正合计（用来折算"等效造价"）
    info = {"mode": "traits", "organization": name, "initial_trait": None, "traits": []}
    ini = org.get("initial_trait")
    if ini:
        mods = engine.combine_modifiers(mods, ini.get("bonuses") or {})
        prod = engine.combine_modifiers(prod, ini.get("production") or {})
        info["initial_trait"] = ini.get("token")
    manual = cfg.get("manual_traits")
    if manual is not None:
        tech_set = set(inputs.get("unlocked_techs") or [])
        # 按**界面钉进来的顺序**取（以前是按组织文件里的顺序遍历，于是"预览的路线"
        # 和"计算列出来的路线"顺序不同 —— 同一套特质、但顺序看着不一样）。
        by_token = {t.get("token"): t for t in org.get("traits", [])}
        for token in manual:
            trait = by_token.get(token)
            if trait is None:
                continue
            # 科技没解锁的特质游戏里点不了，手工清单同样跳过
            if any(t not in tech_set for t in (trait.get("requires_techs") or [])):
                continue
            mods = engine.combine_modifiers(mods, trait.get("bonuses") or {})
            prod = engine.combine_modifiers(prod, trait.get("production") or {})
            info["traits"].append({"token": token, "bonuses": trait.get("bonuses"),
                                   "production": trait.get("production")})
        info["manual"] = True
    else:
        level = int(cfg.get("level") or 0)
        if level and candidates:
            if ref is None:
                enemy_by_role = {
                    r: engine.pick_enemy_values(data["airframes_all"],
                                                inputs.get("enemy") or {}, r,
                                                inputs["current_year"])
                    for r in inputs["roles"]}
                ref = pick_reference_plane(candidates, inputs, data, upgrade_map, enemy_by_role)
            base_mods = dict(mods)          # 只含"初始特质"，用于比较不同路线（别被前一条污染）
            # 满级最优路线（前 level 步）：用"粗筛 + 完整体校验"，保证和实际计分口径一致
            avail = engine.available_upgrades(
                ref["category"], data, techs=inputs.get("unlocked_techs") or [],
                flags=inputs.get("unlocked_flags") or [], archetype=ref.get("archetype"))[0]
            # 统一搜索：每个候选特质集都用真实管线（自己的最优改装 + 生产折算）评分。
            #   分离 → fold=False（纯设计最优）；兼顾 → fold=True（设计 × 生产）
            _enemy_values = engine.pick_enemy_values(
                data["airframes_all"], inputs.get("enemy") or {}, inputs["roles"][0],
                inputs["current_year"])[1]
            _cap = inputs.get("efficiency_cap_now", 100)
            _ca = inputs.get("capacity_bonus_now", 200)
            _fold = (inputs.get("alloc_mode") or "split") == "balanced"
            _ckey = (org["organization"], level, ref.get("key"), _fold, _cap, _ca,
                     tuple(sorted(inputs.get("unlocked_techs") or [])),
                     tuple(inputs["roles"]), float(inputs.get("range_cap") or 0))
            _chosen, mods, log = engine.route_best(
                org, level, ref, upgrade_map, base_mods, _enemy_values, inputs["roles"],
                inputs.get("range_cap"), inputs.get("experience"),
                techs=inputs.get("unlocked_techs") or [], cap_now=_cap, capacity_now=_ca,
                available=avail, fold=_fold, cache_key=_ckey)
            for item in log:
                prod = engine.combine_modifiers(prod, item.get("production") or {})
            info["traits"] = log
            info["level"] = level
            if _fold:
                info["alloc_mode"] = "balanced（兼顾）"

    # 「分离」口径：生产交给更优的那家 MIO（本 MIO 只做设计）。
    # 注意：**界面会把预览的那条路线钉进来**（manual_traits），所以这一步必须在
    # 分支之外执行 —— 以前它挂在"自动搜路线"分支里，界面路径（已钉路线）就漏算了
    # 生产伙伴的折算，实测德国 1944 分离：界面 50.6734 vs 命令行 51.5179（差 1.67%）。
    if (inputs.get("alloc_mode") or "split") == "split" and ref is not None:
        cap = inputs.get("efficiency_cap_now", 100)
        ca = inputs.get("capacity_bonus_now", 200)
        partner = best_production_plan(inputs, data, ref)
        own_gain = engine.production_gain(prod, cap, ca)[0]
        if (partner and partner["gain"] > own_gain + 1e-9
                and partner["organization"] != org["organization"]):
            info["production_partner"] = partner
            info["production_gain_override"] = partner["gain"]
            prod = {}                  # 本 MIO 只做设计，生产不算它的
            info["alloc_mode"] = "split→生产换家"
        else:
            info["alloc_mode"] = "split→本 MIO 顺手做生产"

    # MIO 方针（6 级起可选）：只计入"设计侧"的装备修正
    policy = cfg.get("policy")
    if policy:
        pol = next((p for p in (data.get("policies") or []) if p["token"] == policy), None)
        # 门槛：等级不够（方针都是 6 级起）或前置科技没解锁 → 游戏里根本选不了，一律不计入。
        # 界面那边也已经不列它了，这里再兜一道，防止 inputs.json / 命令行 / 旧配置绕过。
        level_now = int(cfg.get("level") or 0)
        tech_set = set(inputs.get("unlocked_techs") or [])
        if pol and (level_now < (pol.get("min_size") or 0)
                    or any(t not in tech_set for t in (pol.get("requires_techs") or []))):
            info["policy_rejected"] = {"token": policy, "level": level_now,
                                       "need_level": pol.get("min_size")}
            pol = None
        if pol:
            bonuses = dict(pol.get("equipment_bonus") or {})
            # production_cost_factor = **生产产出花费**（只作用于生产、可在生产中规避），
            # 与设计无关 → 不计入造价；设计侧的花费修正是 build_cost_ic，那个会正常计入。
            policy_cost = bonuses.pop("production_cost_factor", None)
            mods = engine.combine_modifiers(mods, bonuses)
            if policy_cost is not None:
                # 这条是**生产产出花费**：设计侧不计入造价，但生产折算要算进去
                prod_mods = engine.combine_modifiers(pol.get("production_bonus") or {},
                                                     {"production_cost_factor": policy_cost})
            else:
                prod_mods = pol.get("production_bonus") or {}
            prod = engine.combine_modifiers(prod, prod_mods)
            info["policy"] = {"token": policy, "bonuses": bonuses,
                              "production_cost_factor_ignored": policy_cost,
                              "organization_modifier": pol.get("organization_modifier") or {}}
    info["production"] = prod
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


def _enemy_mod_line(inputs, field):
    """对手的「设计商修正 / 经验加成」，按用途取值（各用途一致时只写一条）。"""
    cfg = inputs.get("enemy") or {}
    roles = inputs.get("roles") or ["air_far"]
    year = inputs.get("current_year")
    seen = {}
    for role in roles:
        _cats, exp, mods = engine.enemy_spec(role, cfg, year=year)
        src = exp if field == "experience" else mods
        txt = "机动 %+g%% / 速度 %+g%%" % (
            round(src.get("air_agility", 0.0) * 100, 2),
            round(src.get("maximum_speed", 0.0) * 100, 2))
        seen.setdefault(txt, []).append(engine.ROLES.get(role, role))
    return "；".join("%s（%s）" % (t, "、".join(rs)) for t, rs in seen.items())


def _enemy_source_line(inputs):
    """对手数值是手填的、还是工具按模组 AI 权重自动判定的（写明是哪家 MIO）。"""
    cfg = inputs.get("enemy") or {}
    country = cfg.get("country") or ""
    hand = (cfg.get("by_country") or {}).get(country) or {}
    if hand:
        return "界面手填（优先于自动判定）；对手国别 = %s" % country
    role = (inputs.get("roles") or ["air_far"])[0]
    design = engine.enemy_design(country, role, inputs.get("current_year"))
    if not design:
        return "未找到该国空军 MIO，按「无设计商加成 + 满经验」算；对手国别 = %s" % country
    return ("按模组 ai_bonus_weights 自动判定：%s（满级 %d 项特质）｜对手国别 = %s"
            % (design["organization"], len(design["traits"]), country))


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
        ("对手设计商加成（机动/速度）", _enemy_mod_line(inputs, "modifiers")),
        ("对手联队经验加成（机动/速度）", _enemy_mod_line(inputs, "experience")),
        ("对手修正来源", _enemy_source_line(inputs)),
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
    # 2026-10-11 改口径：航程项从"乘实际航程"改成"乘 0~1 的航程效率（实际/目标）"。
    # 该机航程 ≥ 900（效率 = 1.0），所以旧锚点 ÷ 目标航程 900 就是新锚点：
    #     15540.543552 / 900 = 17.267270613…
    "score": 15540.543552 / 900,
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
    # 对手不再手填：由 engine.enemy_design() 按模组 ai_bonus_weights 自动判定
    # （德国 1944 战斗机 → 阿拉多，机动 +4% / 速度 +1.5%；见 §35）
    "enemy": {"country": "GER", "rule": "previous_year", "override_key": None},
}


def anchor_check(tol=1e-3):
    """锚点校验（2026-10-09 定为验收口径）：对空 + 距离 900。

    用 inputs.json 的制造商手填值（= 表内那套），检查
      Yak-9U@1944 的对空远分数 = 15540.543552 / 900 = 17.267270613…
        （2026-10-11 前是 15540.543552＝乘实际航程；现在乘 0~1 航程效率，见 PLAN §25）
      对手 Bf 109 G-14 的最终机动/速度 = 86.112 / 708.72375
        （对手的"设计商修正"是工具按模组 ai_bonus_weights 自动判定的：
          德国战斗机 → 阿拉多，机动 +4% / 速度 +1.5%，见 §35）
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
    # 附加检查：对手 AI 的设计判定（这条是把"德国实测面板"当基准反推出来的）
    design = engine.enemy_design("GER", ANCHOR["role"], ANCHOR["year"], data=data)
    ok = True
    if not design:
        print("对手 AI 判定：找不到德国空军 MIO ✗")
        ok = False
    else:
        mods = design["modifiers"]
        print("对手 AI 判定：%s → %s（满级 %d 项特质）机动 %+g%% / 速度 %+g%%"
              % (design["plane"], design["organization"], len(design["traits"]),
                 round(mods.get("air_agility", 0) * 100, 2),
                 round(mods.get("maximum_speed", 0) * 100, 2)))
        for want_org, want in (("GER_arado_flugzeugwerke_organization", (0.04, 0.015)),):
            if design["organization"] != want_org:
                print("  ✗ 期望阿拉多，实际 %s" % design["organization"])
                ok = False
            if (abs(mods.get("air_agility", 0) - want[0]) > tol
                    or abs(mods.get("maximum_speed", 0) - want[1]) > tol):
                print("  ✗ 期望机动 +4%% / 速度 +1.5%，实际 %+g%% / %+g%%"
                      % (mods.get("air_agility", 0) * 100, mods.get("maximum_speed", 0) * 100))
                ok = False
    rows, _mods, enemy, enemy_values, _info = build_rows(inputs, data)
    top = next((r for r in rows if r["role"] == ANCHOR["role"]), None)
    print("锚点校验：对空 + 距离 %.0f（当前年份/科技年份 %d）" % (ANCHOR["range_cap"], ANCHOR["year"]))
    print("  对手          %s" % (enemy["name"] if enemy else "（无）"))
    if enemy_values:
        print("  对手机动/速度  %.5f / %.5f（期望 %.5f / %.5f）"
              % (enemy_values["agility"], enemy_values["speed"],
                 ANCHOR["enemy_agility"], ANCHOR["enemy_speed"]))
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
