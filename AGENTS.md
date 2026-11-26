# Agent Instructions

- 不需要 TDD 开发，避免过度防御与过度设计。

## 检查两个上游

用户说「检查上游更新」「同步上游」时，分别检查这两个源码上游并报告结果。

| 来源 | 仓库和分支 | 合入方式 |
| --- | --- | --- |
| 主上游 `upstream` | [ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)，`master` | 沿用 EchoDesk 现有的源码合入方式，以主分支实际合入的官方提交和文件为基准。 |
| 次上游 `coco` | [wk321425/coco-ww](https://github.com/wk321425/coco-ww)，`main` | 按用户选定的功能逐项移植，保留来源提交链接。coco 基于 ok-ww v3.8.0 的源码快照，Git 历史独立。 |

`origin` 是 EchoDesk 自己的发布远端。`scripts/Update-EchoDesk.ps1` 从 `origin/master` 获取已经整合的 EchoDesk 版本。`wk321425/coco-ww-char-code` 是队伍代码工坊数据源。

先直接查询两条远端分支。这样新检出也能检查，且本地远端跟踪引用的刷新时间不会影响结果。

```powershell
git ls-remote --exit-code https://github.com/ok-oldking/ok-wuthering-waves.git refs/heads/master
git ls-remote --exit-code https://github.com/wk321425/coco-ww.git refs/heads/main
```

- 官方上游按主分支的合入记录和文件差异确认待同步内容。需要完整历史或差异时，可在可写的临时 Git 仓库取对应分支。
- coco 优先查看上次审阅提交到新分支头的增量，同时保留此前待选功能。对照当前 EchoDesk 代码识别重复实现、共用模块冲突和依赖。检查时只汇报，用户选定功能后逐项合入，并记录实际移植的来源提交。
- 两边都有选定更新时，可以在同一轮维护中处理。先合入官方更新，再按当前接口移植选定的 coco 功能，最后运行集成验证。
- 角色默认代码按角色选择，仅在当前阵容没有匹配的队伍代码时使用。匹配队伍后沿用它自己的代码和切换方式。

### 检查基线

- 2026-11-26，官方 `cf60eb919190e7d149629583f04eb2758e8ce7ed`（v3.8.15）已通过主分支提交 `f5675d0` 合入源码。
- 2026-11-26，coco `cd8c76e0a7ce8e16497f9808a1b067cb43e52ee4`（v1.0.10）作为以下移植功能的审阅基线。后续从这个提交检查 coco 的增量。[源码快照](https://github.com/wk321425/coco-ww/tree/cd8c76e0a7ce8e16497f9808a1b067cb43e52ee4)

### EchoDesk 中的 coco 功能

- 「角色默认代码」可以逐个角色选择 EchoDesk 原生版或 coco 加固版。先按完整阵容匹配本地队伍代码，再找角色默认版本。独立角色实现和源提交、日期放在 `src/coco/characters/`。原生版日期优先从当前 Git 历史读取，加固版日期对应移植的源文件提交。[原生角色加固](https://github.com/wk321425/coco-ww/commit/0025424)
- 「角色代码」中的同队存档放在 `configs/custom_team_variants/`。工坊可在后台按当前阵容批量拉取，用户切换存档时才应用代码。[同队多版本](https://github.com/wk321425/coco-ww/commit/a50d6ff) · [角色排列](https://github.com/wk321425/coco-ww/commit/ef403ca)
- 「自动战斗」任务卡内的按 F 开战默认关闭。刷四费声骸支持在简中游戏客户端按 Boss 名称选择，其他语言使用列表位置。[F 键与拾取判定](https://github.com/wk321425/coco-ww/commit/a117082) · [Boss 名称识别](https://github.com/wk321425/coco-ww/commit/080cdfd) · [进本补点](https://github.com/wk321425/coco-ww/commit/d0f448f) · [残血判断](https://github.com/wk321425/coco-ww/commit/9eecc82)
- 「跑轴记录」任务默认关闭。录制与回放文件保存在 `logs/axis_runs/`。首页快捷按钮使用现有任务入口，战斗面板读取本地录制数据。[快捷主页与面板](https://github.com/wk321425/coco-ww/commit/cb5e5c3) · [回放](https://github.com/wk321425/coco-ww/commit/5db642a)
- 输入方式可选 `SendInput`。暂停和前台失焦时清理战斗过程中由 EchoDesk 发出的长按。队伍代码可使用 `src.combat.MacroKit`，导出 ZIP 时内嵌实现。`tools/char_fuzz.py` 可在离线模拟中检查卡死与松键。[前台输入](https://github.com/wk321425/coco-ww/commit/e2399d9) · [暂停处理](https://github.com/wk321425/coco-ww/commit/1bc4c6b) · [MacroKit](https://github.com/wk321425/coco-ww/commit/db0569d)
- 同步时优先在 `src/coco/` 更新移植功能，核对 `config.py` 与现有任务的接入点。工坊继续使用现有 HTTPS 请求。后台窗口激活修正和异常截图已由 EchoDesk 当前使用的 ok-script 提供。
- 用户已跳过预置队伍功能（第 6 项）。队伍轴继续从工坊获取。[工坊索引](https://github.com/wk321425/coco-ww-char-code/blob/190a832/teams.json)
