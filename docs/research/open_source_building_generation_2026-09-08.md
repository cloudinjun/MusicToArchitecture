# 首次建筑建模的开源复用调研

调研日期：2026-09-08 UTC。范围：GitHub 仓库、官方文档、发布记录、部分源码和本项目当前文件。未安装候选、未运行外部生成器，兼容性和改善效果尚未实测。本文是技术选型输入，不修改项目决策或 evidence matrix 状态。

结论：优先研究 Homemaker 的空间边界到构件规则，验证 IfcOpenShell 的构件与洞口 API；继续利用已有 Shapely、Manifold 和 RhinoCommon。CadQuery、FreeCAD、COMPAS 暂作有条件的候选，避免同时维护多个几何内核和设计模型。

## 筛选依据

GitHub 没有统一的“好评率”。下表的 stars 是本次打开仓库页时的近似显示值，表示关注度；结合发布、测试、文档、适用对象和依赖判断复用价值。星数不能证明建筑正确性，也不能跨 CAD、游戏和研究工具直接比较。

| 项目 | 关注度与维护证据 | 可复用内容 | 本项目建议与限制 |
| --- | --- | --- | --- |
| [IfcOpenShell / Bonsai](https://github.com/IfcOpenShell/IfcOpenShell) | 约 2.8k stars；Python/C++ API、测试及多个配套工具；本次 API 文档版本 0.8.5 | 墙、板、门窗、截面表达、洞口与宿主关系、IFC 数据模型 | 优先局部验证。IfcOpenShell 库与 Bonsai 编辑器应分别考虑；无须先迁移至 Blender 编辑。它不会自动决定空间布局或支承方案。核心 LGPL-3.0-or-later，Bonsai GPL-3.0-or-later，其他模块按仓库清单核对。 |
| [FreeCAD BIM](https://github.com/FreeCAD/FreeCAD) | 约 33.4k；[最新发布页](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.3)显示 1.1.3 | 参数化建筑对象、构件依赖、BIM/IFC、模型与图纸工作流 | 成熟桌面参照与独立复核候选。它需要 FreeCAD 运行环境；当前已使用 Rhino，不宜再引入第二个主设计宿主。仓库 LGPL-2.1。 |
| [Building Tools](https://github.com/ranjian0/building_tools) | 约 1.5k；[发布线](https://github.com/ranjian0/building_tools/releases)为 v1.0.13；README 明示 Blender 4.0 兼容 | 楼层、屋顶、门窗、楼梯、栏杆等分模块生成 | 适合查看局部几何配方及反例。源于游戏建模，不能承接本项目的结构/通行规则；Blender 5.x 兼容未验证。MIT。 |
| [Infinigen Indoors](https://github.com/princeton-vl/infinigen) | 整仓约 7.3k；有测试、论文与单独的 indoors-stable 路线 | 室内程序化资产、约束驱动布置、场景生成阶段 | 重点借鉴家具/设备布置与约束求解。整仓星数包括自然场景等能力，不能当作建筑生成评价。服务合成场景，不提供公共建筑结构或规范保证。BSD-3-Clause，外部资产单独核对。 |
| [Homemaker add-on](https://github.com/brunopostle/homemaker-addon) | 161；有测试；[2026-05-15 预发布](https://github.com/brunopostle/homemaker-addon/releases)更新 Blender 5.1 所需 Topologic 依赖 | 空间 CellComplex → 边界条件 → 构件规则 → IFC | 与 Program Volume 最贴近，值得优先做小范围对照。README 的基本条件是墙竖直、楼板水平；交通/楼梯仍列有未完成项，不能整套替换。GPL-3.0-or-later；附带部分资产/样式另有 CC0。 |
| [TopologicPy](https://github.com/wassimj/topologicpy) | 256；测试、空间图 API；当前主分支说明 PythonOCC 后端 | 共享面、邻接、包含、空间图及拓扑查询 | 可作独立边界核对器。它不负责完整建筑构件生成。当前 README 声明 LGPL，[LICENSE](https://github.com/wassimj/topologicpy/blob/main/LICENSE)需随选定版本固定；旧索引仍有 AGPL 描述，不能跨版本沿用许可证结论。 |
| [CadQuery](https://github.com/CadQuery/cadquery) | 约 5.7k；[2.8.0 发布](https://github.com/CadQuery/cadquery/releases/tag/v2.8.0) | OCCT 实体、拉伸/放样、布尔、装配、STEP 输出 | 只在无 Rhino 后台实体建模有明确收益时采用。不会解决屋面位置、构件支承或建筑语义；复杂实体操作仍可能失败。Apache-2.0。 |

### 补充候选

[COMPAS](https://github.com/compas-dev/compas) 提供几何数据结构与 Rhino/GH/Blender 集成，MIT；可评估其跨软件数据适配，但当前没有足够证据证明替换本项目适配器能减少首次建模失败。

[Manifold](https://github.com/elalish/manifold) 提供实体三角网格布尔与拓扑能力，Apache-2.0。本项目已经使用它，见下文。它不负责支承设计，也不将网格自动变成 Rhino 原生参数对象。

[House-GAN++](https://github.com/ennauata/houseganpp) 约 251 stars，是 CVPR 2021 的住宅布局研究代码，使用 RPLAN。它可研究邻接图到布局，但对剧院、图书馆、博物馆还需数据、类型和规则迁移；本轮不作为首次建模稳定性的优先依赖。未验证权重或数据使用条件，不建议直接嵌入。

## 最贴近当前缺陷的源码机制

### Homemaker：先判定边界条件，再生成构件

[topologist/face.py](https://github.com/brunopostle/homemaker-addon/blob/main/topologist/face.py) 实现 CellsOrdered、IsInternal、IsExternal、CellAbove、CellBelow，以及 TopLevelConditions/BottomLevelConditions。它查询面的两侧空间及连接面来判别几何关系；代码仍含 TODO/FIXME，应以反例验证。

[用户参考](https://homemaker-addon.readthedocs.io/en/latest/reference.html)把带标高的边界路径称为 traces，把面壳称为 hulls；区分外墙、内墙、平屋面、斜屋面和底面等条件，并组合 Shell、Extrusion、Repeat、Grillage 构件生成器。样式配置可以继承，减少重复定义。

对 MTA 的推断：Program Volume 已有空间体量，下一步可利用共享面关系识别每个局部裸露顶面和交接边，而不只从整栋最高边界理解屋面。这样可帮助识别退台需要的局部封闭和支承输入。拓扑分类本身不计算连接承载力，也不能宣称已解决远距离立面连接件。

候选接入点：program_volumes.py / program_volume_contracts.py 的空间关系输出，roof.py 与 envelope.py 的局部边界消费。必须保留 lattice 注册、构件 ID、音乐映射、现有规则及报告来源。

### IfcOpenShell：复用标准构件和真实洞口关系

官方 API 已提供 [add_wall_representation](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/geometry/add_wall_representation/index.html)、[add_window_representation](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/geometry/add_window_representation/index.html)，以及把洞口附着到墙/板的 [feature.add_feature](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/feature/add_feature/index.html)。这些是可调用能力，尚未在本项目验证。

可先选择一个墙—洞口—窗框组合，对照我们发出的实体，测量净开口、宿主扣除和几何回读是否一致。保持原有防火、声学、净宽和材料判定。通过标准构件 API 创建模型不会自动证明这些要求成立。

[IfcClash](https://docs.ifcopenshell.org/ifcclash.html) 可作为 IFC 几何碰撞复核候选，但需要先有正确的 IFC 实体映射，并区分设计连接与非法碰撞。不能把转换成本和误报处理省略。

## 已经复用的基础设施

- `backend/requirements.txt` 已声明 Shapely；`plan_regions.py` 和 `mesh_primitives.py` 使用其多边形与带洞三角化能力。
- `backend/requirements-fabrication.txt` 已声明 trimesh、manifold3d；`fabrication.py` 已用 `trimesh.boolean.union(..., engine='manifold', check_volume=True)`。这是打印导出路径，不等于所有运行时构件已接受同样检查。
- `rhino/import_building_model_v3.py` 已调用 RhinoCommon 原生 Brep，检查对象有效性。已有 Rhino 内核应优先复用；引入 CadQuery 必须说明它解决了哪个现有宿主无法低成本解决的任务。
- `geometry.inset` 对凹多边形已使用 Shapely buffer，凸形仍保留历史径向移动以维持兼容。统一偏移可以评估，但会改变依赖旧站点的构件，不能当作无影响的替换。

## 建议先验证的三个小案例

以下均为待执行实验，不是已经取得的结果。

| 实验 | 使用候选 | 必须测量的结果 | 无法替代的项目职责 |
| --- | --- | --- | --- |
| 高低两个体量相接，带退台 | Homemaker/Topologic 共享面机制 | 裸露顶面、内外墙、底面分类与预期逐一对应；没有重复墙面或遗漏局部顶面 | 屋面构造、排水、支承方案与承载依据 |
| 带洞墙体及窗框 | IfcOpenShell 构件/洞口 API | 净开口、宿主减量、截面与往返读写尺寸一致；不出现封口假面 | 开口位置、声学/防火/通行要求 |
| 非凸楼板、内洞、邻接构件 | 现有 Shapely/Manifold/Rhino 路径 | 几何有效性、洞口保留、体积、连通体数量；拒绝掩盖缺件的自动修补 | 楼梯服务、空间使用、结构连接语义 |

若候选通过，应通过边界清晰的适配器替代对应重复代码，记录固定版本、依赖、输入输出单位和失败语义。先验证一个局部，再扩大到固定建筑和既有跨音乐样本。保持 v2/v3 并行边界、Rhino 接受权和 Blender 展示权。

## 调研限制

未测运行成功率、速度或 Windows/Blender/Rhino 实际兼容；所有“优先”均为基于公开机制与本项目缺陷的判断。许可证列为仓库声明，实际复用时按选定版本和所用子模块核对。没有据此提升任何模型质量或合规状态。

GitHub API 四个元数据读取在同一批次被浏览工具拒绝，随后停止该路径，改读仓库 HTML。stars 均为页面近似数，不声称实时 API 统计；部分发布页省略年份，未据此编造日期。检索错误已另存项目审计记录。
