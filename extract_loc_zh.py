#!/usr/bin/env python3
"""抽取汉化名称（MIO 组织/特质、机型装备名）→ data/loc_zh.json

只收录 data/*.json 里真正用到的键，文件很小。

    python extract_loc_zh.py                      # 默认扫已启用的汉化 mod
    python extract_loc_zh.py --dir <路径> [...]   # 指定汉化目录（可多个）
"""

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WORKSHOP = r"D:\Steam\steamapps\workshop\content\394360"
GAME_DIR = r"D:\Steam\steamapps\common\Hearts of Iron IV"      # 原版也有官方简中（MODIFIER_* 在这）
# 已启用的汉化：2194317383 = BlackICE 内核汉化；3556011214/3431515994 = 正式/测试内核汉化
DEFAULT_DIRS = ([os.path.join(WORKSHOP, i) for i in ("2194317383", "3556011214", "3431515994")]
                + [GAME_DIR])          # 原版放最后，MOD 汉化优先

# 修正名（数据文件里出现的 key）→ 中文名写在 MODIFIER_<大写> 里
MODIFIER_SOURCES = {
    "upgrades": ("modifiers",),
    "mio": ("traits", "initial_trait"),
    "policies": ("equipment_bonus", "organization_modifier"),
    "national_ideas": ("modifiers",),
}
MODIFIER_NESTED = {"traits": "bonuses", "initial_trait": "bonuses"}


def modifier_keys():
    """数据里出现过的修正名（用于查它们的中文名）。"""
    keys = set()
    for name, fields in MODIFIER_SOURCES.items():
        path = os.path.join(DATA, name + ".json")
        if not os.path.exists(path):
            continue
        for item in json.load(open(path, encoding="utf-8")):
            for field in fields:
                value = item.get(field)
                if field in MODIFIER_NESTED:
                    subs = value if isinstance(value, list) else ([value] if value else [])
                    for sub in subs:
                        if isinstance(sub, dict):
                            keys |= set((sub.get(MODIFIER_NESTED[field]) or {}).keys())
                elif isinstance(value, dict):
                    keys |= set(value.keys())
    return keys


def norm_dir(path):
    """Windows 盘符路径在 WSL/Linux 下转成 /mnt/<盘>/...（脚本两边都能跑）。"""
    if os.name != "nt":
        m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
        if m:
            return "/mnt/%s/%s" % (m.group(1).lower(), m.group(2).replace("\\", "/"))
    return path


def needed_keys():
    keys = set()
    for name, fields in (("airframes", ("key",)), ("airframes_all", ("key",)),
                         ("mio", ("organization",)), ("policies", ("token",)),
                         ("upgrades", ("key",)),                       # upgrades 的 requires 也要查
                         ("special_projects", ("project",))):          # 特殊工程名
        path = os.path.join(DATA, name + ".json")
        if not os.path.exists(path):
            continue
        for item in json.load(open(path, encoding="utf-8")):
            for f in fields:
                if item.get(f):
                    keys.add(item[f])
            for trait in item.get("traits", []) or []:
                if trait.get("token"):
                    keys.add(trait["token"])
                keys |= set(trait.get("requires_techs") or [])
            ini = item.get("initial_trait") or {}
            if isinstance(ini, dict) and ini.get("token"):
                keys.add(ini["token"])
            keys |= set(item.get("requires_techs") or [])          # 方针的科技门槛
            keys |= set((item.get("requires") or {}).get("techs") or [])   # 改装的门槛
    for mod_key in modifier_keys():                                # 修正名（含 MODIFIER_ 形式）
        keys.add(mod_key)
        keys.add("MODIFIER_" + mod_key.upper())
    # 国家名（机型里出现的 tag），用于界面把 tag 显示成中文
    for name in ("airframes", "airframes_all"):
        path = os.path.join(DATA, name + ".json")
        if os.path.exists(path):
            for item in json.load(open(path, encoding="utf-8")):
                if item.get("country"):
                    keys.add(item["country"])
    return keys


def scan(dirs, keys):
    found = {}
    for root in dirs:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if "localisation" not in dirpath.lower():
                continue
            for fn in filenames:
                if not fn.endswith(".yml") or "chinese" not in dirpath.lower():
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    text = open(path, encoding="utf-8-sig", errors="replace").read()
                except OSError:
                    continue
                for line in text.splitlines():
                    m = re.match(r'^\s*([A-Za-z_0-9.]+):\d*\s+"(.*)"\s*$', line)
                    if not m:
                        continue
                    key, value = m.group(1), m.group(2)
                    if key.endswith("_desc"):
                        continue
                    if key in keys and key not in found:
                        cleaned = value.replace("\\n", " ").strip()
                        if cleaned:          # 空的条目（MOD 里把 SOV: "" 留空）不算命中
                            found[key] = cleaned
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", nargs="*", default=None)
    args = ap.parse_args()
    dirs = [norm_dir(d) for d in (args.dir or DEFAULT_DIRS)]
    keys = needed_keys()
    found = scan(dirs, keys)
    # 二轮：汉化里有些名字写成 $变量$（例如设计局），把内层键也查出来
    inner = {v.strip("$") for v in found.values()
             if isinstance(v, str) and v.startswith("$") and v.endswith("$")}
    if inner:
        found.update(scan(dirs, inner))
    # 修正名：数据里的 key 若本身没条目，就用 MODIFIER_<大写> 那条
    for mod_key in modifier_keys():
        if mod_key not in found and ("MODIFIER_" + mod_key.upper()) in found:
            found[mod_key] = found["MODIFIER_" + mod_key.upper()]
    out = os.path.join(DATA, "loc_zh.json")
    if not found:
        raise SystemExit("一个键都没命中——汉化目录可能不对，已放弃写入，原 %s 保持不变" % out)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(found, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("需要的键 %d 个，命中 %d 个 → %s" % (len(keys), len(found), out))
    miss = sorted(keys - set(found))[:10]
    if miss:
        print("未命中示例：", ", ".join(miss))


if __name__ == "__main__":
    main()
