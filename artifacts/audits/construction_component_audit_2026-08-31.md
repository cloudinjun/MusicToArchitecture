# 14 个生成模型的施工部件审计

日期：2026-08-31  
审计对象：`artifacts/audio_saturation/corpus-2026-08-31-semantic-rerun/tracks/` 中 14 份 `building_model_v3.json` 及对应 translation report  
规范基线：2025 California Building Code（2026-01-01 生效）、ICC means of egress、2010 ADA Standards，以及 AISC、ACI、APA/AWC 的现行基础标准。洛杉矶地方修订、具体地址、风险类别、场地类别、岩土报告和主管部门解释尚未解析。

## 结论

**0/14 可以被标记为 construction-ready、code-compliant、safe 或 permit-ready。** 这 14 个结果适合表达 program、结构秩序、立面语法和音乐映射关系，当前仍是 schematic / professional-review-required 模型。

| 项目 | 审计结果 |
|---|---|
| 几何生成 | 14/14 完成，并保留 semantic layer、element ID 和 provenance |
| Program 面积装箱 | 11/14 完成；`hurle-cancer`、`nienvox-visions`、`walcker-crew-blind-istanbul` 有未放置空间 |
| 标准产品规格可追溯 | 0/14 完成；截面 ID 未绑定 ASTM/AISC、ACI 钢筋明细或 PRG 320 产品标识 |
| 无障碍入口 | 0/14 通过；14 个 `ramp` 都是 9.0 × 3.0 × 0.28 m 的水平 box，`rotation_z=0`、中心标高 `-0.40 m`，没有坡度、平台、扶手和边缘防护 |
| 疏散系统 | 0/14 通过；模型无 door 元素、无完整出口路径计算，主要楼梯系统没有证明第二个远离出口 |
| 护栏/扶手 | 0/14 通过；护栏高 1050 mm，低于 1067 mm 常规 guard 基线；也高于 865–965 mm handrail 区间，且栏杆开口大于 100 mm 控制球需求 |
| 卫生间/给排水 | 0/14 完整；program 和 element taxonomy 中没有 toilet/restroom/plumbing fixture |
| 防火与生命安全 | 0/14 完整；无喷淋、竖井门、防火分隔、穿透封堵、构件耐火保护和疏散容量模型 |
| 结构计算 | 14/14 仅有不同程度的重力初算；风、地震、组合受力、节点、构造、耐火、振动和完整侧向体系未闭合 |
| 基础 | 0/14 可验收；独立基础为固定候选尺寸，未由柱反力与地基承载力共同确定 |
| 立面施工系统 | 0/14 可采购；多数 glazing/panel/spandrel 使用零厚度 `QuadGeometry`，没有玻璃构成、锚固、排水、热断桥和周边防火封堵 |

`program_fits=true` 只证明面积分配器把房间装入楼板。`facade_gates=passed` 只证明立面语法规则通过。两者均不具有施工规范通过的权力。

## 优先级发现

### P1 — 会阻断建筑许可或施工深化

1. **无障碍坡道几何失真。** 14/14 的 ramp 是水平板。2010 ADA 规定坡道运行坡度不陡于 1:12、单跑升高不超过 760 mm、净宽至少 915 mm，并需平台、两侧扶手及边缘防护。当前对象只保留了一个名为 ramp 的 box，无法构成 accessible route。
2. **护栏和扶手混成一个 1050 mm 高度。** CBC/IBC 常规 guard 高度为 1067 mm；楼梯和坡道 handrail 顶高为 865–965 mm。当前 `rail_height_m=1.05` 同时承担两种角色，两个规范区间都没有被正确表达。立柱间距 1.21–1.79 m，加上仅有 top/mid rail，会形成明显超过 100 mm 的开口。
3. **疏散路径没有形成可验证图。** 14 个模型没有 door 元素，楼梯、出口门、出口通道、室外出口和公共道路之间无法连通。剧院、图书馆和博物馆的 occupant load、出口数量、出口分离距离、共同路径及旅行距离均未计算。
4. **基本卫生与消防部件缺失。** 所有 program list 都没有卫生间；所有 element kinds 都没有 plumbing、sprinkler 或 fire-protection 元素。电梯竖井由连续 box 表达，没有层门和防火节点。
5. **结构体系没有完成洛杉矶所需的侧向设计链。** 当前限制明确记录 gravity only。风、地震、P-Delta、扭转、不规则性、楼板 diaphragm、collector、chord、侧向构件和基础锚固仍缺失。
6. **基础尺寸与地基条件脱节。** `compiler_v3.py` 发出约 1.4/1.6 × 1.4/1.6 × 0.9 m 的候选独立基础，理由同时声明 soils unresolved。没有土承载力、沉降、滑移、倾覆、冲切、配筋和柱脚锚栓验算。

### P2 — 几何可能合理，规格和验算证据不足

7. **钢结构截面不具备标准产品身份。** 梁采用 `I-350x175x7x11`、`I-400x200x8x13`，更接近自定义焊接 I 形截面；柱采用 `SHS-300x300x8` 至 `SHS-400x400x8`，材料为 `steel_s355`。它们没有映射到 AISC Shapes Database、ASTM 材料牌号、设计壁厚、圆角或厂家产品。几何尺寸可制造，标准库存与北美材料合规仍未证明。
8. **方钢管局部屈曲可能控制。** 以上 SHS 的粗略平板宽厚比分别约为 36.5、42.8、49；AISC 对 50 ksi 方/矩形 HSS 压杆给出的非加劲壁宽厚比分界约为 33.7。当前钢柱计算走 AISC E3 轴压路径，没有按 E7 使用有效面积，也没有组合弯矩和二阶效应，现有 utilisation 可能偏低。
9. **混凝土构件只有近似重力初算。** 500–550 mm 柱、600×350 至 850×550 mm 梁、300 mm 楼板从施工尺度看具有可形成性；模型使用固定 1.2% 梁配筋率、2.0% 柱配筋率，缺少钢筋根数/直径、箍筋、锚固、搭接、节点核心区、抗震约束、裂缝、长期挠度、施工缝和墙边界构件。drop panel 的 reason 明确声明没有 ACI punching shear check。
10. **混凝土计算报告混入木结构假设。** `sizing.py` 对所有非钢构件追加 “NDS adjustment factors other than C_D taken as unity”，因此 RC member check 也可能携带 NDS 文本。这是 provenance/报告逻辑错误，降低审计可信度。
11. **CLT/glulam 缺少可采购规格。** 390 mm CLT 与 GL-760/836 梁、GL-912/988/1216 柱可以作为定制构件概念；模型没有 PRG 320 layup、等级、层数、厂家/工厂标识、认证标记、强度、火灾炭化、湿度、振动、连接件和运输分段。390 mm CLT 还与 300 mm concrete `floor_slab` 重叠，模型未声明 hybrid assembly 或复合连接设计。
12. **侧向墙是无开口实体。** RC shear wall 和 timber core wall 都使用 320 mm 厚整块 box；没有门洞、电梯开口、耦联梁、边界构件、hold-down、拼板或 fastener schedule。当前对象只能表达位置与体量。
13. **屋架、悬挑和次构件按 convention 定尺。** 屋架 chord/web、purlin、canopy strut、mullion、screen、fascia 等没有 load path、挠度、稳定、节点、雨水/维护荷载和构件间净空验算。悬挑为 1.83–2.82 m，缺少悬挑专项验算。
14. **立面“passed”标签容易被误读。** facade gate 检查 opening ratio、material count、fragment size 和 score authority。它不检查空气/水密性、结构风压、玻璃安全、层间位移、热工、结露、排水、耐火或可施工节点。建议所有展示层明确标成 `design_grammar_passed`。

### P3 — 尺寸本身可作为下一阶段起点

- 主网格 5.93–7.59 m × 6.53–8.19 m，落在公共建筑常见的概念设计跨度区间。
- 层高 4.08–5.19 m，适合图书馆、剧院和博物馆的初步空间研究。
- 楼梯 riser 固定 175 mm，低于 CBC 11B 的 178 mm 上限；仍需 tread、nosing、headroom、landing、occupant load 和 handrail 全套检查。
- mullion module 1.20–1.50 m、spandrel 0.45–0.70 m 具有常见幕墙分格尺度，但面板厚度、玻璃规格和锚固未定义。
- RC 构件采用 50 mm 左右的尺寸增量，利于模板协调；这只说明尺寸整齐，不能替代配筋和结构验算。

## 分体系审计

| 体系 | 数量 | 可保留 | 施工阻断项 | 结论 |
|---|---:|---|---|---|
| Steel frame | 8 | 网格、构件拓扑、梁柱初选、重力 utilisation | AISC/ASTM 产品映射、HSS slender-element、组合受力、稳定、连接、侧向体系、耐火 | **Unverified / needs redesign checks** |
| RC frame/wall | 3 | 柱梁板体量、RC 尺寸增量、初步重力需求 | ACI 318 完整设计、冲切、配筋与抗震构造、墙洞/耦联梁、节点与施工缝 | **Unverified / schematic only** |
| Mass timber CLT/glulam | 3 | panel/post/beam 语义分层、初步跨度与构件深度 | PRG 320 产品身份、NDS 设计、连接、火灾/湿度/振动、运输安装、重复 concrete slab 冲突 | **Unverified / assembly conflict** |

## 14 个结果的审计索引

| Track | Typology | Structure | Program area fit | Construction status |
|---|---|---|---:|---|
| affen-like-life-easily-ended | library | RC frame/wall | yes | blocked |
| charrier-accorte | theater | steel frame | yes | blocked |
| couperin-harpsichord | theater | steel frame | yes | blocked |
| deadbone-wake-up-call | theater | steel frame | yes | blocked |
| dub-riots-silience-is-gold | theater | steel frame | yes | blocked |
| hurle-cancer | library | RC frame/wall | no | blocked + program incomplete |
| jorgensen-guitar-soundscape-1 | library | steel frame | yes | blocked |
| kevin-bryce-rainfields | library | mass timber | yes | blocked |
| krakenti-his-akorns | theater | steel frame | yes | blocked |
| lucas-darklord-hymne-iii | library | RC frame/wall | yes | blocked |
| m-pex-bueid | museum | mass timber | yes | blocked |
| mozart-symphony-29 | theater | steel frame | yes | blocked |
| nienvox-visions | library | steel frame | no | blocked + program incomplete |
| walcker-crew-blind-istanbul | library | mass timber | no | blocked + program incomplete |

这里的 `blocked` 表示缺少许可级输入或存在明确生命安全冲突；它不等价于模型文件损坏。

## Claim–evidence matrix

| Claim | 当前证据 | 可允许的表述 | 禁止表述 |
|---|---|---|---|
| program fits | 面积分配器及 unplaced list | 面积 brief 是否装入结构网格 | code-compliant program |
| member sized | 重力需求、候选截面、部分 utilisation | gravity preliminary sizing | structurally safe / final section |
| facade gates passed | 4 个语法 gate | selected facade grammar satisfied | facade engineered / weather-tight |
| professional_review_required | 每个 element 的 validation status | honest schematic limitation | permit ready |
| jurisdiction_resolved=false | selection manifest | jurisdiction pending | CBC/LA approved |

## 施工可验证所需 Reality Gates

依赖顺序如下：

1. **Jurisdiction gate**：真实地址、2025 CBC + LA amendments、occupancy、construction type、sprinkler assumption、allowable area/height、risk category、wind、seismic、snow/rain和场地类别。
2. **Life-safety graph**：房间 occupant load → door → corridor → stair/exit enclosure → discharge → public way；同步生成卫生间、无障碍路径、门净宽、回转空间和出口分离。
3. **Product/section registry**：钢材映射 ASTM/AISC，RC 映射混凝土/钢筋/cover 和 bar schedule，木结构映射 PRG 320/AWC 产品及连接件；每个 section ID 带 edition、manufacturer 或 generic-standard provenance。
4. **Material-specific floor assemblies**：steel deck、RC slab、CLT/acoustic topping 分开计算和建模；只有明确 hybrid system 时允许重叠，并附连接及组合设计依据。
5. **Structural analysis gate**：完整 load combinations、风震、侧向体系、diaphragm/collector、P-Delta、构件组合受力、挠度/振动、连接和基础反力。仅受该计算控制的构件可标 `sized_by_calculation`。
6. **Envelope gate**：有厚度的 glazing/panel assembly、风压、层间位移、锚固、空气/水密、排水、热断桥、结露、安全玻璃、周边防火封堵和维护策略。
7. **Constructability gate**：装配顺序、吊装重量、运输长度、施工缝、容差、碰撞、检修、临时支撑、shop drawing 信息和采购规格。
8. **Professional acceptance**：结构、建筑、幕墙、消防、无障碍和岩土专业人员签审；Rhino accepted geometry 与计算模型/图纸版本 hash 一致。

## 规范与标准来源

- [California Building Standards Commission — 2025 code effective January 1, 2026](https://www.dgs.ca.gov/BSC/Codes)
- [2025 California Building Code, Chapter 19A — Concrete](https://codes.iccsafe.org/content/CABC2025P2/chapter-19a-concrete)
- [2025 California Building Code, Chapter 11B — Accessibility](https://codes.iccsafe.org/content/CABC2025P1/chapter-11b-accessibility-to-public-buildings-public-accommodations-commercial-buildings-and-public-housing)
- [2024 IBC, Chapter 10 — Means of Egress](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-10-means-of-egress)
- [2010 ADA Standards for Accessible Design](https://www.ada.gov/law-and-regs/design-standards/2010-stds/)
- [AISC Shapes Database v16.0](https://www.aisc.org/aisc/publications/steel-construction-manual/aisc-shapes-database-v160/)
- [AISC Steel Construction Manual, 16th Edition](https://www.aisc.org/aisc/publications/steel-construction-manual/)
- [AISC HSS connection and slender-wall guidance](https://www.aisc.org/aisc/solutions-center/engineering-faqs/5-connections/)
- [ANSI/APA PRG 320-2025 — Performance-Rated CLT](https://www.apawood.org/guides-tools-training/technical-document-library/standards/ansiapa-prg-320-2025-standard-for-performance-rated-cross-laminated-timber/)
- [AWC 2024 NDS](https://shop.awc.org/product/2024-nds/)

## Residual risk

本审计直接检查生成 JSON、数据契约、计算路径和官方基线，未执行有限元分析、幕墙计算、消防模拟、岩土设计或盖章图审。地方修订和项目输入补齐后，部分判定可能变严；不会自动变成通过。报告适合作为下一轮 pipeline 约束清单及 V4 评估证据。
