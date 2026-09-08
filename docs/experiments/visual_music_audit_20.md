# 20 首音乐建筑视觉审计

2026-09-03—04 · 最终复测：compiler 3.3.2 · 2026-09-05/06 数值复测：compiler 3.7.0、3.8.0、3.9.0 与 3.9.1（见下）

20 首输入全部完成最终 v3 生成与逐曲视觉复核。修复了楼板/吊顶堵梯、电梯井侵入梯段、多个楼梯核心互穿、曲线楼板自交、GLB 填洞伪面及 v2 失败阻断 v3 共六类问题。**20 个模型均保留待解决项，不能据此认定可使用、可施工或规范通过。**

**版本范围：** 本报告中的图片属于 2026-09-03 冻结视觉实验，只用于这次审计。`baseline-frozen`、`after-frozen` 和 `final-frozen` 是被否决的负面证据；`verified-frozen` 是该实验的最终快照，也不代表项目当前模型。项目当前证据只由 [`model_versions/latest.json`](../../artifacts/model_versions/latest.json) 指向，Rhino 与 Blender 的权限状态以该版本清单为准。

2026-09-05 数值复测（compiler 3.7.0）

在 2026-09-05 把同一 20 首录音按当时的工作树（compiler 3.7.0）重新编译，只做数值检查，没有重新渲染 140 个视图。每首走同一条音频 → score → v3 链，不经 Blender；逐曲记录在本机 [recheck_3_7_0.json](../../artifacts/visual_audit/2026-09-03/recheck_3_7_0.json)，与 3.4.0 的同格式记录 [recheck_3_4_0.json](../../artifacts/visual_audit/2026-09-03/recheck_3_4_0.json) 比较（两者由 Git 忽略，随本机审计目录保留）。这不是像对像比较：3.7.0 下 20 首的体量为 13 板式、5 基座＋条形、1 合院、1 亭式，与 3.3.2 的 11/8/0/1 不同，Night in Venice 从板式变为合院；因此只按问题类别汇总，不逐构件对对应。

测量期间工作树仍在被另一会话修改（compiler_v3、program、archetypes 等），每首在各自编译时刻的源码上测得：同一首 Android Sock Hop 在 22:38 与 22:55 两次编译分别报 15 与 0 根待复核构件。下面的数字是一个状态，不是一个版本；双方改动落地、版本号固定后需要重跑。

| 编号 | 3.7.0 复测结论 |
|---|---|
| G7 | **部分修复**。板边节点判定改为含边界后，四面都有柱与主梁（此前每栋楼有一侧没有）。133 个跨轴线的梯井按托换框架生成：主梁止于梯井两侧的托换梁，托换梁沿梯井落到开间主梁，每根构件按其收集的反力选型；9 首不再有任何梁穿越梯井。11 首仍有 291 根构件保留待复核，分四类：柱节点落入梯井（梯井在两个方向都跨轴线）；基座条形体的窄开间里一个梯井跨多条轴线；梯井贴板边、边梁只有一侧支承；退台残余开间的单根主梁。斜撑不再穿梯段。头顶净空改为按真实截面在穿越点测量：3.3.2 的 5,430 条未评估变为 0，11 首共 483 条实测违规，全部来自上述残余构件。 |
| G8 | **部分修复**。20 首都在停靠层生成轿厢（底板、背板、顶篷）与机房设备，井道门覆盖全部使用楼层（20/20，无缺门楼层）；停靠层门洞按轿厢地板判定可通行，其余楼层门洞报 PORTAL-LIFT-CAR-UNVERIFIED。未证明运行、门机与服务能力。 |
| G9 | **已修复**。平台与楼板齐平重叠 20 首合计 155.39 m² → 0 m²（20/20 为零）。入口平台、坡道顶平台与无障碍梯由一次决策拥有，楼板据此切除。 |
| G10 | **未解决，且有回退**。3.4.0 复测时 20 首没有未落位空间；3.7.0 工作树下 7 首剧场共 29 个后台空间未落位（排练、化妆、设备、卫生间、库房等），观众厅与舞台均已落位。当时 program.py 正被另一会话修改（通道净宽与墙体余量从开间容量扣除），归因需在其落地后重测；未缩小空间制造成功。 |

| 检查 | 3.4.0（20 模型） | 3.7.0（20 模型） |
|---|---:|---:|
| 平台与楼板齐平重叠 | 155.39 m²，20 首 | 0 m²，0 首 |
| 梯井托换框架 | 0 | 133 |
| 洞口处保留待复核的构件 | 290（16 首） | 291（11 首） |
| 楼梯头顶净空 | 0 违规 / 全部未评估 | 483 违规 / 0 未评估 |
| 空间规则整体：通过 / 未评估 / 失败 | 0 / 18 / 2 | 4 / 0 / 16 |
| 依赖图通过 | 17 | 18 |
| 使用楼层缺电梯门 | 0 | 0 |
| 轿厢与机房 | 无 | 20/20 |
| 未落位空间 | 0 | 29（7 首） |

逐曲：托换井为按框架生成的梯井数；待复核构件为编译器保留供复核的洞口构件数及其主要类别；其他违规列出头顶净空以外的空间规则发现。

| 曲目 / 风格 | 体量 | 类型 | 托换井 | 待复核构件 | 头顶净空违规 | 其他违规 | 空间规则 | 依赖图 | 未落位 |
|---|---|---|---:|---|---:|---|---|---|---|
| Android Sock Hop / Retro pop / synth rock | 板式 | 图书馆 | 18 | 0 | 0 | — | 通过 | 通过 | 0 |
| Blue Ska / Ska / brass dance | 板式 | 剧场 | 12 | 18（柱节点落入梯井） | 49 | 子系统重叠 6 | 失败 | 失败（MINIMUM-SUPPORTS, MEMBER-END-GEOMETRY） | 0 |
| BossaBossa / Brazilian bossa nova | 板式 | 剧场 | 7 | 23（柱节点落入梯井） | 54 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Cantina Blues / Blues / voice and saz | 基座＋条形上部 | 剧场 | 5 | 49（窄开间跨多条轴线） | 88 | 子系统重叠 6 | 失败 | 通过 | 4 |
| Carefree / Contemporary ukulele / light pop | 板式 | 图书馆 | 6 | 24（柱节点落入梯井） | 34 | 房间越出支承 1 | 失败 | 通过 | 0 |
| Cloud Dancer / EDM / synthwave | 板式 | 剧场 | 1 | 30（柱节点落入梯井） | 61 | — | 失败 | 通过 | 3 |
| L'Art de toucher le clavecin (recorded excerpt) / Baroque harpsichord | 基座＋条形上部 | 剧场 | 3 | 54（窄开间跨多条轴线） | 65 | 子系统重叠 6 | 失败 | 通过 | 4 |
| Dama-May / Asynchronous autoharp / experimental folk | 板式 | 图书馆 | 12 | 0 | 0 | — | 通过 | 通过 | 0 |
| 4 RNDD! / Tracker chiptune / computer music | 板式 | 图书馆 | 7 | 0 | 0 | 房间越出支承 1 | 失败 | 通过 | 0 |
| Dub Eastern / Reggae dub / electronic fusion | 基座＋条形上部 | 剧场 | 10 | 0 | 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Exotic Battle / Cinematic orchestral / African-influenced | 板式 | 剧场 | 0 | 24（柱节点落入梯井） | 32 | — | 失败 | 通过 | 0 |
| Funky Boxstep / Funk / off-kilter dance | 基座＋条形上部 | 剧场 | 8 | 0 | 0 | 子系统重叠 6 | 失败 | 失败（MINIMUM-SUPPORTS, MEMBER-END-GEOMETRY） | 0 |
| Night in Venice / Jazz / saxophone lounge | 合院 | 博物馆 | 6 | 4（退台残余开间单根主梁） | 16 | — | 失败 | 通过 | 0 |
| Raw / Raw low-bass rock | 基座＋条形上部 | 剧场 | 8 | 18（窄开间跨多条轴线） | 17 | 子系统重叠 6 | 失败 | 通过 | 4 |
| Ritual / Slow world flute / synth atmosphere | 板式 | 剧场 | 0 | 0 | 0 | — | 通过 | 通过 | 6 |
| SCP-x5x (Outer Thoughts) / Horror piano / dark score | 板式 | 剧场 | 7 | 35（柱节点落入梯井） | 58 | — | 失败 | 通过 | 4 |
| Still Pickin / Bluegrass / folk picking | 板式 | 图书馆 | 13 | 0 | 0 | — | 通过 | 通过 | 0 |
| Tafi Maradi / African percussion / call-and-response | 板式 | 图书馆 | 6 | 0 | 0 | 房间越出支承 1 | 失败 | 通过 | 0 |
| The Britons / Medieval / tavern soundtrack | 亭式 | 亭 | 0 | 0 | 0 | 面不齐平 1 | 失败 | 通过 | 0 |
| Valse Gymnopedie / Classical piano with a modern beat | 板式 | 剧场 | 4 | 12（梯井贴板边，边梁单侧支承） | 9 | — | 失败 | 通过 | 4 |

7 首剧场各有 6 条子系统重叠，3 首图书馆各有 1 条房间越出支承，The Britons 有 1 条面不齐平；这些没有在本次定位，前者落在另一会话正在做的座席与舞台工作范围内。Blue Ska 与 Funky Boxstep 的依赖图失败（最少支承数、构件端点几何）同样未定位。

这轮改动的单元证据见 `backend/tests/test_opening_transfers.py`（12 项：边界节点、托换规划四种情形、按真实截面量的头顶净空、入口平台切板），决策记录见 [0020](../decisions/0020-the-frame-meets-the-stair.md)。

2026-09-05 第二次数值复测（compiler 3.8.0：核心即网格单元）

同日按决策记录 0022 把核心改为结构网格的单元来布置——楼梯落在单元中心或双单元中线，电梯落在相邻单元中心，两个方向都跨轴线（柱落入梯井）的点位永远排最后，远离度配对只在框架能承担的点位里选；轴网按梯井尺寸加粗，开间窄于梯井时不再有任何无柱点位可选。另修正了折返坡道板宽（板宽等于折返间距，消除两段坡道间的落差缝）。20 首在这棵树上重编译，耗时约 74 分钟，仍只做数值检查，不重新渲染视图。逐曲记录在本机 [recheck_3_8_0.json](../../artifacts/visual_audit/2026-09-03/recheck_3_8_0.json)；只做单元布置、未加粗轴网的中间态保留为 recheck_3_8_0_cells_partial.json（11 首，被否决，其中 4 RNDD! 因 5.58 m 开间容不下 5.87 m 梯井回退到 24 根待复核构件）。

| 检查 | 3.7.0（20 模型） | 3.8.0（20 模型） |
|---|---:|---:|
| 洞口处保留待复核的构件 | 291（11 首） | 21（3 首） |
| 梯井托换框架 | 133 | 177 |
| 楼梯头顶净空违规 | 483（11 首） | 41（2 首） |
| 平台与楼板齐平重叠 | 0 m² | 0.0 m² |
| 空间规则整体通过 | 4 | 12 |
| 依赖图通过 | 18 | 18 |
| 未落位空间 | 29（7 首） | 28（8 首） |

| 曲目 / 风格 | 体量 | 类型 | 托换井 | 待复核构件 3.7.0 → 3.8.0 | 头顶净空违规 3.7.0 → 3.8.0 | 其他违规 | 空间规则 | 依赖图 | 未落位 |
|---|---|---|---:|---|---|---|---|---|---:|
| Android Sock Hop / Retro pop / synth rock | 板式 | 图书馆 | 12 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Blue Ska / Ska / brass dance | 板式 | 剧场 | 11 | 18 → 0 | 49 → 0 | 子系统重叠 6 | 失败 | 失败（REQUIRED-COVERAGE, ASSEMBLY-TO-STRUCTURE, MINIMUM-SUPPORTS, MEMBER-END-GEOMETRY） | 0 |
| BossaBossa / Brazilian bossa nova | 板式 | 剧场 | 11 | 23 → 0 | 54 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Cantina Blues / Blues / voice and saz | 基座＋条形上部 | 剧场 | 4 | 49 → 3 | 88 → 36 | 子系统重叠 6 | 失败 | 通过 | 4 |
| Carefree / Contemporary ukulele / light pop | 板式 | 图书馆 | 12 | 24 → 0 | 34 → 0 | — | 通过 | 通过 | 0 |
| Cloud Dancer / EDM / synthwave | 板式 | 剧场 | 12 | 30 → 0 | 61 → 0 | — | 通过 | 通过 | 3 |
| L'Art de toucher le clavecin (recorded excerpt) / Baroque harpsichord | 基座＋条形上部 | 剧场 | 4 | 54 → 5 | 65 → 0 | 子系统重叠 6 | 失败 | 通过 | 3 |
| Dama-May / Asynchronous autoharp / experimental folk | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 1 |
| 4 RNDD! / Tracker chiptune / computer music | 板式 | 图书馆 | 14 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Dub Eastern / Reggae dub / electronic fusion | 基座＋条形上部 | 剧场 | 10 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Exotic Battle / Cinematic orchestral / African-influenced | 板式 | 剧场 | 16 | 24 → 0 | 32 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Funky Boxstep / Funk / off-kilter dance | 基座＋条形上部 | 剧场 | 8 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 失败（REQUIRED-COVERAGE, ASSEMBLY-TO-STRUCTURE, MINIMUM-SUPPORTS, MEMBER-END-GEOMETRY） | 0 |
| Night in Venice / Jazz / saxophone lounge | 合院 | 博物馆 | 10 | 4 → 0 | 16 → 0 | — | 通过 | 通过 | 0 |
| Raw / Raw low-bass rock | 基座＋条形上部 | 剧场 | 5 | 18 → 13 | 17 → 5 | 子系统重叠 6 | 失败 | 通过 | 2 |
| Ritual / Slow world flute / synth atmosphere | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 6 |
| SCP-x5x (Outer Thoughts) / Horror piano / dark score | 板式 | 剧场 | 16 | 35 → 0 | 58 → 0 | — | 通过 | 通过 | 5 |
| Still Pickin / Bluegrass / folk picking | 板式 | 图书馆 | 12 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Tafi Maradi / African percussion / call-and-response | 板式 | 图书馆 | 12 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| The Britons / Medieval / tavern soundtrack | 亭式 | 亭 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Valse Gymnopedie / Classical piano with a modern beat | 板式 | 剧场 | 8 | 12 → 0 | 9 → 0 | — | 通过 | 通过 | 4 |

仍保留待复核的构件：Cantina Blues 3 根（STR-BMY-X04-Y02-L04, STR-BMY-X04-Y02-L05, STR-BMY-X04-Y02-L06…）；L'Art de toucher le clavecin (recorded excerpt) 5 根（STR-BMX-X04-Y03-L03, STR-BMX-X04-Y03-L04, STR-BMX-X04-Y03-L05, STR-BMX-X04-Y03-L…）；Raw 13 根（STR-BMX-X04-Y02-L03, STR-BMX-X03-Y03-L03, STR-HDR-X04-Y02-L03-O1S, STR-BMX-X04-Y…）。这些都在基座条形体的窄开间上：梯井跨越多条轴线或贴着板边，托换缺少第二支承，按 0020 的边界记录而不切梁。

8 首剧场仍各有 6 条子系统重叠，属另一会话正在做的座席与舞台工作范围；未落位空间与 3.7.0 同源（program.py 的通道净宽与墙体余量扣减开间容量），未归因于本次改动。这次测量在版本号固定后的静止树上完成；数字仍不构成可用、可施工或规范通过的结论。

2026-09-05 第三次数值复测（compiler 3.9.0：轴网跟随体积，核心为结构）

同日按用户确定的优先级——massing 给出的体积高于结构网格——重写核心与结构的关系（决策记录 0022）：楼梯核心只按楼板平面落位，轴网随后画到核心的四个面（每个面成为轴线，板边、切除房间边与给定轴线保留为固定线，其余跨距按模数填充，核心内不加线）；核心四面是从筏板基础通到屋面的钢筋混凝土核心墙，核心内不排任何柱梁，遇核心面的梁与次梁落在墙上，落地面墙体带真实门洞（两侧门框与过梁，另发出 door 构件供门洞与疏散报告读取），核心墙按承重墙做重力筛查并把自重与所承楼面荷载记入构件；托换框架、跨线分级、可行性缓存、单元候选整套删除。房间按板的模数行布局（`Lattice.band_lines`），不随核心面线切分；电梯井不落在核心门前通道；屋面桁架止于核心墙。入口平台、坡道与无障碍梯先于核心按板面定下，其范围核心不得占用（一首拱端图书馆的核心曾把半层平台压在坡道上）；坡道顶平台归入基座层并计为房间支承；核心门在依赖图中挂在自身核心墙门框上；原型采光门槛的外围判定改按开间模数而非结构线（结构线现含核心面，其间的窄条曾把判定缩到 450 mm）。第二核心的选址改为先满足出口远离度（所服务面积对角线的三分之一），再在满足者中选窄条最少的，都不满足才取最远——窄条惩罚排在前面时，基座＋条形上部的一对核心只相距 15 m 而要求 25 m，裙楼远端角落因为紧挨坡道保留区的窄条被筛掉；主楼梯在其偏好点中选能让每层都有两条出路的；落位点另采样与板边齐平的位置（齐平的核心面就是轴网自己的线）；核心门在门外有 2 m 余地时背向配对楼梯开（远离度按门到门量），否则朝内。20 首在这棵树上重编译，耗时约 56 分钟，仍只做数值检查。逐曲记录在本机 [recheck_3_9_0.json](../../artifacts/visual_audit/2026-09-03/recheck_3_9_0.json)。

| 检查 | 3.8.0（20 模型） | 3.9.0（20 模型） |
|---|---:|---:|
| 洞口处保留待复核的构件 | 21（3 首） | 0（0 首） |
| 梯井托换框架 | 177 | 已删除（核心为墙） |
| 楼梯头顶净空违规 | 41（2 首） | 0（0 首） |
| 平台与楼板齐平重叠 | 0 m² | 0.0 m² |
| 空间规则整体通过 | 12 | 13 |
| 依赖图通过 | 18 | 20 |
| 未落位空间 | 28（8 首） | 32（11 首） |

| 曲目 / 风格 | 体量 | 类型 | 托换井 | 待复核构件 3.8.0 → 3.9.0 | 头顶净空违规 3.8.0 → 3.9.0 | 其他违规 | 空间规则 | 依赖图 | 未落位 |
|---|---|---|---:|---|---|---|---|---|---:|
| Android Sock Hop / Retro pop / synth rock | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | 非法环 1 | 失败 | 通过 | 0 |
| Blue Ska / Ska / brass dance | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 1 |
| BossaBossa / Brazilian bossa nova | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Cantina Blues / Blues / voice and saz | 基座＋条形上部 | 剧场 | 0 | 3 → 0 | 36 → 0 | 子系统重叠 6 | 失败 | 通过 | 4 |
| Carefree / Contemporary ukulele / light pop | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Cloud Dancer / EDM / synthwave | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 1 |
| L'Art de toucher le clavecin (recorded excerpt) / Baroque harpsichord | 基座＋条形上部 | 剧场 | 0 | 5 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 2 |
| Dama-May / Asynchronous autoharp / experimental folk | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 3 |
| 4 RNDD! / Tracker chiptune / computer music | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Dub Eastern / Reggae dub / electronic fusion | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 |
| Exotic Battle / Cinematic orchestral / African-influenced | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 1 |
| Funky Boxstep / Funk / off-kilter dance | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 1 |
| Night in Venice / Jazz / saxophone lounge | 合院 | 博物馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Raw / Raw low-bass rock | 基座＋条形上部 | 剧场 | 0 | 13 → 0 | 5 → 0 | 子系统重叠 6 | 失败 | 通过 | 6 |
| Ritual / Slow world flute / synth atmosphere | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 5 |
| SCP-x5x (Outer Thoughts) / Horror piano / dark score | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 4 |
| Still Pickin / Bluegrass / folk picking | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Tafi Maradi / African percussion / call-and-response | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| The Britons / Medieval / tavern soundtrack | 亭式 | 亭 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 |
| Valse Gymnopedie / Classical piano with a modern beat | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 4 |

20 首没有任何构件保留待复核：没有梁穿过梯井或井道，核心内没有柱梁。

6 首剧场仍各有 6 条子系统重叠，属另一会话正在做的座席与舞台工作范围。其他空间违规：INVALID-PLAN-RING Android Sock Hop 1。未落位空间 28（8 首）→ 32（11 首）：Cloud Dancer 3→1，L'Art de toucher le clavecin (recorded excerpt) 3→2，Ritual 6→5，SCP-x5x (Outer Thoughts) 5→4，Blue Ska 0→1，Dama-May 1→3，Exotic Battle 0→1，Funky Boxstep 0→1，Raw 2→6——核心墙占去了走道规划曾使用的楼面，第二核心按远离度优先落到板边、门在有余地时背向配对楼梯，剧场后台失去的走道跑道多于得到的，这一进一出归因于本次改动（门朝向的 A/B 另测）；未落位的根源仍是 program.py 的通道净宽与墙体余量扣减开间容量。这次测量在版本号固定后的静止树上完成；数字仍不构成可用、可施工或规范通过的结论。

2026-09-06 第四次数值复测（compiler 3.9.1：分区切片暴露的分配器缺陷）

决策记录 0023（模型判、内核算）的第一片：massing 的 zones 进分配器，模型按 --brief 导出的行段写分区，内核在分区内排房间、按名报告放不下的。手写分区时暴露并修掉三个分配器缺陷：房间只能取每个模数行的一个条带，楼梯门前走道桩把整行沿全长切成 4.4/1.5/3.3 m 的碎条，5 m 进深的房间在整层都站不住（现按连续条带链叠加）；行段计算把 0.1 mm 的缝当作缺失楼面而封掉整段（现半毫米以内视为舍入）；房间不知道入口平台与坡道顶平台（现在入口层预留）。20 首在 3.9.1 树上重编译，耗时约 59 分钟。逐曲记录在本机 [recheck_3_9_1.json](../../artifacts/visual_audit/2026-09-03/recheck_3_9_1.json)。

| 检查 | 3.9.0（20 模型） | 3.9.1（20 模型） |
|---|---:|---:|
| 洞口处保留待复核的构件 | 0（0 首） | 0（0 首） |
| 梯井托换框架 | 已删除 | 已删除 |
| 楼梯头顶净空违规 | 0（0 首） | 0（0 首） |
| 平台与楼板齐平重叠 | 0 m² | 0.0 m² |
| 空间规则整体通过 | 13 | 13 |
| 依赖图通过 | 20 | 20 |
| 未落位空间 | 32（11 首） | 20（7 首） |

| 曲目 / 风格 | 体量 | 类型 | 托换井 | 待复核构件 3.9.0 → 3.9.1 | 头顶净空违规 3.9.0 → 3.9.1 | 其他违规 | 空间规则 | 依赖图 | 未落位 3.9.0 → 3.9.1 |
|---|---|---|---:|---|---|---|---|---|---:|
| Android Sock Hop / Retro pop / synth rock | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Blue Ska / Ska / brass dance | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 1 → 0 |
| BossaBossa / Brazilian bossa nova | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 → 0 |
| Cantina Blues / Blues / voice and saz | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 4 → 3 |
| Carefree / Contemporary ukulele / light pop | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Cloud Dancer / EDM / synthwave | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 1 → 0 |
| L'Art de toucher le clavecin (recorded excerpt) / Baroque harpsichord | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 2 → 3 |
| Dama-May / Asynchronous autoharp / experimental folk | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 3 → 2 |
| 4 RNDD! / Tracker chiptune / computer music | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Dub Eastern / Reggae dub / electronic fusion | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 0 → 0 |
| Exotic Battle / Cinematic orchestral / African-influenced | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 1 → 0 |
| Funky Boxstep / Funk / off-kilter dance | 基座＋条形上部 | 剧场 | 0 | 0 → 0 | 0 → 0 | 子系统重叠 6 | 失败 | 通过 | 1 → 0 |
| Night in Venice / Jazz / saxophone lounge | 合院 | 博物馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Raw / Raw low-bass rock | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 6 → 2 |
| Ritual / Slow world flute / synth atmosphere | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 5 → 3 |
| SCP-x5x (Outer Thoughts) / Horror piano / dark score | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 4 → 4 |
| Still Pickin / Bluegrass / folk picking | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Tafi Maradi / African percussion / call-and-response | 板式 | 图书馆 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| The Britons / Medieval / tavern soundtrack | 亭式 | 亭 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 0 → 0 |
| Valse Gymnopedie / Classical piano with a modern beat | 板式 | 剧场 | 0 | 0 → 0 | 0 → 0 | — | 通过 | 通过 | 4 → 3 |

20 首没有任何构件保留待复核：没有梁穿过梯井或井道，核心内没有柱梁。

7 首剧场仍各有 6 条子系统重叠，属另一会话正在做的座席与舞台工作范围。未落位空间 32（11 首）→ 20（7 首）：Blue Ska 1→0，Cantina Blues 4→3，Cloud Dancer 1→0，Dama-May 3→2，Exotic Battle 1→0，Funky Boxstep 1→0，Raw 6→2，Ritual 5→3，Valse Gymnopedie 4→3，L'Art de toucher le clavecin (recorded excerpt) 2→3——归因于条带叠加的修正（房间可以跨走道切线叠满整行）与入口平台预留。这次测量在版本号固定后的静止树上完成；数字仍不构成可用、可施工或规范通过的结论。

初轮 20 次尝试中，19 个生成模型，Drozerix 在 v2 导出阶段中断；最终 20 个均生成 v3。正式几何前后比较采用这 19 个共同样本，Drozerix 单列为失败恢复案例。中间两轮虽然导出成功，仍被实际网格和视觉检查否决。

输入与方法

- 18 首 Kevin MacLeod 的 CC BY 4.0 录音，2 首来源页声明 CC0 的录音；保留作者、逐曲来源、许可和音频 SHA256。[曲库及来源](../../artifacts/visual_audit/2026-09-03/corpus_table.md) · [完整署名与许可说明](visual_music_corpus_20_license.md) · [机器清单](visual_music_corpus_20.json)。18 首署名授权录音使用时仍需署名。
- 每次输入使用整个下载文件。Couperin 来源本身是约 32.8 秒的公开录音节选；其余为来源发布的完整录音文件。未把节选称为完整作品。许可依据是链接来源的明确声明，未采用权利来源含糊的候选。
- 调用真实 `pipeline.compile_generation(..., render=True)`，经过音频、score、设计选择、编译、既有 Blender 无界面导出链。使用冻结源代码归档隔离同时进行的绘图工作；没有针对这 20 首调整音乐阈值或增加风格。
- 每个最终模型实际查看五个整体/结构视角，以及主楼梯 L02 俯视和剖切，共 **140 个视图**。原始渲染 100 张，实际 GLB 近景 40 张。橙色为楼梯，紫色为井道，灰色为楼板与结构。
- 视觉判断后以独立几何检查定位，再用实际 GLB 水平三角面和源多边形的并集比较复核导出。每个模型的楼板、吊顶各一次，**40/40 表面积一致检查通过**。范围不包括所有立面、节点或梁实体。

问题表

P1：影响交通、空间有效性或证据可靠性；P2：表面表达与几何归属问题。

| 编号 | 优先级 | 问题 | 根因与已做修改 | 复测结论 / 余项 |
|---|---|---|---|---|
| G1 | P1 | 楼梯穿过楼板与吊顶 | 楼梯生成与楼板开洞各自计算，楼板没有避让梯段。 楼梯、楼板、吊顶与空间预留共用 core layout；精确扣除洞口。 | **已修复并复测**。结构梁的避让仍属 G7。 |
| G2 | P1 | 电梯井侵入梯段 | 井道与楼梯共享锚点，井道尺寸跟随楼梯宽度。 独立搜索楼梯四侧的井道位置；采用明确的井道尺寸并验证避让。 | **已修复并复测**。门、设备和服务覆盖属 G8。 |
| G3 | P1 | 多个楼梯核心互穿 | 候选点没有排除其他核心的完整占地。 用包含平台的完整核心占地做互斥；实际梯段另行检查。 | **已修复并复测**。不从零碰撞推导疏散合格。 |
| G4 | P1 | 半圆端部楼板自交 | 西侧弧线的遍历方向与外边界不连续，形成跨越闭合边。 在 datum 源头纠正弧线顺序；非法多边形继续报错。 | **已修复并复测**。未用自动修补掩盖源几何错误。 |
| G5 | P1 | 源数据有洞，GLB 出现填洞伪面 | 环方向约定不一致；统一方向后，多个孔洞的最近顶点桥接仍会生成伪面。 把扣洞后的材料区域分解为无孔简单多边形；验证并集与原区域一致，再独立比较导出网格表面。 | **已修复并复测**。3.3.0 与 3.3.1 保留为失败证据；网格检查仅针对楼板和吊顶表面。 |
| G6 | P1 | v2 预览失败阻断 v3 审查 | Drozerix 的 v2 预览对象数为 550，超过现有 500 上限，异常提前终止共同流程。 保留 v2 错误和 blocked 状态，让独立的 v3 流程继续；前端处理缺失的 v2 资产。 | **已隔离并复测**。未抬高上限，未把缺失资产或 Rhino 接受状态写成通过。 |
| G7 | P1 | 梁占用楼梯与井道空间 | 结构梁仍按原轴网生成，尚未消费交通核心的三维净空需求。 新增几何净空检查和显式限制，保留构件供复核。 | **仍未解决**。需要洞口边梁、转换与节点方案，以及相应荷载重算；当前未切掉梁来隐藏冲突。 **3.7.0：**部分修复，133 个梯井托换，291 根构件仍待复核。**3.8.0：**核心改为网格单元、轴网按梯井加粗后，21 根待复核（3 首），头顶净空违规 41（2 首），见下节。**3.9.0：**轴网画到核心面、核心为混凝土墙后，0 根待复核（0 首），头顶净空违规 0（0 首）。 |
| G8 | P1 | 井体未证明可用电梯及完整顶层空间 | 现有模型只有井体，缺门、设备与顶部余量设计；布局的 served 列表与实发井段覆盖口径不同。 审计额外逐层列出实发井段；不以布局宣称或楼梯覆盖替代电梯覆盖。 | **仍未解决**。Raw 的井体止于 L06 楼面，缺该层以上井段；编译器文字仍未反映这一差异。全部模型缺电梯门、设备和可用服务验证。 **3.7.0：**部分修复，20/20 有轿厢、机房与全部使用层井道门。 |
| G9 | P2 | 平台与楼板共面条纹 | 齐平平台与楼板局部重叠，彩色检查材质下出现共面深度竞争。 保留齐平和接触检查，没有用高差遮掩条纹。 | **仍未解决**。后续需统一面归属与连接细节，避免重复表面和重复计量。 **3.7.0：**已修复，20/20 重叠为 0。 |
| G10 | P1 | 局部几何改善仍未满足完整使用要求 | 部分空间无法落位，疏散数量、容量、无障碍或构造检查仍有失败或未评估项。 保留未放置空间、未服务楼层、独立疏散报告与 unknown 状态。 | **仍未解决**。没有把模型可显示或楼梯接层升级为可使用、可施工或规范通过。 **3.7.0：**未解决，7 首剧场 29 个后台空间未落位，见下节。 |

实际导出反例

Valse 的 3.3.1 源数据已经没有本审计记录的楼板碰撞，导出的楼板却仍封住梯洞。这个反例促成第二次修正：先把扣洞后的材料区域分解为无孔简单多边形，再交给既有导出器。保留全部材料区域，检查并集相等与零面积重叠。

![Valse 的实际 GLB：修正前后](../../artifacts/visual_audit/2026-09-03/stair_opening_comparison.jpg)

左：3.3.1 的导出伪面。右：3.3.2 的洞口已保留，灰梁仍需要协调。共面橙色条纹也保留为 G9。图片是实际模型截图。

逐曲结果

下表“初轮”列为视觉记录及源几何定位编号；最终各行均已查看七个视图。G7? 表示该组视图只支持待核查，未直接确认梁侵入。所有行另有 G8（门、设备和可用服务未验证）、G10（其余使用与规范检查未闭合）；额外列出明确未落位的空间和 Raw 顶层井段。

| 曲目 / 风格 | 生成体量 | 初轮问题 | 最终仍见 / 额外未解决项 | 查看 |
|---|---|---|---|---|
| L'Art de toucher le clavecin (recorded excerpt) / Baroque harpsichord | 基座＋条形上部 | G1, G2, G3 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/couperin-harpsichord.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/couperin-harpsichord.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/couperin-harpsichord/geometry_measurements.json) |
| Carefree / Contemporary ukulele / light pop | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/carefree.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/carefree.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/carefree/geometry_measurements.json) |
| 4 RNDD! / Tracker chiptune / computer music | 板式 | P1 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/drozerix-rndd.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/drozerix-rndd.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/drozerix-rndd/geometry_measurements.json) |
| Tafi Maradi / African percussion / call-and-response | 板式 | G1, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/tafi-maradi.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/tafi-maradi.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/tafi-maradi/geometry_measurements.json) |
| Cantina Blues / Blues / voice and saz | 基座＋条形上部 | G1, G2, G3 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/cantina-blues.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/cantina-blues.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/cantina-blues/geometry_measurements.json) |
| Valse Gymnopedie / Classical piano with a modern beat | 基座＋条形上部 | G1, G2 | G7, G9；未落位：观众厅、舞台 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/valse-gymnopedie.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/valse-gymnopedie.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/valse-gymnopedie/geometry_measurements.json) |
| Funky Boxstep / Funk / off-kilter dance | 基座＋条形上部 | G1, G2, G3 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/funky-boxstep.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/funky-boxstep.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/funky-boxstep/geometry_measurements.json) |
| Cloud Dancer / EDM / synthwave | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/cloud-dancer.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/cloud-dancer.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/cloud-dancer/geometry_measurements.json) |
| Night in Venice / Jazz / saxophone lounge | 板式 | G1, G2, G4 | G7?, G9；未落位：两间展厅 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/night-in-venice.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/night-in-venice.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/night-in-venice/geometry_measurements.json) |
| BossaBossa / Brazilian bossa nova | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/bossa-bossa.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/bossa-bossa.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/bossa-bossa/geometry_measurements.json) |
| Dub Eastern / Reggae dub / electronic fusion | 基座＋条形上部 | G1, G2, G3 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/dub-eastern.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/dub-eastern.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/dub-eastern/geometry_measurements.json) |
| Raw / Raw low-bass rock | 基座＋条形上部 | G1, G2 | G7, G9；井体止于 L06 楼面，缺上方井段 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/raw.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/raw.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/raw/geometry_measurements.json) |
| Blue Ska / Ska / brass dance | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/blue-ska.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/blue-ska.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/blue-ska/geometry_measurements.json) |
| The Britons / Medieval / tavern soundtrack | 亭式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/the-britons.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/the-britons.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/the-britons/geometry_measurements.json) |
| Still Pickin / Bluegrass / folk picking | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/still-pickin.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/still-pickin.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/still-pickin/geometry_measurements.json) |
| Exotic Battle / Cinematic orchestral / African-influenced | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/exotic-battle.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/exotic-battle.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/exotic-battle/geometry_measurements.json) |
| Dama-May / Asynchronous autoharp / experimental folk | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/dama-may.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/dama-may.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/dama-may/geometry_measurements.json) |
| SCP-x5x (Outer Thoughts) / Horror piano / dark score | 基座＋条形上部 | G1, G2, G3 | G7, G9；未落位：观众厅、舞台 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/scp-outer-thoughts.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/scp-outer-thoughts.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/scp-outer-thoughts/geometry_measurements.json) |
| Android Sock Hop / Retro pop / synth rock | 板式 | G1, G2, G4 | G7, G9 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/android-sock-hop.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/android-sock-hop.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/android-sock-hop/geometry_measurements.json) |
| Ritual / Slow world flute / synth atmosphere | 基座＋条形上部 | G1, G2 | G7, G9；未落位：观众厅、舞台 | [整体](../../artifacts/visual_audit/2026-09-03/verified-frozen/review_cards/ritual.jpg) · [剖切](../../artifacts/visual_audit/2026-09-03/verified-frozen/detail_cards/ritual.jpg) · [数据](../../artifacts/visual_audit/2026-09-03/verified-frozen/tracks/ritual/geometry_measurements.json) |

可核对的测量结果

这些是检查记录数，包含不同构件对和多边形；不能当作独立的视觉缺陷数量。非法源几何、无可计算顶部障碍等仍列为未评估。楼板分片改变了构件对数量，因此不计算跨轮“碰撞下降百分比”。

| 检查 | 初轮发现 / 未评估（19 模型） | 最终发现 / 未评估（20 模型） |
|---|---:|---:|
| 边界自交或非法拓扑 | 162 / 0 | 0 / 0 |
| 楼梯顶部净空（限定几何） | 1527 / 4185 | 0 / 5430 |
| 踏步与楼板实体相交 | 212 / 348 | 0 / 0 |
| 踏步与井壁实体相交 | 1268 / 0 | 0 / 0 |
| 不同楼梯核心的踏步相交 | 170 / 0 | 0 / 0 |
| 程序分区正面积重叠 | 0 / 0 | 0 / 0 |
| 平台接层与楼板接触 | 0 / 174 | 0 / 0 |

最终完成 248,614 条有限范围的几何求值，记录的发现为 0，同时有 **5,430 条顶部净空检查未评估**。独立运行时空间报告另外保留 2,449 条顶部净空审查警告与 22 条子系统重叠警告；梁采用中心线包络近似，警告不升级为精确实体判决。视觉看到的 G7 因而没有被“零发现”掩盖。报告详情存在数量上限，汇总使用未截断计数。

250 个平台接触记录完成求值，无接层/接触失败；全部占用层均有内部楼梯平台记录。这只证明被测平台的几何关系，无法证明所有房间都能抵达、疏散容量充足或梯段净空合格。Raw 的最后一段井体从 L05 延伸至 L06 楼面，没有 L06 以上的井段；编译器的文字仍按布局服务列表判断，尚未反映这个几何口径差异。

4 首仍有共 8 个程序空间无法放置：Night in Venice 的两间展厅，以及 Valse、SCP-x5x、Ritual 各自的观众厅和舞台。没有缩小它们来制造分配成功。

整体视图未确认整层楼板悬浮。构造连接、局部隐藏构件、全部房间内部和承载能力未由这些视角穷尽验证；不能用该观察推导“没有悬浮部件”。

覆盖范围也有限：这 20 首产生 11 个板式、8 个基座＋条形上部、1 个亭式；用途为 6 图书馆、12 剧场、1 博物馆、1 亭；最终全部采用钢框架，立面语法为 11 International Style、2 Organic、7 Critical Regionalism。测试揭示了当前可执行域的集中性，不能宣称覆盖全部体量、结构或风格。七种体量的楼梯接层另由合成测试覆盖。

架构优化与验证

1. 统一交通核心决策。完整楼梯占地包含平台；楼梯、洞口、空间预留和井道消费同一布局，体量切除先于布局。无合法位置时记录无法服务的楼层。
2. 把平面材料区域处理放在便携模块 `plan_regions.py`，修复 datum 源头错误；从源几何到网格保留独立验证。Blender 导入器没有被改写来偷偷修补设计。
3. 将运行时几何审查和独立审计脚本分开；缺输入、非法拓扑和近似几何保留 unknown。平台接触合并同层齐平楼板分片，重叠仅计一次。
4. 隔离 v2 预览异常。Drozerix 仍明确记录 550 个预览对象超过现有 500 上限，v3 完成；缺失 v2 资产保持空值和 blocked。未提高对象上限，未升级 Rhino 接受状态。

后续首要工作是让结构生成器消费交通三维净空，形成洞口边梁、转换和节点方案并重算荷载；其次闭合井道顶部空间、门与设备，再处理平台与楼板的面归属。简单删除相撞梁会破坏受力路径，因此当前保留冲突及审查记录。

验证记录见 [测试日志](../../artifacts/visual_audit/2026-09-03/targeted_test_results.txt)：3.3.2 的交通/边界测试 19 项通过；几何审查、v2 隔离与 integration 16 项通过；GLB parity 与几何审查 21 项通过，其中有重复用例，不能相加为独立测试总数。接触测量与几何审查共 12 项通过，覆盖相邻分片、非法分片和竖向错位。七种体量接层测试在分片修正前通过，分片后重跑了保持区域并集的定向测试。未声称运行完整后端测试套件。

v3 demo 和浏览器冻结 demo 均已按 3.3.2 重新生成；18 个独立资源引用存在，两个模型的资产及 manifest 共 4 个哈希匹配。保留 demo 原有失败和未评估状态，未删除其他模型资产。

证据与复现

- [验证清单](../../artifacts/visual_audit/2026-09-03/verification.json)：20 个保留音频哈希、140 个原始模型/渲染文件哈希均匹配；另有 40 张 GLB 近景。实际人工视觉记录在 [visual_review.json](../../artifacts/visual_audit/2026-09-03/verified-frozen/visual_review.json)；生成时 result 中的 pending 是导出瞬间的状态快照。
- [初轮测量](../../artifacts/visual_audit/2026-09-03/baseline-frozen/measurement_summary.json) · [最终测量](../../artifacts/visual_audit/2026-09-03/verified-frozen/measurement_summary.json) · [实际 GLB parity](../../artifacts/visual_audit/2026-09-03/verified-frozen/glb_parity_report.json) · [逐曲 CSV](../../artifacts/visual_audit/2026-09-03/case_results.csv) · [问题目录 JSON](../../artifacts/visual_audit/2026-09-03/issue_catalog.json)。
- [源代码差异边界](../../artifacts/visual_audit/2026-09-03/source_comparison.json) 记录正式前后版本。源代码快照、`after-frozen`（3.3.0）和 `final-frozen`（3.3.1）保留在本机审计目录；两轮中间结果均被否决。公开仓库保留最终对照卡与测量 JSON。
- 共同完成的 19 首中，18 首的完整音频特征与 score 序列化哈希完全相同；Valse 的路径迁移改变文件名元数据，数值和源音频仍相同。Drozerix 初轮无响应，不能参与该特征对比。
- 音频、完整 GLB 与逐视图渲染保留在本机 `artifacts/visual_audit/2026-09-03/` 并由 Git 忽略；公开仓库保留对照卡、测量 JSON、汇总和哈希。审计 native Blender 临时文件未作为交付保留。
- Blender 无界面文件工作流仅提供下游展示证据；本次未通过 GUI MCP 操作，也未改变 Rhino 接受的设计权威。

运行新批次时，使用新输出目录；对已有冻结目录只做读入或独立测量。完整再生会调用既有 Blender 导出器：

```powershell
.venv/Scripts/python.exe backend/scripts/run_visual_music_audit.py --manifest docs/experiments/visual_music_corpus_20.json --output artifacts/visual_audit/new-run
.venv/Scripts/python.exe backend/scripts/summarize_visual_music_audit.py artifacts/visual_audit/new-run --compare-dir artifacts/visual_audit/2026-09-03/baseline-frozen
```

该证据对应 V2 系统协调、V3 故障隔离与可复现流程、V4 对实际结果的独立评估；未完成的建筑问题没有被证据统计转写为通过。

临时清理：浏览器审查会话与临时 HTTP 服务已关闭。任务临时目录仍保留在本机并由 Git 忽略；这些副本与辅助初测目录不属于正式 20 首结果。公开证据均使用上方链接。
