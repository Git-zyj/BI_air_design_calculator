import sys, time
sys.path.insert(0, ".")
import gui, engine, run
gui.App._pop_to_front = lambda self: None
app = gui.App(); app.withdraw()
def pump(s=1.5):
    t0=time.time()
    while time.time()-t0 < s: app.update(); time.sleep(0.02)
pump(1.5)
app.var_tag.set("苏联"); app._refresh_country()
for k, v in app.role_vars.items(): v.set(k == "air_far")
app._on_role_click("air_far")
app.var_tech.set(1946); app._on_tech_year_changed()
app.var_year.set(1944); app._build_tech_checks()
app.var_distance.set("1200"); app.var_band.set("300")
app.var_org.set(next(l for l, k in app._org_keys.items() if k == "SOV_yakovlev_design_bureau_organization"))
app._on_org_change(); pump(2.0)
app.on_calculate(); pump(1.5)
inputs = app.collect()
print("③ 解锁科技 %d 项；MIO=%s；近边=%s" % (len(inputs["unlocked_techs"]), inputs["mio"]["organization"],
      float(app.var_distance.get()) - float(app.var_band.get())))
data = app.data; up = engine.upgrades_by_key(data["upgrades"])
mig = [r for r in app.rows if r["role"]=="air_far" and "Mikoyan-Gurevich 9" in r["airframe"]["name"]]
if mig:
    r = mig[0]
    print("MiG-9 行：分数 %.3f 覆盖率 %.4f 航程 %.1f 配方 %s" % (r["score"], r["values"]["range_factor"], r["values"]["range"], r["design"]))
    a = r["airframe"]
    av = engine.available_upgrades(a["category"], data, techs=inputs["unlocked_techs"], flags=inputs["unlocked_flags"], archetype=a.get("archetype"))[0]
    pos = [(t, up[t]["modifiers"].get("air_range"), up[t]["max_level"]) for t in av if (up[t]["modifiers"].get("air_range") or 0) > 0]
    print("MiG-9 可用的正向航程改装：", pos)
    # 拉满所有正向航程改装 + 当前 MIO 路线加成
    base = r["values"]["range"] / max(1e-9, 1 + sum(v for _k, _v, _n in []))  # 占位
    mfr_mods, _info = run.resolve_manufacturer(inputs, data, up, app._ref_plane() and [app._ref_plane()])
    coef = sum(v * n for _t, v, n in pos) + float(mfr_mods.get("air_range", 0.0))
    print("   拉满 = 基础 %.0f × (1 + 改装 %.4f + MIO 航程 %.4f) = %.1f" % (
        a["range"], sum(v*n for _t, v, n in pos), float(mfr_mods.get("air_range", 0.0)), a["range"]*(1+coef)))
    print("   MIO 路线是否含航程特质：", [t["token"] for t in (app._org().get("traits") or []) if "air_range" in (t.get("bonuses") or {})][:6])
for nm in ("Lavochkin 9", "Yakovlev 9P"):
    rr = [r for r in app.rows if r["role"]=="air_far" and nm in r["airframe"]["name"]]
    if rr:
        print("%-14s 分数 %7.3f 覆盖率 %.3f 航程 %.0f" % (nm, rr[0]["score"], rr[0]["values"]["range_factor"], rr[0]["values"]["range"]))
app.destroy()
