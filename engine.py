#!/usr/bin/env python3
"""BI_SOV 飞机选型引擎（B2）

实现 BI_SOV.xlsx「飞机改装」表的全部口径，并提供：
  - 单机构型求值（八项数值 + 有效造价 + 七个用途分数）
  - 贪心改装搜索（按边际性价比 > 1 逐步加改装）
  - 对手选取（默认该国 year <= 当前年份-1 中 priority 最高者）
  - 制造商加成合成（MIO 特质按权重贪心，或直接给定修正）
  - golden 回归：用 BI_SOV.xlsx 现成的输入复算，与表内分数逐格比对

用法：
    python engine.py --golden
    python engine.py --demo --year 1944 --tech-year 1944
"""

import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# 手工表「飞机改装」14 项改装（按表内行顺序），与游戏 token 的对应已核对
SHEET_UPGRADES = [
    "plane_gun_upgrade",
    "plane_engine_upgrade",
    "plane_range_upgrade",
    "plane_reliability_upgrade",
    "plane_naval_upgrade",
    "plane_fighter_bomb_upgrade",
    "plane_drop_tank_upgrade",
    "plane_light_cannons_upgrade",
    "plane_anti_air_rocket_upgrade",
    "plane_bubble_canopy_upgrade",
    "plane_turret_defence_upgrade",
    "plane_airframe_upgrade",
    "plane_heavy_cannons_upgrade",
    "plane_cas_upgrade",
]

# ---------------------------------------------------------------------------
# 口径常量（2026-10-08 按 BICE 定义确定；wiki 描述的是原版）
#
# 空战：原版 COMBAT_BETTER_AGILITY_DAMAGE_REDUCTION=0.45、COMBAT_BETTER_SPEED_DAMAGE_INCREASE=0.65、
# 封顶 4.0 / 3.5；BICE 分别是 1.3 / 3.0，封顶 1.7 / 2.0。
# 事故：原版 ACCIDENT_CHANCE_BASE=0.1、BALANCE_MULT=0.10、RELIABILITY_MULT=2.0、EFFECT_MULT=0.007；
# BICE 为 0.06 / 0.75 / 1.0 / 0.005。
# 年损失率 f = 换算常数 × (1 − 可靠度)：
#   逐小时损失 = BASE × BALANCE × REL_MULT × (EFFECT×100/2)
#   年损失率   = 逐小时损失/100 × 8760
#   BICE（含 BALANCE）：0.06×0.75×1.0×0.25 = 0.01125 → 0.01125/100×8760 = 0.9855
#   若不计 BALANCE（旧口径）：1.314
# 下面这些值来自模组 common/defines/00_defines.lua 的 NAir 段（data/defines.json）。
# 表里是兜底默认值，模组更新后重跑 extract_game_data.py 即同步。
AIR_DEFINE_DEFAULTS = {
    "ACCIDENT_CHANCE_BASE": 0.06,
    "ACCIDENT_CHANCE_CARRIER_MULT": 1.25,
    "ACCIDENT_CHANCE_BALANCE_MULT": 0.75,
    "ACCIDENT_CHANCE_RELIABILITY_MULT": 1.0,
    "ACCIDENT_EFFECT_MULT": 0.005,
    "COMBAT_BETTER_AGILITY_DAMAGE_REDUCTION": 1.3,
    "COMBAT_BETTER_SPEED_DAMAGE_INCREASE": 3.0,
    "BIGGEST_AGILITY_FACTOR_DIFF": 1.7,
    "BIGGEST_SPEED_FACTOR_DIFF": 2.0,
}


def _load_air_defines():
    path = os.path.join(DATA_DIR, "defines.json")
    out = dict(AIR_DEFINE_DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for key, value in (json.load(fh) or {}).items():
                if key in out:
                    out[key] = value
    return out


AIR_DEFINES = _load_air_defines()

COMBAT_AGILITY_DAMAGE_REDUCTION = AIR_DEFINES["COMBAT_BETTER_AGILITY_DAMAGE_REDUCTION"]
COMBAT_SPEED_DAMAGE_INCREASE = AIR_DEFINES["COMBAT_BETTER_SPEED_DAMAGE_INCREASE"]
BIGGEST_AGILITY_FACTOR_DIFF = AIR_DEFINES["BIGGEST_AGILITY_FACTOR_DIFF"]
BIGGEST_SPEED_FACTOR_DIFF = AIR_DEFINES["BIGGEST_SPEED_FACTOR_DIFF"]
# 年损失率 f = 系数 × (1 − 可靠度)。
# wiki 正文给出的链：每小时事故率 = 10%(BASE) × 0.1(BALANCE) × 2× (1−可靠度)(REL_MULT) × 其它修正，
# 平均损失 = 事故率 × 0.35%（= 0.5 × 0.7%，EFFECT_MULT/2）。
# 但 wiki 自己的算例写的是 10% × (1−可靠度) × 2 × 0.35% = 0.07%/小时（80% 可靠度→0.014%/小时→122%/年），
# **漏了 BALANCE**——两者只能取一个口径：
#
#   口径 A（不计 BALANCE，与 wiki 算例一致）
#     原版：10% × 2 × 0.35%                        = 0.07  %/小时 → 年 613%  (×0.2 → 122%) ✓ 与 wiki 算例吻合
#     BICE： 6% × 1.0 × 0.25%                      = 0.015 %/小时 → f = 1.314
#     相对原版：0.015/0.07 = 0.214（BICE 事故率是原版的 21%）
#
#   口径 B（计 BALANCE，与 wiki 正文一致；此时 wiki 的算例数值不成立，应为 0.007%/小时）
#     原版：10% × 0.1 × 2 × 0.35%                  = 0.007 %/小时
#     BICE： 6% × 0.75 × 1.0 × 0.25%               = 0.01125 %/小时 → f = 0.9855
#     相对原版：0.01125/0.007 = 1.607（BICE 事故率是原版的 161%）
#
# 两个口径下 BICE 自身相差 0.75 倍（BALANCE 0.75）——即"纳入 BALANCE 会让年损失率降 25%"。
# 引擎默认用口径 B（用户 2026-10-08 决定纳入 0.75）。
# 2026-10-08 游戏内 tooltip 实证（决定性）：可靠度 65% 时显示
#   「随机起降事故几率：基础 6%，装备可靠性 35%，经验 0%，最终值 2.1%」
#   6% × 35% = 2.1%  ⇒  每小时事故率 = BASE × (1 − 可靠度)，**没有 BALANCE、也没有 ×2**
# 因此口径 B（把 BALANCE 乘进去）不成立，采用口径 A：
#   f = 8760 × BASE × (事故平均毁伤 EFFECT_MULT/2) = 8760 × 0.06 × 0.0025 = 1.314
# 唯一仍未定的是「每次事故平均毁伤比例」：wiki 说平均 0.7%、BICE 定义给 0.005(→平均 0.25%)；
#   首次实测（8 队×50 架同机场、可靠度65%、46 天、损失 11 架）反推有效 f ≈ 0.62，介于两者之间偏低。
ACCIDENT_MODE = "with_balance"            # 2026-10-08 用户实验确定：BALANCE 在链条里（0 → 完全无损耗）
ACCIDENT_CHANCE_BASE = AIR_DEFINES["ACCIDENT_CHANCE_BASE"]
ACCIDENT_EFFECT_MULT = AIR_DEFINES["ACCIDENT_EFFECT_MULT"]
ACCIDENT_CHANCE_BALANCE_MULT = AIR_DEFINES["ACCIDENT_CHANCE_BALANCE_MULT"]
ACCIDENT_CHANCE_CARRIER_MULT = AIR_DEFINES["ACCIDENT_CHANCE_CARRIER_MULT"]
# 年事故折损系数 f = 8760 小时 × 每小时事故率 × 每次事故平均毁伤(EFFECT_MULT/2)
#   BICE：8760 × 0.06 × (0.005/2) × 0.75 = 0.9855
ACCIDENT_FACTOR = (8760.0 * ACCIDENT_CHANCE_BASE * (ACCIDENT_EFFECT_MULT / 2.0)
                   * (ACCIDENT_CHANCE_BALANCE_MULT if ACCIDENT_MODE == "with_balance" else 1.0))
# 停放在航母上的飞机事故率再乘 ACCIDENT_CHANCE_CARRIER_MULT（BICE = 1.25）
ACCIDENT_FACTOR_CARRIER = ACCIDENT_FACTOR * ACCIDENT_CHANCE_CARRIER_MULT


def accident_factor(carrier=False):
    """年事故折损系数 f。舰载用途（停在航母上）要乘 ACCIDENT_CHANCE_CARRIER_MULT。"""
    return ACCIDENT_FACTOR_CARRIER if carrier else ACCIDENT_FACTOR


# 空战伤害项的地板。游戏里这一项是 MAX(公式, 0)（伤害乘子），
# 但 0 会让"战力比"退化成 0/0，整列机型并列 0 分、排名失去意义。
# 所以做**排名分数**时把地板抬到 0.05：低于此值在游戏里等价于"打不动"，
# 抬起来只是保留强弱区分度，不影响任何本来就 > 0.05 的机型（锚点机型是 0.6061）。
COMBAT_FACTOR_FLOOR = 0.05

# 「效果」的指数表（Cobb–Douglas 弹性）：效果 = Π 属性^指数，再除以有效造价。
# 指数含义 = "该属性翻倍，分数涨 2^指数 倍"：1.0 → ×2；0.5 → ×1.41。
# 改权重只动这张表，不用改公式。当前值与历史上的硬编码完全一致（对空三项都是 1）。
EFFECT_EXPONENTS = {
    "air": {"attack": 1.0, "defence": 1.0, "ratio": 1.0},
    "ground": {"ground_attack": 1.0, "defence": 0.5},        # 防御是次要属性 → 开方
    "naval": {"naval_attack": 1.0, "aiming": 1.0, "defence": 0.5},
    "recon": {"range": 1.0},
}
# 兼容旧引用（对地/对海的防御指数）
NON_AIR_DEFENCE_EXPONENT = EFFECT_EXPONENTS["ground"]["defence"]


def effect_score(mission, terms):
    """按 EFFECT_EXPONENTS 把若干属性乘起来（缺省指数 1）。"""
    exps = EFFECT_EXPONENTS[mission]
    out = 1.0
    for key, value in terms.items():
        out *= value ** exps.get(key, 1.0)
    return out
GOLDEN_SHEET_CONSTANTS = True             # golden 回归时用表内（原版）系数，保持可比
DEFAULT_RANGE_CAP = 900.0
GROUND_FLOOR = 0.0001

ROLES = {
    "air_near": "对空（近）",
    "air_far": "对空（远）",
    "recon": "侦察/运输",
    "ground_near": "对地（近）",
    "ground_far": "对地（远）",
    "naval_near": "对海（近）",
    "naval_far": "对海（远）",
    # 舰载专用用途（只挑能上舰的机种）；注意追加在末尾，golden 依赖前 7 个的顺序
    "air_cv": "对空（舰载）",
    "naval_cv": "对海（舰载）",
}

# golden 回归按这 7 个（表内 V19:AB19 的列顺序）比对，不要改顺序
GOLDEN_ROLE_ORDER = ("air_near", "air_far", "recon", "ground_near", "ground_far",
                     "naval_near", "naval_far")

# 用途 → 国家精神（national_ideas）的装备类别，**按优先级排序**。
#
# BICE 会把同一个国家精神在多个装备类别里各写一份（例如 SOV_improved_designs 在
# fighter_equipment / fighter_alt_equipment / interceptor_equipment / twin_cas_equipment
# 里都有同名条目）。所以不能把类别取并集后逐个累加——那会把同一份修正算好几遍。
# 规则：对每个国家精神名，按下面这个优先级找出**第一个命中的类别**，取它、然后停止。
# 这样「针对战斗机的精神」在选了对地时自然落不到（除非它在 CAS 类别里也有条目）。
ROLE_IDEA_CATEGORIES = {
    "air_near": ("fighter_equipment", "fighter_alt_equipment", "interceptor_equipment",
                 "mr_fighter_equipment", "jet_fighter_equipment", "heavy_fighter_equipment",
                 "night_fighter_equipment", "fighter_navy_equipment",
                 "interceptor_navy_equipment", "rocket_interceptor_equipment",
                 "jet_mr_fighter_equipment", "cv_fighter_equipment", "cv_mr_fighter_equipment"),
    "air_far": ("fighter_equipment", "fighter_alt_equipment", "interceptor_equipment",
                "mr_fighter_equipment", "jet_fighter_equipment", "heavy_fighter_equipment",
                "night_fighter_equipment", "fighter_navy_equipment",
                "interceptor_navy_equipment", "rocket_interceptor_equipment",
                "jet_mr_fighter_equipment", "cv_fighter_equipment", "cv_mr_fighter_equipment"),
    "ground_near": ("twin_cas_equipment", "cas_equipment", "jet_cas_equipment",
                    "mr_fighter_equipment", "jet_mr_fighter_equipment"),
    "ground_far": ("twin_cas_equipment", "cas_equipment", "jet_cas_equipment",
                   "mr_fighter_equipment", "jet_mr_fighter_equipment"),
    "naval_near": ("nav_bomber_equipment", "heavy_nav_bomber_equipment",
                   "nav_bomber_gb_equipment", "cv_nav_bomber_equipment", "naval_bomber"),
    "naval_far": ("nav_bomber_equipment", "heavy_nav_bomber_equipment",
                  "nav_bomber_gb_equipment", "cv_nav_bomber_equipment", "naval_bomber"),
    "recon": ("scout_plane_equipment", "transport_plane_equipment"),
    "air_cv": ("cv_fighter_equipment", "cv_mr_fighter_equipment"),
    "naval_cv": ("cv_nav_bomber_equipment",),
}


def role_idea_categories(roles):
    """把若干用途合成一个**有序**的国家精神类别列表（去重、保序）。"""
    out = []
    for role in roles or []:
        for cat in ROLE_IDEA_CATEGORIES.get(role, ()):
            if cat not in out:
                out.append(cat)
    return out


# 用途 → 候选机身的 archetype（决定"这一类任务能用哪些飞机"）。
# 注意 archetype 名与游戏文件一致（CAS 是大写），与上面的 idea 类别名不完全相同。
ROLE_MISSION = {
    "air_near": "air", "air_far": "air",
    "ground_near": "ground", "ground_far": "ground",
    "naval_near": "naval", "naval_far": "naval",
    "recon": "recon",
    "air_cv": "air_cv", "naval_cv": "naval_cv",
}
# 舰载机能下舰（陆基机场也能用），所以陆基用途把 cv_ 也算进来；
# 反过来普通机不能上舰，所以舰载用途只留 cv_。
_CARRIER_FIGHTERS = ("cv_fighter_equipment", "cv_mr_fighter_equipment")
_CARRIER_NAVAL = ("cv_nav_bomber_equipment",)
MISSION_ARCHETYPES = {
    # 对空：陆基战斗机族 + 舰载战斗机
    "air": ("fighter_equipment", "fighter_alt_equipment", "interceptor_equipment",
            "mr_fighter_equipment", "jet_fighter_equipment", "heavy_fighter_equipment",
            "night_fighter_equipment", "fighter_navy_equipment", "interceptor_navy_equipment",
            "rocket_interceptor_equipment", "jet_mr_fighter_equipment") + _CARRIER_FIGHTERS,
    # 对空（舰载）：只有舰载战斗机
    "air_cv": _CARRIER_FIGHTERS,
    # 对地：CAS 族 + 多用途战斗机（多用途既是战斗机也是近距支援机，两边都算）
    "ground": ("CAS_equipment", "twin_cas_equipment", "jet_cas_equipment",
               "mr_fighter_equipment", "jet_mr_fighter_equipment"),
    # 对海：海军轰炸机族 + 舰载海军轰炸机
    "naval": ("nav_bomber_equipment", "heavy_nav_bomber_equipment",
              "nav_bomber_gb_equipment") + _CARRIER_NAVAL,
    # 对海（舰载）：只有舰载海军轰炸机
    "naval_cv": _CARRIER_NAVAL,
    "recon": ("scout_plane_equipment", "transport_plane_equipment"),
}

# 用途 → 计算用的分数键。舰载版与陆基版共用同一套公式（"远"口径，距离由 range_cap 决定），
# 区别只在候选机种。
SCORE_ROLE = {"air_cv": "air_far", "naval_cv": "naval_far"}


def score_role(role):
    return SCORE_ROLE.get(role, role)


def role_archetypes(roles):
    """把若干用途合成一个**有序**的机身 archetype 列表（去重、保序）。"""
    out = []
    for role in roles or []:
        for arch in MISSION_ARCHETYPES.get(ROLE_MISSION.get(role, ""), ()):
            if arch not in out:
                out.append(arch)
    return out

# 各用途经验加成（满级联队经验，正式版；逐属性不同）
EXPERIENCE_BONUS = {
    "air_attack": 0.10,
    "air_defence": 0.10,
    "air_agility": 0.20,
    "maximum_speed": 0.05,
    "air_ground_attack": 0.10,
    "naval_strike_attack": 0.10,
    "naval_strike_targetting": 0.15,
    "air_bombing": 0.10,
}


def load_data():
    data = {}
    for name in ("airframes", "airframes_all", "upgrades", "national_ideas", "mio", "archetypes",
                 "policies", "special_projects", "tech_years"):
        path = os.path.join(DATA_DIR, name + ".json")
        data[name] = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    return data


def available_upgrades(category, data, techs=(), flags=(), require_prereqs=True, archetype=None):
    """该机身允许的改装轨（按游戏 archetype 的 upgrades 列表），并过滤未解锁的前置。

    给了 archetype 就按 archetype 查（推荐，机种多了之后 category 不再唯一）；否则退回按 category 查。
    """
    allowed = None
    for entry in data["archetypes"]:
        if (archetype and entry["archetype"] == archetype) or \
                (not archetype and entry["category"] == category):
            allowed = set(entry["upgrades"])
            break
    upgrade_map = upgrades_by_key(data["upgrades"])
    out = []
    for token, up in upgrade_map.items():
        if token.startswith("cv_"):
            continue
        if allowed is not None and token not in allowed:
            continue
        if require_prereqs:
            req = up.get("requires") or {}
            if any(t not in techs for t in req.get("techs", [])):
                continue
            if any(f not in flags for f in req.get("flags", [])):
                continue
        out.append(token)
    return out, upgrade_map


def resource_weighted(scores, airframe):
    """资源加权分数 = 纯分数 ÷ 飞机装配资源开销（用户口径，暂不含发动机装配）。"""
    cost = airframe.get("air_production") or 0
    if not cost:
        return {}
    return {role: value / cost for role, value in scores.items()}


def upgrades_by_key(upgrades):
    return {u["key"]: u for u in upgrades}


# ----------------------------------------------------------------------------
# 核心口径
# ----------------------------------------------------------------------------

def combine_modifiers(*sources):
    """把若干 {属性: 修正(小数)} 相加。"""
    out = {}
    for src in sources:
        for key, value in (src or {}).items():
            out[key] = out.get(key, 0.0) + float(value)
    return out


def evaluate(base, levels, upgrade_map, mods, enemy, range_cap=DEFAULT_RANGE_CAP,
             experience=None, reliability_override=None, bice_combat=True,
             accident_factor=None):
    """返回 (最终数值 dict, 有效造价, 七用途分数 dict)。

    base 为机型基础值；levels 为 {token: 次数}；mods 为制造商/国家精神/手填的修正合计；
    enemy 为 {'agility': x, 'speed': y}（缺省视为同型机）。
    """
    exp = dict(experience or {})
    coef = dict(mods)
    add = {}
    for token, count in levels.items():
        if not count:
            continue
        up = upgrade_map.get(token)
        if not up:
            continue
        for key, value in up["modifiers"].items():
            coef[key] = coef.get(key, 0.0) + value * count
        for key, value in up["add_stats"].items():
            add[key] = add.get(key, 0.0) + value * count
    # 口径（已用表内与实测双重验证）：
    #   设计阶段 = 基础 × (1 + 制造商 + 国家精神 + 改装合计) + 改装数值增量
    #   最终     = 设计阶段 × (1 + 联队经验 + 王牌)      ← 经验是**独立乘算**，不与上面加算
    FIELD = {"air_attack": "attack", "air_defence": "defence", "air_agility": "agility",
             "maximum_speed": "speed", "air_ground_attack": "ground_attack",
             "air_range": "range", "reliability": "reliability", "build_cost_ic": "cost"}

    def stage(key):
        return base[FIELD[key]] * (1 + coef.get(key, 0.0)) + add.get(key, 0.0)

    values = {
        "attack": stage("air_attack") * (1 + exp.get("air_attack", 0.0)),
        "defence": stage("air_defence") * (1 + exp.get("air_defence", 0.0)),
        "agility": stage("air_agility") * (1 + exp.get("air_agility", 0.0)),
        "speed": stage("maximum_speed") * (1 + exp.get("maximum_speed", 0.0)),
        "ground_attack": stage("air_ground_attack") * (1 + exp.get("air_ground_attack", 0.0)),
        "range": min(stage("air_range") * (1 + exp.get("air_range", 0.0)), range_cap),
        # 可靠性是乘算（实测：Bf 109 G-14 基础 0.59，维护 1 级 → 0.59×1.0375 = 0.6121）
        "reliability": (base["reliability"] * (1 + coef.get("reliability", 0.0))
                        * (1 + exp.get("reliability", 0.0))
                        if reliability_override is None else reliability_override),
        "cost": base["cost"] * (1 + coef.get("build_cost_ic", 0.0)),
        # 对海同样用机型**自身的**属性：base × (1+改装/制造商) + 增量，再乘经验
        # （以前这里只有 (1+修正) 这个乘子，因为 naval_strike_* 两个字段根本没抽）
        "naval_attack": (base.get("naval_strike_attack", 0.0)
                         * (1 + coef.get("naval_strike_attack", 0.0))
                         + add.get("naval_strike_attack", 0.0))
                        * (1 + exp.get("naval_strike_attack", 0.0)),
        "aiming": (base.get("naval_strike_targetting", 0.0)
                   * (1 + coef.get("naval_strike_targetting", 0.0))
                   + add.get("naval_strike_targetting", 0.0))
                  * (1 + exp.get("naval_strike_targetting", 0.0)),
    }
    values["effective_cost"] = values["cost"] * (
        1 + (ACCIDENT_FACTOR if accident_factor is None else accident_factor)
        * (1 - values["reliability"]))

    if bice_combat:
        a, s = COMBAT_AGILITY_DAMAGE_REDUCTION, COMBAT_SPEED_DAMAGE_INCREASE
        cap_a, cap_s = BIGGEST_AGILITY_FACTOR_DIFF, BIGGEST_SPEED_FACTOR_DIFF
    else:  # 表内（原版）系数
        a, s = 0.45, 0.65
        cap_a, cap_s = 4.0, 3.5
    r_agility = values["agility"] / enemy["agility"] if enemy and enemy.get("agility") else 1.0
    r_speed = values["speed"] / enemy["speed"] if enemy and enemy.get("speed") else 1.0
    # 我打对手（对手的机动/速度做分母）与对手打我，两侧各自套封顶，然后取比值
    # 等价于模组/wiki 的写法：MAX(-0.7 - 1.3×MIN(机动比,1.7) + 3.0×MIN(速度比,2.0), 0)
    floor = COMBAT_FACTOR_FLOOR
    mine = max(1 - a * (min(1 / r_agility, cap_a) - 1) + s * (min(r_speed, cap_s) - 1), floor)
    theirs = max(1 - a * (min(r_agility, cap_a) - 1) + s * (min(1 / r_speed, cap_s) - 1), floor)
    ratio = mine / theirs          # 两侧都有了正地板，ratio 恒 > 0，不会再出现 0 或 ∞

    cost = values["effective_cost"]
    ground = max(values["ground_attack"], GROUND_FLOOR)
    # 效果一律按 EFFECT_EXPONENTS 合成，再除以有效造价（对空/侦察的指数都是 1，与旧口径等价）
    air_near = effect_score("air", {"attack": values["attack"],
                                    "defence": values["defence"], "ratio": ratio}) / cost
    ground_near = effect_score("ground", {"ground_attack": ground,
                                          "defence": values["defence"]}) / cost
    naval_near = effect_score("naval", {"naval_attack": values["naval_attack"],
                                        "aiming": values["aiming"],
                                        "defence": values["defence"]}) / cost
    scores = {
        "air_near": air_near,
        "air_far": air_near * values["range"],
        "recon": effect_score("recon", {"range": values["range"]}) / cost,
        "ground_near": ground_near,
        "ground_far": ground_near * values["range"],
        "naval_near": naval_near,
        "naval_far": naval_near * values["range"],
    }
    return values, values["effective_cost"], scores


def optimize(base, upgrade_map, mods, enemy, role="air_near", available=None,
             range_cap=DEFAULT_RANGE_CAP, experience=None, max_steps=60, accident_f=None):
    """贪心：每步取边际性价比最高且 > 1 的改装加一级。"""
    tokens = [t for t in (available or SHEET_UPGRADES) if t in upgrade_map]
    levels = {t: 0 for t in tokens}
    _, _, scores = evaluate(base, levels, upgrade_map, mods, enemy, range_cap, experience,
                            accident_factor=accident_f)
    current = scores[role]
    steps = []
    for _ in range(max_steps):
        best = None
        for token in tokens:
            up = upgrade_map[token]
            if levels[token] >= up["max_level"]:
                continue
            levels[token] += 1
            _, _, trial = evaluate(base, levels, upgrade_map, mods, enemy, range_cap, experience,
                                   accident_factor=accident_f)
            levels[token] -= 1
            gain = trial[role] / current if current else 0.0
            if best is None or gain > best[0]:
                best = (gain, token)
        if not best or best[0] <= 1.0:
            break
        levels[best[1]] += 1
        _, _, scores = evaluate(base, levels, upgrade_map, mods, enemy, range_cap, experience,
                                accident_factor=accident_f)
        current = scores[role]
        steps.append({"token": best[1], "gain": round(best[0], 6)})
    values, eff_cost, scores = evaluate(base, levels, upgrade_map, mods, enemy, range_cap, experience,
                                        accident_factor=accident_f)
    return {"levels": levels, "values": values, "scores": scores,
            "effective_cost": eff_cost, "steps": steps}


# ----------------------------------------------------------------------------
# 对手选取 / 制造商
# ----------------------------------------------------------------------------

def pick_enemy(all_airframes, country, year, category=None, override_key=None,
               rule="previous_year"):
    """对手选取。

    rule="previous_year"（默认）：year <= 当前年份-1 中 priority 最高者
    rule="same_year"：year <= 当前年份 中 priority 最高者
    override_key：手动指定机型 key
    category：机种类别，可以是单个字符串或一串（任一命中即可）
    """
    if override_key:
        for a in all_airframes:
            if a["key"] == override_key:
                return a
        return None
    limit = year - 1 if rule == "previous_year" else year
    cands = [a for a in all_airframes
             if a.get("country") == country and (a.get("year") or 0) <= limit]
    if category:
        wanted = (category,) if isinstance(category, str) else tuple(category)
        same = [a for a in cands if a["category"] in wanted]
        if same:
            cands = same
    if not cands:
        return None
    return max(cands, key=lambda a: ((a.get("priority") or 0), a.get("year") or 0))


# 舰载用途的对手也是舰载机，并且不吃经验加成（避免拿陆基王牌去压舰载机）
CARRIER_ROLES = ("air_cv", "naval_cv")
CARRIER_ENEMY_CATEGORIES = {
    "air_cv": ("cv_fighter", "cv_mr_fighter"),
    "naval_cv": ("cv_nav_bomber",),
}


def enemy_spec(role, enemy_cfg):
    """该用途对应的 (对手机种类别, 经验加成, 制造商修正)。"""
    cfg = enemy_cfg or {}
    if role in CARRIER_ROLES:
        return CARRIER_ENEMY_CATEGORIES[role], {}, cfg.get("modifiers") or {}
    return ("fighter",), cfg.get("experience") or {}, cfg.get("modifiers") or {}


def pick_enemy_values(all_airframes, enemy_cfg, role, year):
    """按用途取对手及其最终机动/速度。返回 (对手条目, 数值 dict)，找不到时为 (None, None)。"""
    cfg = enemy_cfg or {}
    cats, exp, mods = enemy_spec(role, cfg)
    enemy = pick_enemy(all_airframes, cfg.get("country", "GER"), year, category=cats,
                       override_key=cfg.get("override_key"),
                       rule=cfg.get("rule", "previous_year"))
    if not enemy:
        return None, None
    values = {
        "agility": enemy["agility"] * (1 + mods.get("air_agility", 0.0))
                   * (1 + exp.get("air_agility", 0.0)),
        "speed": enemy["speed"] * (1 + mods.get("maximum_speed", 0.0))
                 * (1 + exp.get("maximum_speed", 0.0)),
    }
    return enemy, values


def mio_traits(org):
    traits = list(org.get("traits", []))
    initial = org.get("initial_trait")
    return ([initial] if initial else []) + traits


def pick_mio_traits(org, level, base, upgrade_map, mods, enemy, roles, range_cap,
                    experience=None, techs=()):
    """按「加权收益 × ai_will_do」贪心选 level 个特质（近似 AI 选择）。

    调用方应已把 initial_trait 的加成放进 mods——它不占等级、也不参与挑选，避免重复计入。

    返回 (选中特质列表, 修正合计, 选择过程)。
    """
    all_traits = [t for t in org.get("traits", []) if t.get("token")]
    tech_set = set(techs or ())
    all_traits = [t for t in all_traits
                  if all(x in tech_set for x in (t.get("requires_techs") or []))]
    orig_roles = list(roles or []) or ["air_far"]
    roles = [score_role(r) for r in orig_roles]
    # 舰载用途的事故折损系数不同（ACCIDENT_CHANCE_CARRIER_MULT），逐个用途取
    role_accident = {score_role(r): accident_factor(r in CARRIER_ROLES) for r in orig_roles}
    chosen, chosen_tokens = [], set()
    mods_now = dict(mods)
    log = []
    for step in range(level):
        best = None
        for trait in all_traits:
            token = trait.get("token")
            if not token or token in chosen_tokens:
                continue
            if any(t in chosen_tokens for t in trait.get("mutually_exclusive", [])):
                continue
            ok = True
            for kind, parents in trait.get("parents", []):
                if kind == "all_parents" and not all(p in chosen_tokens for p in parents):
                    ok = False
                if kind == "any_parent" and not any(p in chosen_tokens for p in parents):
                    ok = False
            if not ok:
                continue
            gain = 0.0
            for role in roles:
                before = optimize(base, upgrade_map, mods_now, enemy, role,
                                  range_cap=range_cap, experience=experience,
                                  accident_f=role_accident.get(role))["scores"][role]
                after_mods = combine_modifiers(mods_now, trait.get("bonuses", {}))
                after = optimize(base, upgrade_map, after_mods, enemy, role,
                                 range_cap=range_cap, experience=experience,
                                 accident_f=role_accident.get(role))["scores"][role]
                if before:
                    gain += after / before - 1
            weight = trait.get("ai_will_do") or 1.0
            score = gain * weight
            if best is None or score > best[0]:
                best = (score, trait)
        if not best:
            break
        trait = best[1]
        chosen.append(trait)
        chosen_tokens.add(trait["token"])
        mods_now = combine_modifiers(mods_now, trait.get("bonuses", {}))
        log.append({"token": trait["token"], "score": round(best[0], 6),
                    "bonuses": trait.get("bonuses", {})})
    return chosen, mods_now, log


# MIO「满级」步数上限（够覆盖任何组织的特质树；贪心会在没有正收益时提前停）
MIO_MAX_LEVEL = 14


def _trait_tree(org, techs=()):
    """把组织的特质按"前置在前"排好序，并给出前提/互斥的索引关系。

    有科技门槛（`requires_techs`）而科技没解锁的特质直接排除。
    """
    tech_set = set(techs or ())
    traits = [t for t in org.get("traits", [])
              if t.get("token")
              and all(x in tech_set for x in (t.get("requires_techs") or []))]
    by_token = {t["token"]: t for t in traits}
    order, seen = [], set()

    def visit(t):
        if t["token"] in seen:
            return
        seen.add(t["token"])
        for _kind, parents in t.get("parents") or []:
            for p in parents:
                if p in by_token:
                    visit(by_token[p])
        order.append(t)

    for t in traits:
        visit(t)
    idx = {t["token"]: i for i, t in enumerate(order)}
    req_all, req_any, excl = [], [], []
    for t in order:
        allp, anyp = [], []
        for kind, parents in t.get("parents") or []:
            ids = [idx[p] for p in parents if p in idx]
            (allp if kind == "all_parents" else anyp).extend(ids)
        req_all.append(allp)
        req_any.append(anyp)
        excl.append([idx[e] for e in t.get("mutually_exclusive") or [] if e in idx])
    return order, req_all, req_any, excl


def mio_feasible_sets(org, max_level=MIO_MAX_LEVEL, techs=()):
    """枚举前提闭包内、大小 ≤ max_level 的所有可行特质子集（bitmask 列表）。"""
    order, req_all, req_any, excl = _trait_tree(org, techs)
    n = len(order)
    out = []

    def dfs(i, mask, picks):
        out.append(mask)                      # 任意大小都算一个候选（可能少选更优）
        if picks >= max_level or i >= n:
            return
        for j in range(i, n):
            if any(not (mask >> p) & 1 for p in req_all[j]):
                continue
            if req_any[j] and not any((mask >> p) & 1 for p in req_any[j]):
                continue
            if any((mask >> p) & 1 for p in excl[j]):
                continue
            dfs(j + 1, mask | (1 << j), picks + 1)

    dfs(0, 0, 0)
    return order, out


def pick_mio_traits_exact(org, level, base, upgrade_map, mods, enemy, roles, range_cap,
                          experience=None, max_level=MIO_MAX_LEVEL, techs=()):
    """满级配点用**穷举**求全局最优（贪心会陷局部最优）；再按边际收益排成路线，取前 level 步。

    目标函数：各用途的「该子集分数 ÷ 起始分数」之和（多用途时量级可比）。
    返回 (选中 token 列表, 修正合计, log)，log 每项 = {token, score, bonuses}。
    """
    order, masks = mio_feasible_sets(org, max_level, techs)
    role_list = [score_role(r) for r in (roles or [])] or ["air_far"]

    def score_of(chosen_mods):
        total = 0.0
        for role in role_list:
            value = evaluate(base, {}, upgrade_map, chosen_mods, enemy, range_cap, experience,
                             accident_factor=accident_factor(role in CARRIER_ROLES))[2][role]
            total += value / base_scores[role] if base_scores.get(role) else value
        return total

    base_scores = {}
    for role in role_list:
        base_scores[role] = evaluate(base, {}, upgrade_map, mods, enemy, range_cap, experience,
                                     accident_factor=accident_factor(role in CARRIER_ROLES))[2][role]

    best_mask, best_score = 0, score_of(mods)
    for mask in masks:
        if not mask:
            continue
        chosen_mods = dict(mods)
        i = 0
        m = mask
        while m:
            if m & 1:
                chosen_mods = combine_modifiers(chosen_mods, order[i].get("bonuses") or {})
            m >>= 1
            i += 1
        value = score_of(chosen_mods)
        if value > best_score:
            best_mask, best_score = mask, value

    # 在最优子集内部按边际收益排序，形成"升级路线"
    remaining = [i for i in range(len(order)) if (best_mask >> i) & 1]
    cur = dict(mods)
    log = []
    while remaining:
        pick, pick_value = None, None
        for i in remaining:
            value = score_of(combine_modifiers(cur, order[i].get("bonuses") or {}))
            if pick is None or value > pick_value:
                pick, pick_value = i, value
        cur = combine_modifiers(cur, order[pick].get("bonuses") or {})
        remaining.remove(pick)
        log.append({"token": order[pick]["token"], "score": round(pick_value, 8),
                    "bonuses": order[pick].get("bonuses") or {}})
    log = log[:max(0, int(level))]
    mods_now = dict(mods)
    for item in log:
        mods_now = combine_modifiers(mods_now, item["bonuses"])
    return [item["token"] for item in log], mods_now, log


def mio_route(org, level, base, upgrade_map, mods, enemy, roles, range_cap,
              experience=None, max_level=MIO_MAX_LEVEL, techs=()):
    """先按**满级**用穷举求出全局最优配点，再按边际收益排成路线、取前 `level` 步。

    这样低级时的配点就是"满级最优路线"的前缀——升级过程中不会出现半路改路线。
    返回 (选中 token 列表, 修正合计, 选择过程 log)。
    """
    return pick_mio_traits_exact(org, level, base, upgrade_map, mods, enemy, roles, range_cap,
                                 experience, max_level, techs)


def spirit_modifiers(ideas, names, category="fighter_equipment", categories=None):
    """按国家精神名取修正。

    category   单个装备类别（默认 fighter_equipment，兼容旧调用）
    categories 有序类别列表（见 role_idea_categories）；对每个精神名取**首个命中**的类别，
               命中即停止，避免同名条目跨类别重复累加。
    任何类别都不匹配的精神直接忽略（既不显示也不计算）。
    """
    order = list(categories) if categories is not None else ([category] if category else [])
    mods = {}
    for name in names or []:
        for cat in order:
            hit = next((e for e in ideas if e["idea"] == name and e["category"] == cat), None)
            if hit is not None:
                mods = combine_modifiers(mods, hit["modifiers"])
                break
    return mods


# ----------------------------------------------------------------------------
# golden 回归：与 BI_SOV.xlsx 现成输入逐格比对
# ----------------------------------------------------------------------------

def golden():
    import openpyxl

    print("注意：golden 比对的是 BI_SOV.xlsx「飞机改装」第 19 行那个**旧场景**，")
    print("      该行的输入在 2026-10-08 之后的表体重建里已被覆盖，因此这个比对可能长期不一致。")
    print("      当前验收口径请用：python run.py --anchor（对空 + 距离 900）")
    print()

    sheet_path = os.path.join(HERE, "BI_SOV.xlsx")
    wb = openpyxl.load_workbook(sheet_path, data_only=True)
    ws = wb["飞机改装"]

    base = {
        "range": ws["B3"].value, "defence": ws["C3"].value, "attack": ws["D3"].value,
        "agility": ws["E3"].value, "ground_attack": ws["F3"].value, "speed": ws["G3"].value,
        "reliability": ws["H3"].value, "cost": ws["I3"].value,
    }
    coef_map = {"K": "air_attack", "L": "air_defence", "M": "air_agility", "N": "maximum_speed",
                "O": "reliability", "P": "build_cost_ic", "Q": "air_range",
                "R": "air_ground_attack", "S": "naval_strike_attack", "T": "naval_strike_targetting"}
    mods = {key: (ws["%s3" % col].value or 0) / 100.0 for col, key in coef_map.items()}
    levels = {}
    for offset, token in enumerate(SHEET_UPGRADES):
        value = ws.cell(4 + offset, 21).value  # U4:U17
        levels[token] = int(value or 0)
    enemy = {"agility": ws["E20"].value, "speed": ws["G20"].value}
    range_cap = ws["B21"].value or DEFAULT_RANGE_CAP
    expected = [ws.cell(19, col).value for col in range(22, 29)]  # V19:AB19
    sheet_row = [ws.cell(19, col).value for col in range(2, 10)]  # B19:I19
    wb.close()

    data = load_data()
    upgrade_map = upgrades_by_key(data["upgrades"])
    values, eff_cost, scores = evaluate(base, levels, upgrade_map, mods, enemy, range_cap,
                                        bice_combat=not GOLDEN_SHEET_CONSTANTS,
                                        accident_factor=1.314)
    # 表内 H19 公式漏了制造商可靠系数（$O$3），用表内口径复算一遍作对照
    _, _, scores_sheet_quirk = evaluate(base, levels, upgrade_map, mods, enemy, range_cap,
                                        reliability_override=sheet_row[6],
                                        bice_combat=not GOLDEN_SHEET_CONSTANTS,
                                        accident_factor=1.314)
    order = list(GOLDEN_ROLE_ORDER)
    print("输入：基础=%s" % {k: round(v, 4) for k, v in base.items()})
    print("      修正=%s" % {k: round(v, 4) for k, v in mods.items()})
    print("      改装=%s" % {k: v for k, v in levels.items() if v})
    print("      对手机动=%.2f 速度=%.2f 航程上限=%s" % (enemy["agility"], enemy["speed"], range_cap))
    print()
    print("最终数值（引擎 vs 表内 B19:I19）:")
    for key, col, sheet_value in (
        ("range", "B", sheet_row[0]), ("defence", "C", sheet_row[1]),
        ("attack", "D", sheet_row[2]), ("agility", "E", sheet_row[3]),
        ("ground_attack", "F", sheet_row[4]), ("speed", "G", sheet_row[5]),
        ("reliability", "H", sheet_row[6]), ("cost", "I", sheet_row[7]),
    ):
        flag = "" if abs(values[key] - sheet_value) < 1e-9 else "   <== 不一致"
        print("  %-14s 引擎 %-14.6f 表内 %-14.6f%s" % (key, values[key], sheet_value, flag))
    print("  有效造价       引擎 %.6f（表内由 H19=%.4f 推得 %.6f）"
          % (eff_cost, sheet_row[6],
             values["cost"] * (1 + ACCIDENT_FACTOR * (1 - sheet_row[6]))))
    worst = 0.0
    print("%-12s %-22s %-22s %s" % ("用途", "引擎", "表内", "相对误差"))
    for role, exp in zip(order, expected):
        got = scores[role]
        err = abs(got - exp) / abs(exp) if exp else 0.0
        worst = max(worst, err)
        print("%-12s %-22.10f %-22.10f %.3e" % (ROLES[role], got, exp, err))
    print()
    print("最大相对误差：%.3e" % worst)
    quirk_worst = max(
        abs(scores_sheet_quirk[role] - exp) / abs(exp) for role, exp in zip(order, expected) if exp)
    print("按表内 H19 口径（即忽略制造商可靠系数）复算：最大相对误差 %.3e" % quirk_worst)
    values_ok = all(
        abs(values[key] - sheet_value) < 1e-9
        for key, sheet_value in zip(
            ("range", "defence", "attack", "agility", "ground_attack", "speed", "cost"),
            (sheet_row[0], sheet_row[1], sheet_row[2], sheet_row[3],
             sheet_row[4], sheet_row[5], sheet_row[7]))
    )
    print()
    print("结论：")
    print("  数值：引擎可靠度 %.5f vs 表内 %.5f（差 %.5f）"
          % (values["reliability"], sheet_row[6], values["reliability"] - sheet_row[6]))
    if abs(values["reliability"] - sheet_row[6]) > 1e-9:
        print("        差异原因：表内漏算 $O$3（制造商可靠系数），或用了加法 $H$3+Σ；"
              "正确的是 $H$3*(1+$O$3/100+Σ)")
    else:
        print("        表内与引擎口径一致（乘法 + 计入 $O$3）")
    print("  分数：按表内 H19 口径复算 %s；按引擎口径（计入 $O$3）%s"
          % ("一致 ✓" if quirk_worst < 1e-9 else "不一致 ✗",
             "偏高 %.3f%%" % ((worst - quirk_worst) * 100)))
    ok = quirk_worst < 1e-9 and values_ok
    print("golden 回归：%s" % ("通过 ✓（口径已复刻，另记表内 H19 漏项）" if ok else "未通过 ✗"))
    return 0 if ok else 1


def demo(year, tech_year, country="SOV", enemy_country="GER", roles=("air_near",)):
    data = load_data()
    upgrade_map = upgrades_by_key(data["upgrades"])
    player = [a for a in data["airframes"] if (a["year"] or 0) <= tech_year]
    enemy = pick_enemy(data["airframes_all"], enemy_country, year, category="fighter",
                       rule="previous_year")
    print("当前年份 %d，科技年份 %d，可用机型 %d 型" % (year, tech_year, len(player)))
    pools = {}
    for airframe in player:
        pools.setdefault(airframe["category"],
                         available_upgrades(airframe["category"], data)[0])
    for category, tokens in sorted(pools.items()):
        print("  %-12s 合法改装 %d 项：%s"
              % (category, len(tokens), ", ".join(t.replace("plane_", "").replace("_upgrade", "") for t in tokens)))
    if enemy:
        print("对手：%s（%s，%s 年，priority %s）机动 %.1f 速度 %.1f"
              % (enemy["name"], enemy["country"], enemy["year"], enemy["priority"],
                 enemy["agility"], enemy["speed"]))
        enemy_values = {"agility": enemy["agility"] * (1 + 0.04) * (1 + 0.20),
                        "speed": enemy["speed"] * (1 + 0.015) * (1 + 0.05)}
    else:
        enemy_values = None
    rows = []
    for airframe in player:
        tokens = available_upgrades(airframe["category"], data)[0]
        for role in roles:
            result = optimize(airframe, upgrade_map, {}, enemy_values, role, available=tokens)
            weighted = resource_weighted(result["scores"], airframe)
            rows.append((result["scores"][role], airframe, role, result, weighted))
    rows.sort(key=lambda r: -r[0])
    print()
    print("%-9s %-13s %-9s %-11s %s" % ("用途", "机型", "纯分数", "资源加权", "推荐设计"))
    for score, airframe, role, result, weighted in rows[:10]:
        design = " ".join("%s×%d" % (t, n) for t, n in result["levels"].items() if n)
        print("%-9s %-13s %-9.6f %-11.6f %s"
              % (role, airframe["name"][:13], score, weighted.get(role, 0.0),
                 design or "（无需改装）"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--year", type=int, default=1944)
    ap.add_argument("--tech-year", type=int, default=1944)
    args = ap.parse_args()
    if args.golden:
        return golden()
    if args.demo:
        demo(args.year, args.tech_year)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
