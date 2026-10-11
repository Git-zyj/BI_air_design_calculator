# BI Air Design Calculator

给 **BIX（BlackICE 子模组）** 用的飞机选型计算器：输入年份、国家、用途、军工组织与已解锁的前置，
输出「该造哪一型飞机、怎么改装、为什么」。

**对应模组**：BlackICE Historical Immersion Mod（黑冰）**正式版**（workshop id 1137372539）
**v12.1.0**（游戏本体 1.19.2.0，仅参考）。数据是这个组合的固定快照——
黑冰更新后需重跑 `extract_game_data.py` / `extract_loc_zh.py` 并重新打包，
打出来的 exe 名字里会带**模组版本**（如 `飞机设计计算器_黑冰正式版v12.1.0.exe`）。

> **本分支 = `main`，适配正式版。** 黑冰**测试版**（`Blackice HOI IV TEST`，
> workshop id 1851181613 / v12.3.0）在 **`beta` 分支**，配套 Release 是
> [v12.3.0-test](https://github.com/Git-zyj/BI_air_design_calculator/releases/tag/v12.3.0-test)（Pre-release）。
> **两个版本的数据不通用，别混用 exe。**

## 快速开始

```
双击 gui.bat            （Windows，推荐）
python gui.py           （同上，命令行）
bash gui.sh             （WSL；需要 bisov 环境，见 PLAN.md §11）
```

界面上方是输入（① 用途 ② 年份 + 国家/对手 ③ 前置科技 ④ 军工组织 ⑤ 国家精神 ⑥ 总体累计），
下方 ⑦ 是结果表 + 帕累托散点图。**「计算」**只出结果，**「导出 Excel」**才写文件
（默认写到 `output/BI_SOV_选型输出.xlsx`）。
② 里还能看到/改**对手（AI）的修正**：对手 = 该机型原始数值 ×（1 + 设计商修正）×（1 + 满经验）。
设计商修正**不是手输的**：工具按模组 `common/military_industrial_organization/ai_bonus_weights`
（AI 挑 MIO 用的属性权重）自动判定"该国 AI 会用哪家 MIO、点哪些特质"——德国 1944 战斗机
算出来就是阿拉多（机动 +4% / 速度 +1.5%），与游戏内实测面板一致。和游戏里对不上时，
可以直接改那四个数字（改完即生效），点「恢复 AI 自动值」回到自动判定。

⑥ 里还有**我方联队经验加成**（机动/速度/对空/防御/对地/对海/瞄准）：它是和军工组织、
国家精神并列的另一层，按经验单独乘进最终数值。默认是满经验那套；
想只手算"设计值"（和经验无关）就把七个框清零。

## 目录结构

```
gui.py / gui.sh / gui.bat      图形界面与启动器
engine.py                      评分口径（空战比值、事故折损、改装求值、MIO 穷举）
run.py                         读输入 → 计算 → 写工作簿
extract_game_data.py           从游戏/模组文件抽取数据（机身、改装、MIO、方针、特殊工程、科技年份…）
extract_loc_zh.py              抽取汉化名（机型/MIO/特质/改装/科技/修正名）
data/*.json                    抽取结果（重跑抽取脚本即可同步游戏版本）
BI_SOV.xlsx                    最初的手工试算表（只作 golden 参照，已被新口径覆盖）
output/                        导出的工作簿
PLAN.md                        完整设计文档与变更记录（**优先看这个**）
```

## 数据来源与复现

数据全部从游戏与模组文件抽取，不手写：

```
python extract_game_data.py --game-dir "<BIX 模组目录>"    # BIX/子模组目录
python extract_loc_zh.py                                   # 汉化（含原版简中）
```

抽取结果带 `data/manifest.json`（sha256 指纹），游戏版本更新后重跑即可。
数值口径、公式推导、踩过的坑都记在 `PLAN.md`。

## 验收

```
python run.py --anchor     # 对空 + 距离 900：Yak-9U@1944 = 17.2672706（= 旧值 15540.543552 ÷ 目标航程 900）
```

## 依赖

- Python 3.8+，`openpyxl`（导出 Excel 用）
- 图形界面用 Tkinter；Windows 原生即可，字体不受限

## 构建与发布（exe）

给别人用不需要装 Python：打一个单文件 exe（数据已内置）。

```
build_exe.bat        → dist\飞机设计计算器_黑冰正式版v12.1.0.exe        （发行版，无控制台）
build_exe_debug.bat  → dist\飞机设计计算器_黑冰正式版v12.1.0_调试版.exe  （带控制台，会打印 [DEBUG] 日志）
```

- 版本号在 `.bat` 里的 `set EXE_NAME=...`，写的是**黑冰模组版本**；
  模组更新 → 改这一行 + 重跑抽取脚本，重新打包，文件名自然区分；
- 先出**调试版**排错（有 traceback 可见），确认没问题再出**发行版**；
- `build/` `dist/` `*.spec` `output/` **不进版本库**（都是可复现的中间产物）；
- **发行版 exe 作为 GitHub Release 附件发布**，不提交进 git
  （二进制一进库，之后每个版本都会跟着膨胀，而且已经没有"看历史 diff"的意义）；
- 发布时附上 `开始使用前先看.txt`，release notes 直接摘 `CHANGELOG.md` 顶部几条；
- ⚠️ **附件名只能用 ASCII**：GitHub 会把附件名里的中文清洗成 `_`
  （`飞机设计计算器_黑冰正式版v12.1.0.exe` → `_.v12.1.0.exe`）。
  所以约定：上传 `BI_air_design_calculator_v<版本>.zip`（里面是中文原名的 exe + 说明 txt）
  + 一个 ASCII 名的 `BI_air_design_calculator_v<版本>.exe`；详见 `PLAN.md` §21.2。

## 说明

这是一个**工具模组**，本身不包含游戏内容；`descriptor.mod` 里把 BIX 标为依赖只是为了记录它服务于哪个模组。

## 版权与第三方

- **代码**：**MIT**（见 [`LICENSE`](LICENSE)）——随便用、随便改、可商用，保留版权声明即可。
- **数据**：`data/*.json`、`BI_SOV.xlsx` 是从**第三方模组**抽取的数值快照，版权不属于本仓库：
  - **BlackICE Historical Immersion Mod**（黑冰正式版 workshop id `1137372539`；
    测试版 `Blackice HOI IV TEST` `1851181613`）——数值与定义归 BlackICE 作者团队；
  - 汉化名称（`data/loc_zh.json`）来自黑冰内核汉化与 HOI4 官方简中，归各自作者。
  本仓库只是把这些数值**聚合起来做计算与对照**，不主张对它们的所有权；
  原作者如对收录有异议，可移除对应数据。
- **依赖**：`openpyxl`（MIT）；打包用的 **PyInstaller 是 GPL-2.0 + 特别例外**，
  该例外明确允许用它打包并分发自己的程序（含闭源、商用），所以与上面的 MIT 不冲突。
- 本工具与 Paradox Interactive、BlackICE 作者团队**没有隶属关系**；
  《钢铁雄心 4》及其素材版权归 Paradox Interactive。
