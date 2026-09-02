# FLORIS 工程师技术手册

> **读者定位**：风电场工程技术人员
> **覆盖范围**：FLORIS 的技术原理、工作流程、模型与算法、输入输出、以及在复杂地形、不确定性等高级工程场景下的能力边界
> **参考代码库**：NREL FLORIS（floris >= 4.x）

> **与本仓库的关系**：本文是上游 FLORIS 能力手册，不等同于本仓库的公开接口。
> 当前 CLI 和布局优化 API 使用均匀来流或 WRG；粗糙度/WAsP 驱动的异质入流链路已经
> 删除。`POST /v1/hourly-aep` 仍在内部用 `heterogeneous_inflow_config` 表达逐机组
> 风速差异。仓库行为以 [`wind-layout-opt.md`](wind-layout-opt.md) 和
> [`api.md`](api.md) 为准。

---

## 1. 概述

本章从"FLORIS 是什么、擅长什么、不擅长什么、有哪些工程特征"四个角度，对框架做一次整体定位。后面章节再展开技术原理、模型与算法细节。

### 1.1 FLORIS 是什么

FLORIS（FLOw Redirection and Induction in Steady State）是一套围绕**稳态工程尾流模型**构建的风电场分析框架。它要回答的核心问题是：在给定风资源、风机型号与控制策略下，**定量估计风电场的 AEP 以及场内的速度亏损与偏转**。

从技术栈定位看：

- **不是**高保真 CFD 求解器：不直接求解 N-S 方程；
- **不是**经验黑盒模型：尾流形成、偏转、恢复、叠加每一步都可被显式建模与替换；
- **是**介于解析工程模型与三维 CFD 之间的中低保真平台：物理可解释、计算效率高、可批量对比。

它把"风场仿真 + 控制优化 + 布局评估 + 不确定性分析"四件事接到同一个计算内核 `FlorisModel` 上，工程师可以按精度、速度与场景特点灵活组合模型与算法。

### 1.2 FLORIS 能做什么

按典型工程任务划分，FLORIS 主要覆盖以下场景：

- **AEP 评估**：在指定风况、机型与控制策略下，计算风电场年度发电量及场内功率分布；
- **布局优化**：在给定边界与最小间距约束下，搜索最大化 AEP 的机组布置（`LayoutOptimizationGridded` + `LayoutOptimizationScipy` / `LayoutOptimizationRandomSearch`）；
- **控制优化**：偏航对齐、降额控制（power setpoint）、价值函数（value function）导向控制；
- **流场可视化**：风速、风向、湍流强度在空间网格上的分布，以及尾流偏转形态；
- **批量工况计算**：在 `WindRose` / `TimeSeries` / `WindTIRose` 描述的多维风况矩阵上批量求 AEP；
- **复杂场景分析**：复杂地形（heterogeneous inflow）、复杂边界、多地块布置、浮式风机；
- **不确定性与稳健性**：`UncertainFlorisModel` 支持参数采样下的稳健性评估与敏感性分析。

### 1.3 FLORIS 不能做什么

明确"不做什么"对工程边界判断很重要。下列任务应交给更合适的工具，或在 FLORIS 之外做前置/后置处理：

- **长期风资源订正与代表性分析**：MCP（measure-correlate-predict）、测风数据质控、长期气候订正应在外部完成，FLORIS 只接受已合格的代表性风况作为输入；
- **复杂地形仅修正来流，不替代 CFD**：FLORIS 用 `HeterogeneousMap` 刻画地形对**来流风速**的空间乘数效应（地形加速 / 减速），但**不直接求解三维绕流**；完整 CFD / LES / WAsP 等高保真地形流场应在外部完成；
- **尾流模型假设平坦地形**：FLORIS 提供的尾流模型（Jensen / Gauss / Empirical Gauss / CC / TurbOPark / TurbOParkGauss 等）**默认建立在均匀、平坦来流假设上**。尾流在复杂地形上的演化（尾流上抬 / 下沉 / 弯曲、地形诱导恢复加速等）**未被建模**——地形对来流的影响通过 `HeterogeneousMap` 注入，但尾流在弯曲地形上的传播与恢复不在 FLORIS 能力范围内，这一点在 NREL FLORIS 官方文档中有明确说明；
- **电气与土建工程设计**：集电网络、道路、吊装平台、基础、海缆选型等不在 FLORIS 范围内；
- **秒级动态响应与瞬态仿真**：阵风、湍流脉动、机组动态控制、极端天气过程不在能力范围内，FLORIS 输出的是"10 分钟到 1 小时平均"意义上的稳态结果；
- **高精度载荷验证**：载荷是多物理场耦合问题（气动 + 结构 + 控制），不能把 FLORIS 的功率曲线 / 流场结果作为载荷计算的唯一依据。

### 1.4 FLORIS 的核心特征

理解下面五个特征，就能把握 FLORIS 与其他风场建模工具的差异：

- **稳态假设**：假设给定风况下风电场处于平衡态，计算速度快、可批量、适合布局优化；不直接用于瞬态分析。
- **模块化**：尾流被拆为 **速度亏损（velocity deficit）+ 偏转（deflection）+ 湍流（turbulence）+ 叠加（combination）** 四个子模块，可按场景独立替换、组合与调参（详见第 4 章）。
- **控制友好**：偏航、降额、价值函数、控制相关参数都能显式建模并直接参与优化（详见第 6 章、第 11 章）。
- **批量评估与并行**：`ParFlorisModel` 对风况矩阵自动并行化；`ApproxFlorisModel` 用解析近似加速；`UncertainFlorisModel` 在参数空间上做蒙特卡洛/拉丁超立方扫描；统一通过 `max_workers` 控制并发。
- **工程扩展已就位**：浮式风机、异质来流、多维 `Cp/Ct` 曲面、复杂边界、价值函数接口在官方实现中都已原生支持，可在同一框架内组合使用。

---

## 2. 工程问题与求解方法

§1 给出了 FLORIS "能做什么"的功能地图。本章自顶向下、逐步细化地讲清 FLORIS 是怎么把这些功能组合起来完成 **AEP 计算、布局优化和控制优化** 的。整体思路是：

> **问题 → 假设 → 原理 → 建模 → 优化 → 流程 → 接口**

每一层只讲"是什么"和"为什么"，具体模型与算法的实现细节留给对应的后续章节。

### 2.1 风电场优化问题：三层分解视角

把"风电场优化"这个大问题拆开，工程上关心的核心问题可以归为三句话：

1. **装在哪**——在给定场址里怎么排布机组，才能让 AEP 最大；
2. **怎么转**——对已经装好的机组，怎么设置偏航、降额、主动尾流控制等，才能让 AEP 或价值最大；
3. **一年发多少**——在已知风况、机型与控制策略下，风电场年发电量是多少，尾流损失有多大。

这三句话对应到 FLORIS 中的三类计算任务，**共享同一个计算内核 `FlorisModel`**：

| 工程问题 | FLORIS 任务 | 决策变量 | 典型方法 |
|------|----------|----------|----------|
| 一年发多少 | AEP 评估（正问题） | 无（给定布局与控制） | 批量工况并行计算 |
| 装在哪 | 布局优化（反问题） | 机组坐标 $(x_m, y_m)$ | 网格初始化 + 局部/全局精修 |
| 怎么转 | 控制优化（反问题） | 偏航角 $\gamma_m$、降额设定 $P_{\mathrm{set},m}$ | 梯度/启发式 + 风况矩阵评估 |

三类任务的差别只在"上层调用方式"上：正问题直接调用 `FlorisModel`；反问题把 `FlorisModel` 嵌入到外层优化器中作为目标函数。下文的建模、优化、流程章节会反复回到这张"三层任务表"。

### 2.2 核心假设：模型成立的边界

FLORIS 是一套**工程化**模型，它的速度来自一组明确的简化假设。理解这些假设，才知道结果的适用边界——这与 §1.3 的"不能做什么"清单是对偶关系：假设越强，能力范围越窄，计算也越快。

**稳态假设**。给定风速、风向、湍流强度和空气密度后，假设风电场处于平衡态，只输出"10 分钟到 1 小时平均"意义上的稳态结果。工程含义：

- 适合布局优化、批量方案比选与长期 AEP 评估；
- 计算成本远低于瞬态/CFD 仿真，可承担大量工况组合；
- 不适用于秒级载荷、动态控制律验证或瞬态尾流相互作用。

**工程化尾流假设**。尾流被参数化为"速度亏损 + 偏转 + 湍流附加 + 多尾流叠加"四个可替换子模块，而不是直接求解 N-S 方程。工程含义：

- 每一步的物理含义明确，可针对场景灵活选模型；
- 不替代 CFD 描述三维绕流细节（尾流上抬、下沉、弯曲、地形诱导恢复等）；
- 在平坦地形、稳态工况下与高精度模型吻合度较好。

**时空独立假设**。默认情况下，各机组的入流风速只取决于当前工况 $(wd, ws, ti)$，与历史时刻无关；同一风况矩阵下，各工况之间也是独立评估的。工程含义：

- 风况矩阵天然可并行（`ParFlorisModel` 利用这一点）；
- 不直接模拟"风向连续变化下的动态尾流过渡"。

**空间均匀来流假设（默认）**。在未启用 `HeterogeneousMap` 时，假设整个场址上自由来流是空间均匀的；启用后，空间非均匀来流以乘数场方式注入。详见 §8。

### 2.3 物理原理：尾流的形成与演化

不论 AEP 评估、布局优化还是控制优化，底层的物理过程都是同一个：**上游风机的尾流如何影响下游风机的入流**。本节先把这个物理过程分解为四步，具体模型选型留到 §4。

**速度亏损（velocity deficit）**。当上游风机从来流中提取能量后，下游尾流区的风速相对自由流降低，亏损强度由推力系数 $C_T$ 决定。亏损沿下游**逐渐扩张**（尾流宽度增长）并**逐渐恢复**（亏损衰减）。不同模型对扩张/恢复速率的描述不同：Jensen 用线性扩张，Gauss 用高斯分布，等等。

**尾流偏转（deflection）**。当上游风机做**偏航失配**（主动偏航或被动对风误差）时，尾流中心线会向侧向偏移。偏转模型描述偏移大小与恢复过程（Jimenez 解析式、Gauss 偏转等）。偏转的存在意味着：即使风从正前方来，如果上游机组主动偏航，也能给下游让出更多风能——这是主动尾流控制（AWC）的物理基础。

**湍流附加（turbulence）**。尾流区的湍流强度会升高，反过来加速尾流的恢复。湍流模型刻画"附加湍流 → 恢复加速"的耦合关系（Crespo-Hernandez 是经典经验式，基于 RANS/LES 数据拟合）。当输入场 TI 显著变化时，湍流模型对 AEP 的影响会显现。

**多尾流叠加（combination）**。当多台上游风机同时影响同一位置时，需要把多个尾流亏损合成为总亏损。叠加方式（线性叠加、平方和开方、几何叠加等）会影响下游机组的入流估计。

这四步是 FLORIS 中所有尾流模型的统一骨架，差别仅在于各步的数学表达。工程上的模块化也由此而来：**换模型就是换某一步的具体函数**，不需要改动其他三步。

### 2.4 数学建模：从物理到方程

把 §2.3 的物理过程形式化，就得到四组数学模型。FLORIS 把每组都做成可替换的"积木"，工程上的灵活性由此而来。

**风况模型（wind resource）**。把风况描述为可枚举的工况集合，FLORIS 给出三种主要接口：

- `TimeSeries`：按时序给出 $(ws, wd, ti)$ 序列，适合做 8760 小时 AEP；
- `WindRose`：按风向 × 风速的二维频率分布，适合方案比选；
- `WindTIRose`：在 WindRose 基础上把 TI 也作为维度，适合 TI 显著影响尾流恢复的场景。

建模细节、转换方式与质量检查清单见 §7。

**风机模型（turbine）**。以致动盘理论为基础，核心是两条曲线：

- **功率曲线** $P(u)$：风速到有功的映射（切入以下为零，切入至额定近似三次方增长，额定以上恒定，切出以上归零）；
- **推力系数曲线** $C_T(u)$：风速到 $C_T$ 的映射，决定风机对来流动量的抽取强度。

通过**操作模型**（operation model）进一步反映控制策略：cosine-loss（偏航损失）、derating（降额）、AWC（主动尾流控制）、peak-shaving（峰值削减）、controller-dependent（控制器依赖）等。操作模型详见 §6.3，多机型混排详见 §6.6。

**尾流模型（wake）**。把 §2.3 的四步形式化为可调用的子模型组合，FLORIS 提供多个候选：

- 速度亏损：Jensen、Gauss、Empirical Gauss、Cumulative Gauss Curl、TurbOPark、TurbOParkGauss；
- 偏转：Jimenez、Gauss、Empirical Gauss；
- 湍流：Crespo-Hernandez、wake-induced mixing、None；
- 叠加：线性、平方和开方、几何等。

选型决策表见 §4.5。

**异质来流模型（heterogeneous inflow）**。当来流空间上不均匀（复杂地形、海陆过渡），FLORIS 用 `HeterogeneousMap` 注入空间速度乘数场，刻画"地形加速/减速"对自由来流的修正。地形上叠加风切变（`wind_shear` $\alpha$）与风向扭转（`wind_veer` $\beta$），共同描述非平坦、非均匀来流。详见 §8。

**AEP 表达式**。在给定工况 $(wd_i, ws_j)$ 下，机组 $m$ 的有效入流为：

$$
U_{\mathrm{eff},m}(wd_i, ws_j) = U_\infty(wd_i, ws_j) - \Delta U_m(wd_i, ws_j)
$$

其中 $\Delta U_m$ 是经速度亏损、偏转、湍流修正和多尾流叠加后的总亏损。机组功率由功率曲线映射得到 $P_m = \mathcal{P}(U_{\mathrm{eff},m})$，风场总功率为 $\sum_m P_m$。全年 AEP 通过联合频率加权：

$$
AEP = \sum_{i=1}^{N_{wd}} \sum_{j=1}^{N_{ws}} P_{\mathrm{farm}}(wd_i, ws_j) \cdot f(wd_i, ws_j) \cdot 8760
$$

当 TI 维度被加入时，求和扩展为三维离散加权。AEP 的完整推导、派生指标与一致性检查见 §3。

### 2.5 优化建模：从方程到目标函数

把"求解 AEP"提升为"最大化 AEP"，需要一个外层的优化器把 §2.4 的方程包成目标函数。

**决策变量**。三类优化任务共享 `FlorisModel`，但决策变量不同：

- 布局优化：$\mathbf{x} = (x_m, y_m)_{m=1}^{N_t}$，每台机组的平面坐标；
- 控制优化：$\mathbf{u} = (\gamma_m, P_{\mathrm{set},m})_{m=1}^{N_t}$，每台机组的偏航角与功率设定，通常随工况变化；
- 混合优化：同时调整坐标与控制。

**目标函数**。AEP 是默认目标，FLORIS 也支持扩展：

| 上层目标 | 与 AEP 的关系 | FLORIS 角色 |
|------|---------------|-------------|
| AEP 最大化 | 直接等同 | 直接计算 |
| AVP（年度价值产量） | AEP × 电价权重 | 加 `WindRose.value_table` |
| LCOE 最小化 | AEP 在分母；CapEx/OpEx 需外部 | FLORIS 仅算 AEP |
| 价值函数 | 任意用户定义 | 通过 `value_functions` 接口 |

具体的目标函数设计与权衡详见 §3.5 和 §11.2。

**约束**。三类工程约束，FLORIS 都支持：

- **几何约束**：机组必须落在给定的允许边界内（`boundaries`），且与禁布区保持安全距离；
- **最小间距约束**：任意两台机组之间的距离 $\geq$ `min_dist`（常用 $2\sim 5$ 倍转子直径 $D$）；
- **控制约束**：偏航角范围、降额系数上下限、控制切换时序等。

**优化问题分类**。三类问题在数学性质上差别很大：

- **AEP 评估（正问题）**：给定 $\mathbf{x}$、$\mathbf{u}$ 与风况，直接求 AEP。本质是一次"批量工况计算"，无迭代；
- **布局优化（组合 + 连续）**：$\mathbf{x}$ 是 $2N_t$ 维连续变量，但目标函数高度非凸（尾流耦合导致），实用上用"网格初始化 + 局部/全局精修"两步法；
- **控制优化（连续）**：$\mathbf{u}$ 是 $2N_t$ 维连续变量，在选定的尾流模型下可微，适合梯度方法或启发式方法。

### 2.6 标准工作流程

三类任务在 FLORIS 中共享一条主干流程，差异只在循环和终止条件上不同：

> **风况准备 → 风机/场址 → 边界与约束 → 初始解 → 物理配置 → 优化求解 → 后处理评估**

各步骤的工程含义与 FLORIS 接口：

1. **风况准备**。把测风 / MCP / ERA5 数据整理成 `TimeSeries` / `WindRose` / `WindTIRose`，确保风速、风向、TI 都有代表性长期分布。详见 §7。
2. **风机与场址**。选定机型（功率曲线、$C_T$ 曲线、转子直径 $D$、轮毂高度），并准备好场址 GeoJSON（地块边界、禁布区、UTM 投影）。详见 §6。
3. **边界与约束**。从地块 + 禁布区几何计算"可安装区域"多边形，定义 `min_dist`、控制约束等。详见 §11.2。
4. **初始解**。对布局优化，先用 `LayoutOptimizationGridded` 在可安装区域做"网格化最大填充"，得到一个工程合理的初始布局；对控制优化，初始解通常是"全部对风 + 额定功率"或历史最优。
5. **物理配置**。选定尾流模型组合（§4.5 决策表）、湍流模型、是否启用 `HeterogeneousMap`（复杂地形）。这一步直接决定后续计算的物理保真度与速度。
6. **优化求解**。外层优化器迭代调用 `FlorisModel` 求 AEP，典型组合：
   - 布局优化：`LayoutOptimizationGridded` → `LayoutOptimizationScipy`（SLSQP，<50 台）或 `LayoutOptimizationRandomSearch`（>50 台或边界复杂）；
   - 控制优化：梯度方法（SciPy SLSQP、COBYLA）或启发式方法（遗传、模拟退火、FLORIS 自带的 yaw optimization driver）。
7. **后处理评估**。对比优化前/后的 AEP、容量因子、尾流损失率，绘制流场与布局图，输出 JSON/CSV 报告。

**并行策略**。FLORIS 的并行有两层，工程上要分清：

- **工况级并行**（默认）：`ParFlorisModel` 自动把风况矩阵的不同工况分给多个 CPU/进程，适合 AEP 评估与优化内层；
- **优化器级并行**：`LayoutOptimizationRandomSearch` 等算法可在外层"批量采样"时进一步并行。

两层并行通过 `max_workers` 统一控制（默认 -1 = 所有 CPU），无需手动管理 worker。

**与高保真 CFD 的衔接**。FLORIS 与 CFD 是互补关系，而非替代关系。整体数据流是：

```
DEM / 地形
    ↓
CFD / WRF / WAsP（高保真流场求解）
    ↓
WS / WD / TI / Shear / Veer
    ↓
FLORIS（工程级尾流 + 优化）
    ↓
AEP / 布局 / 控制策略
```

FLORIS 真正需要的是"风速、风向、TI、Shear、Veer"等已经过外部模型预处理后的来流条件，而不是 DEM 本身。复杂地形、海岸线等造成的非均匀来流通过 `HeterogeneousMap` 注入（详见 §8）。

### 2.7 模块映射：从工程动作到 FLORIS 接口

下表把"工程上要做的事"映射到"FLORIS 中要调的接口"，帮助读者快速定位后续章节。

| 工程动作 | FLORIS 接口 | 详见 |
|----------|------------|------|
| 加载风况 | `TimeSeries` / `WindRose` / `WindTIRose` | §7 |
| 加载机型 | `turbine_type`（内置/用户） | §6 |
| 加载场址 | `boundaries`（GeoJSON/Shapely） | §11.2 |
| 选尾流模型 | `wake` 子配置 | §4 |
| 异质来流 | `HeterogeneousMap` | §8 |
| AEP 评估 | `FlorisModel.get_farm_AEP()` | §3 |
| 时序 AEP | `FlorisModel.get_turbine_P()` | §3.8 |
| 布局优化 | `LayoutOptimizationGridded` / `Scipy` / `RandomSearch` | §5.1 |
| 降额 / 价值控制 | `power_setpoint` / `value_functions` | §6.3 / §11.2 |
| 批量 / 并行 | `ParFlorisModel` / `max_workers` | §3.10 |
| 不确定性 | `UncertainFlorisModel` | §9 |
| 浮式 | `floating_tilt_table` | §10 |

### 2.8 输入与输出（详细）

承接 §2.7 的“模块映射”索引表，本节把每个工程动作背后的**具体入参 / 出参 / 参数约束**展开为可查的速查表。

#### 2.8.1 典型输入

**必须具备**：

- 风机坐标 `layout_x`, `layout_y`；
- 轮毂高度、转子直径、功率曲线或 $C_P/C_T$ 数据；
- 风速、风向离散工况；
- 每个工况对应的频率权重或联合频率矩阵；
- 环境湍流强度；
- 至少一套明确的尾流模型组合配置。

**建议补充**：

- 空气密度和风切变参数；
- 场址边界、禁布区和最小间距约束；
- heterogeneous inflow / map；
- 不同机型或运行模式下的多维 $C_P/C_T$ 数据；
- 风向偏差、湍流波动和模型参数不确定性分布；
- 用于结果复核的实测 SCADA 或测风塔统计数据。

#### 2.8.2 典型输出

- 风场总 AEP、毛发电量与净发电量；
- 容量因子、尾流损失率；
- 单机发电量分布和主要受尾流影响机组；
- 不同风向和风速区间的发电贡献；
- 优化前后布局或控制策略的增益对比。

#### 2.8.3 关键参数速查

##### 2.8.3.1 空间分辨率要求

**均匀来流**（Homogeneous Inflow）：

- 不需要空间网格；
- 只需风速频率、风向频率、TI。

**非均匀来流**（Heterogeneous Inflow）：

- 需要空间网格 $U = U(x, y)$；
- 推荐分辨率：复杂地形 50–100 m；一般建议 $\le 0.5D$（$D$ 为转子直径）。

**常见数据源分辨率**：

| 数据源 | 分辨率 |
|----------|----------|
| ERA5 | 25–31 km |
| WRF | 333 m – 1 km |
| CFD | 20–100 m |

##### 2.8.3.2 缺失数据处理

- **空间插值**：相邻格点双线性插值；
- **最近邻**：使用最近有效数据点；
- **外推**：根据风资源梯度外推。

具体方式取决于风资源接口配置。

##### 2.8.3.3 风资源输入形式

FLORIS 的风资源输入**可以是内存对象**，不强制磁盘文件。可以：

- 构造 Python 字典或 Pandas DataFrame；
- 直接传入 `UncertaintyInterface` 等接口；
- 从 GRIB、NetCDF 读取后加载到内存中处理。

##### 2.8.3.4 尾流参数设置

**Cumulative Gauss Curl 等复杂模型的参数**（$a_s$、$b_s$、$c_{s1}$、$c_{s2}$、$a_f$、$b_f$、$c_f$）通常**建议直接使用 FLORIS 默认值**。若没有 SCADA 校准、LES 或 CFD 数据，优先保证 $C_T$ 曲线和 TI 准确，尾流参数保持默认即可。

---

## 3. AEP 计算原理与建模

### 3.1 AEP 本质上只有两类输入：风况 × 风机

AEP 计算的所有输入，本质上可归为**两类**：

1. **风况**（Wind Conditions）：描述风在大气中如何存在
2. **风机**（Turbine）：描述风如何被转化为电

AEP 在数学上可抽象为这两类的"内积"：

$$
\mathrm{AEP} = \int_{\text{风况}} \int_{\text{风机}} \mathrm{Power}(\text{风}, \text{机}) \cdot d\text{风} \cdot d\text{机}
$$

离散化后：

$$
\mathrm{AEP} = \sum_{w \in \text{风况}} \sum_{t \in \text{风机}} P(w, t) \cdot f(w) \cdot 8760
$$

其中 $w$ 是风况（包含来流风速、风向、TI、Shear、Veer、空间异质性等所有"风"的属性），$t$ 是风机（包含机型、布局、控制策略等所有"机"的属性）。

**关键洞察**：

- **看似并列的"尾流"、"地形"、"稳定度"、"异质性"，本质上都是风况在空间/时间/高度/方向上的变化或扰动** —— 它们不是与"风况"并列的第三类维度，而是对风况的修正。
- 当风况 $U_{\mathrm{eff}}$ 已知时，任意风机的功率 $P$ 唯一确定。FLORIS 的全部计算就是"把这两类输入按物理规律对齐得到 AEP"。
- FLORIS 输入清单虽多（功率曲线、$C_T$ 曲线、风速风向频率、TI、密度、HeterogeneousMap、布局…），但**每一项都归属于这两类中的一类**。
- **AEP 是几乎所有风电场优化的"原子量"**。上层目标（AVP、LCOE、容量因子、尾流损失率、载荷…）都建立在 AEP 之上。

| 上层目标 | 与 AEP 的关系 | FLORIS 角色 |
|------|---------------|-------------|
| AEP 最大化 | 直接等同 | 直接计算 |
| AVP（年度价值产量） | AEP × 电价权重 | 加 `WindRose.value_table` |
| LCOE 最小化 | AEP 在分母；CapEx/OpEx 需外部 | FLORIS 仅算 AEP |
| 容量因子最大化 | AEP / (P_rated · 8760) | 直接计算 |
| 尾流损失率最小化 | $1 - \mathrm{AEP}_{\text{actual}} / \mathrm{AEP}_{\text{no-wake}}$ | 同时算两次 AEP |
| 载荷最小化 | 与 AEP 加权 | 配合外部载荷分析 |

### 3.2 风况这一类

风况在 FLORIS 中由若干子维度共同描述，每个子维度刻画"风"的不同物理属性：

| 子维度 | 描述 | FLORIS 体现 |
|------|------|------------|
| **风速频率** | 各风速段出现的概率 | `wind_speeds` + `freq_table` |
| **风向频率** | 各风向扇区出现的概率 | `wind_directions` + `freq_table` |
| **湍流强度（TI）** | 风的脉动程度 | `turbulence_intensities` / `WindTIRose` |
| **垂直结构** | 风速、风向随高度变化 | `wind_shear` ($\alpha$)、`wind_veer` ($\beta$) |
| **空气密度** | 风的物质密度 | `air_density` |
| **空间异质性** | 风在不同空间位置的变化 | `HeterogeneousMap`（详见 §8） |

**核心理解**：风况这一类**只有一个对象**——风本身；上述子维度都是风的某一方面。所有子维度必须协同描述，缺一会丢失关键信息。

### 3.3 风机这一类

风机在 FLORIS 中由以下属性描述：

| 属性 | 描述 | FLORIS 体现 |
|------|------|------------|
| **气动性能** | 功率曲线 $P(U)$、推力曲线 $C_T(U)$ | `power_thrust_table` |
| **几何参数** | 轮毂高度 $z_h$、转子直径 $D$、TSR | `hub_height`、`rotor_diameter` |
| **布局** | 各台风机的位置 $(x_i, y_i)$ | `layout_x`、`layout_y` |
| **控制策略** | 偏航、降额、AWC 等 | `operation_model` |
| **环境适应** | 与 TI/波高等耦合的性能面 | 多维 `Cp/Ct` 表 |

**核心理解**：风机这一类**只关心"机"如何把风转成电**。当风 $U_{\mathrm{eff}}$ 已知时，风机功率 $P$ 唯一确定。

### 3.4 看似独立的物理现象：都是风况的变化或影响

工程上常被列为"独立模块"的现象，本质上都是**对风况的修正**或**对风机的修正**：

| 现象 | 物理本质 | 在两类中的归属 |
|------|---------|---------------|
| 自由来流风速 | 风的直接属性 | 风况 |
| **尾流速度亏损** | 上游风机对下游风况的扰动 | **风况的修正** |
| 尾流偏转 | 偏航后尾流中心线偏移 | 风况的修正 |
| 尾流诱导湍流 | 尾流区 TI 增强 | 风况的修正 |
| **地形加速/减速** | 地形对自由来流的修正 | 风况的修正（HeterogeneousMap） |
| 海陆过渡 | 大尺度空间梯度 | 风况的修正（HeterogeneousMap） |
| 风切变 | 风速随高度变化 | 风况的子维度（已在 §3.2 列出） |
| 风向扭转（Veer） | 风向随高度变化 | 风况的子维度 |
| 大气稳定度 | 影响湍流强度 | 通过 TI 间接表达 → 风况 |
| 浮式倾角 | 平台运动改变转子姿态 | **风机的修正**（操作模型 + 浮动倾角表） |

**统一视角**：所有"风相关的物理"最终都通过**有效入流风速 $U_{\mathrm{eff}}$** 进入 AEP 计算；所有"机相关的物理"最终都通过**功率映射 $\mathcal{P}(U)$** 进入 AEP 计算。FLORIS 内部没有"尾流维度"、"地形维度"或"稳定度维度"——它们都被表达为对风况 $U_{\mathrm{eff}}$ 的修正项。

**重要工程含义**：忽略了地形加速会严重低估 AEP；在山地风场中，地形增益（10–30%）往往大于尾流损失（5–10%）。因此，"风况修正"模块的精度比"风机模型"对 AEP 误差的影响更大。

### 3.5 AEP 的数学定义

#### 3.5.1 基本表达式

AEP 是风电场在全年统计风况下的预期发电量。在 FLORIS 的离散工况框架下：

$$
\mathrm{AEP} = \sum_{i=1}^{N_{wd}} \sum_{j=1}^{N_{ws}} P_{\mathrm{farm}}(wd_i, ws_j) \cdot f(wd_i, ws_j) \cdot 8760
$$

其中：

- $P_{\mathrm{farm}}(wd_i, ws_j)$：在第 $i$ 个风向、第 $j$ 个风速工况下的风场总功率（kW），由 FLORIS 的稳态尾流模型计算；
- $f(wd_i, ws_j)$：对应工况的联合频率（无量纲，$\sum f = 1$）；
- $8760$：全年小时数；
- $N_{wd}, N_{ws}$：风向扇区数、风速分箱数。

#### 3.5.2 多维扩展

如果加入 TI 维度（湍流强度作为第三维）：

$$
\mathrm{AEP} = \sum_{i=1}^{N_{wd}} \sum_{j=1}^{N_{ws}} \sum_{k=1}^{N_{ti}} P_{\mathrm{farm}}(wd_i, ws_j, ti_k) \cdot f(wd_i, ws_j, ti_k) \cdot 8760
$$

也可进一步按季节/分时权重展开：

$$
\mathrm{AEP} = \sum_{s=1}^{N_s} w_s \cdot \mathrm{AEP}_s
$$

其中 $w_s$ 为第 $s$ 个季节/时段权重。

#### 3.5.3 相关派生指标

- **容量因子（Capacity Factor）**：

$$
\mathrm{CF} = \frac{\mathrm{AEP}}{P_{\mathrm{rated,farm}} \cdot 8760}
$$

- **毛发电量**（不考虑尾流损失的理论发电量）：通过 `FlorisModel` 不计尾流或关闭尾流模型计算；
- **净发电量**：包含尾流损失的 AEP；
- **尾流损失率**：

$$
\eta_{\mathrm{wake}} = 1 - \frac{\mathrm{AEP}_{\mathrm{actual}}}{\mathrm{AEP}_{\mathrm{no-wake}}}
$$

工程上毛/净 AEP 的差异通常在 5–15% 之间，密集布局下可达 20% 以上。

### 3.6 AEP 计算的链式分解

AEP 不是单一公式，而是**一条由五个环节组成的计算链**。链的两端是风况和风机：

$$
\text{风况数据} \xrightarrow{\text{离散化}} \text{工况集合} \xrightarrow{\text{风况修正}} \text{有效入流风速} \xrightarrow{\text{功率映射}} \text{单机功率} \xrightarrow{\text{求和}} \text{风场总功率} \xrightarrow{\text{加权}} \text{AEP}
$$

其中"风况修正"包括尾流模型、地形异质 inflow 等所有"对风的扰动"；"功率映射"是风机的固有属性 $P = \mathcal{P}(U)$。

**逐步拆解**：

1. **风况数据 → 离散工况集合**
   - 外部完成 MCP 订正、长期代表性修正；
   - 选择风向扇区数（8/12/36）和风速分箱（1 m/s 或基于功率曲线关键点）；
   - 必要时引入 TI 维度（WindTIRose）；
   - 必要时引入空间维度（HeterogeneousMap）。

2. **风况修正（风况的细化）→ 有效入流风速**
   - 对每个 $(wd_i, ws_j, ti_k)$ 工况，计算每台机组的有效入流风速 $U_{\mathrm{eff},m}$：

$$
U_{\mathrm{eff},m}(wd_i, ws_j) = U_\infty(wd_i, ws_j) \cdot M(x_m, y_m) - \Delta U_m^{\mathrm{wake}}(wd_i, ws_j)
$$

其中 $M$ 是空间异质乘数（HeterogeneousMap），$\Delta U^{\mathrm{wake}}$ 是尾流亏损。

3. **功率映射（风机的固有属性）→ 单机功率**
   - 通过功率曲线（含偏航/倾角/降额等操作模型修正）映射：

$$
P_m(wd_i, ws_j) = \mathcal{P}\big(U_{\mathrm{eff},m}(wd_i, ws_j)\big)
$$

4. **单机功率 → 风场总功率**

$$
P_{\mathrm{farm}}(wd_i, ws_j) = \sum_{m=1}^{N_t} P_m(wd_i, ws_j)
$$

5. **风场总功率 → AEP**
   - 按联合频率加权，乘 8760：

$$
\mathrm{AEP} = 8760 \cdot \sum_{i,j} P_{\mathrm{farm}}(wd_i, ws_j) \cdot f(wd_i, ws_j)
$$

**误差传递特性**：

- 误差**累积**：风况分箱误差 + 风况修正偏差 + 功率曲线误差 + 频率权重偏差 → 最终 AEP 误差；
- 误差**放大**：尾流模型对 $C_T$ 的 5% 偏差在密集布局下可导致 AEP 偏差 1–3%；
- 误差**非线性**：功率与风速的三次方关系放大低风速区误差；联合频率的小分箱若被错误归并会显著影响 AEP。

因此，AEP 计算的**模型选型**和**输入精度**必须匹配工程可接受误差。

### 3.7 为计算 AEP 需要建立的模型

按"风况 / 风机 / 风况修正"三类组织：

| 子模型 | 归属类别 | 关键参数 | FLORIS 接口 |
|------|------|---------|-------------|
| **风况模型** | 风况 | 风向/风速/TI 联合频率、垂直结构、密度 | `wind_data`（TimeSeries/WindRose/WindTIRose） |
| **风机模型** | 风机 | 功率曲线、$C_T$ 曲线、几何参数、操作模型 | `turbine_type` |
| **尾流模型** | 风况的修正 | 速度亏损、偏转、湍流、叠加 | `wake` 子配置（详见 §4） |
| **异质 inflow** | 风况的修正 | 空间速度乘数场 | `HeterogeneousMap`（详见 §8） |
| **场址模型** | 风机的载体 | 边界多边形、禁布区、最小间距 | `boundaries`（布局优化时） |

**关键认识**：

- 5 个子模型中，**只有"风况模型"和"风机模型"是独立输入**；其余三个本质上是对这两类的修正或约束。
- FLORIS 的核心计算引擎只解决"**如何把风况和风机对齐得到 AEP**"。
- §4 尾流模型和 §8 异质来流都属于"风况修正"——它们和 §6 风机模型不是并列模块。

### 3.8 AEP 计算所需的输入

按"必备"和"建议补充"两层组织，并明确每个输入在两类中的归属。

#### 3.8.1 必须具备的输入

**风况类（必备）**：

| 参数 | 说明 |
|------|------|
| `wind_directions` | 离散风向扇区中心或边界 |
| `wind_speeds` | 离散风速分箱中心或边界 |
| `frequencies` 或 `freq_table` | 联合频率，sum=1 |
| `turbulence_intensities` | 环境湍流强度，可为常数或数组 |

**风机类（必备）**：

| 参数 | 说明 |
|------|------|
| `layout_x`, `layout_y` | 风机 UTM 坐标（m） |
| 轮毂高度 $z_h$、转子直径 $D$ | 从功率曲线/机型配置中提取 |
| 功率曲线（`wind_speed` vs `power`） | 查找表，覆盖切入到切出 |
| 推力系数曲线（`wind_speed` vs `thrust_coefficient`） | 查找表，与功率曲线同源 |

**风况修正类（必备）**：

| 参数 | 说明 |
|------|------|
| 速度亏损模型类型 | `jensen` / `gauss` / `empirical_gauss` / `cumulative_gauss_curl` / `turbopark` |
| 偏转模型类型 | `none` / `jimenez` / `gauss` / `empirical_gauss` |
| 湍流模型类型 | `none` / `crespo_hernandez` / `wake_induced_mixing` |
| 叠加模型类型 | `fls` / `sosfs` / `max` |

#### 3.8.2 建议补充的输入

| 类别（归属） | 参数 | 作用 |
|------|------|------|
| **风况** | `air_density` | 密度修正，默认 1.225 kg/m³ |
| **风况** | `wind_shear` ($\alpha$) | 风切变指数，影响转子面风速分布 |
| **风况** | `wind_veer` ($\beta$) | 风向扭转率 |
| **风况修正** | `HeterogeneousMap` | 复杂地形/海陆过渡下的空间非均匀来流（详见 §8） |
| **风况修正** | TI 维度（`WindTIRose`） | 当 TI 显著影响尾流恢复时使用 |
| **风机** | 多维 `Cp/Ct` 表 | 与 TI/波高等耦合的性能面 |
| **风机** | 操作模型 | cosine-loss / derating / AWC / peak-shaving / controller-dependent |
| **场址** | `boundaries` | 边界多边形（布局优化时） |
| **场址** | `min_dist` | 最小间距约束（布局优化时） |
| **不确定** | 风向偏差分布 | `UncertainFlorisModel` 用 |
| **不确定** | 风速扰动分布 | `UncertainFlorisModel` 用 |
| **不确定** | 模型参数分布（$C_T$、$k$ 等） | `UncertainFlorisModel` 用 |
| **校核** | 实测 SCADA 数据 | 用于结果校核 |

#### 3.8.3 输入一致性检查清单

工程上 AEP 误差的最大来源是**输入口径不一致**。提交计算前应逐项检查：

- [ ] 风向定义和坐标系一致（0° 起点、顺时针/逆时针）；
- [ ] 联合频率 $\sum f = 1$；
- [ ] 功率曲线与 $C_T$ 曲线对应同一机型版本、同一参考密度；
- [ ] 湍流强度在物理合理区间（海上 0.04–0.12，复杂地形可更高）；
- [ ] 风机坐标与场址边界坐标系一致（UTM 区号、东西/北向）；
- [ ] HeterogeneousMap 的参考点和参考风速与风况数据对应；
- [ ] 优化阶段和最终评估阶段使用同一组风况统计口径；
- [ ] 单位统一：风速 m/s、功率 kW、距离 m、频率无量纲；
- [ ] 切入/切出风速与功率曲线端点匹配；
- [ ] 最小间距单位明确（绝对值 m 或 $D$ 的倍数）。

### 3.9 AEP 计算的输出指标体系

完整的 AEP 评估应同时给出**总量指标、结构性指标和损失类指标**三类，便于工程决策和方案比选。

#### 3.9.1 总量指标

- **风场总 AEP**（GWh）：直接用于经济测算；
- **毛发电量**：不考虑尾流，理论上限；
- **净发电量**：包含尾流损失的实际可发电量；
- **容量因子**：实际发电 / 满发小时数。

#### 3.9.2 结构性指标

- **单机 AEP 分布**：识别受尾流影响最严重的机组；
- **分风向 AEP 贡献**：识别主导发电风向扇区；
- **分风速 AEP 贡献**：识别最优运行风速区间；
- **分季节 AEP 贡献**：用于运维计划、电网调度。

#### 3.9.3 损失类指标

- **尾流损失率** = $1 - \mathrm{AEP}_{\mathrm{actual}} / \mathrm{AEP}_{\mathrm{no-wake}}$；
- **场内损失分布**：识别尾流损失集中在哪几台机组；
- **优化前后 AEP 提升率**：

$$
\eta_{\mathrm{AEP}} = \frac{\mathrm{AEP}_{\mathrm{opt}} - \mathrm{AEP}_{\mathrm{base}}}{\mathrm{AEP}_{\mathrm{base}}} \times 100\%
$$

- **典型尾流损失率参考**：单排列布局 2–5%，多排密集布局 8–15%，极端密集 20%+。

### 3.10 推荐的 AEP 评估流程

工程上推荐按以下顺序开展 AEP 评估。**先确认两类必备输入**（风况、风机），**再选择修正模块**（尾流、异质 inflow），**最后校核**。

```
1. 输入准备（按"两类"组织）
   ├─ 风况：测风塔/再分析 → MCP 订正 → 联合频率表
   ├─ 风机：选择机型 → 功率曲线 + Ct 曲线 + 布局
   └─ 修正：选择尾流模型组 + 是否需要 HeterogeneousMap
2. 模型建立
   ├─ 风况模型（TimeSeries / WindRose / WindTIRose）
   ├─ 风机模型（turbine_type + operation_model）
   ├─ 尾流模型组（速度亏损 + 偏转 + 湍流 + 叠加）
   ├─ 异质 inflow（若需要）
   └─ 场址模型（边界、禁布区）
3. 基准评估
   ├─ 关闭尾流：计算毛 AEP（"完美风况"下的发电能力）
   └─ 开启尾流：计算净 AEP
4. 多工况批量计算
   ├─ 逐工况调用 FLORIS
   └─ 按联合频率加权
5. 指标输出
   ├─ 总量指标（AEP、容量因子）
   ├─ 结构性指标（单机/分风向/分风速贡献）
   └─ 损失类指标（尾流损失率、主导损失机组）
6. 校核与敏感性分析
   ├─ 对照 SCADA 实测（若可用）
   ├─ 关键参数敏感性（TI、k、Shear）
   └─ 不确定性区间（UncertainFlorisModel）
7. 方案比选/优化
   ├─ 在统一风况/模型下比较不同布局
   ├─ 比较不同机型/控制策略
   └─ 输出推荐方案
```

**关键工程原则**：

- AEP 评估的**可信度首先来自两类输入**（风况 + 风机），其次才是修正模块（尾流、异质 inflow）；
- **多工况并用毛/净 AEP 计算**得到尾流损失率，比单一 AEP 数字更有解释力；
- **分风向/分风速分解**能识别优化机会，避免"总 AEP 提升"掩盖局部恶化；
- **校核环节不可省略**，特别是与 SCADA/测风塔实测对比。

---

## 4. 尾流模型体系

### 4.1 速度亏损模型

#### 4.1.1 Jensen 模型（`jensen.py`）

又称 Park 模型，将尾流近似为随下游距离线性扩张的"顶帽型"区域，内部速度亏损近似均匀：

$$
\Delta U(x) = U_\infty \left(1 - \sqrt{1 - \frac{C_T}{(1 + 2kx/D)^2}}\right)
$$

工程特点：参数少、计算快、稳定性高；适合前期大范围方案筛选。局限：对横向尾流结构和偏航效应表达较粗。

**尾流扩张系数 $k$ 的工程取值**：

| 场景 | $k$ |
|--------|------|
| 海上稳定层 | 0.02–0.04 |
| 海上中性层 | 0.04–0.06 |
| 陆上平坦地形 | 0.06–0.08 |
| 复杂地形 | 0.08–0.12 |

#### 4.1.2 Gauss 模型（`gauss.py`）

用高斯分布描述尾流截面速度亏损，认为中心亏损最大、往边缘平滑衰减：

$$
\frac{\Delta U}{U_\infty} = C(x)\exp\left(-\frac{(y-\delta)^2}{2\sigma_y^2} - \frac{(z-z_h)^2}{2\sigma_z^2}\right)
$$

工程特点：尾流截面分布平滑，更适合分析偏航控制、非均匀来流和尾流重叠。计算成本略高于 Jensen，但物理表达更细致。

#### 4.1.3 Empirical Gauss 模型（`empirical_gauss.py`）

在高斯尾流框架上加入经验修正，便于工程校准和特定数据集上的表现。保留高斯分布主要结构，对尾流扩张、近尾流到远尾流过渡、偏转与恢复行为做经验参数化。

#### 4.1.4 Cumulative Gauss Curl 模型（`cumulative_gauss_curl.py`）

在高斯尾流基础上增强对旋转、偏航和尾流卷吸效应的表达能力。

特征宽度：

$$
\sigma_n = k\tilde{x} + \varepsilon, \quad k = a_s I + b_s, \quad \varepsilon = (c_{s1}C_T + c_{s2})\sqrt{\beta}
$$

$$
\beta = \frac{1}{2}\frac{1+\sqrt{1-C_T}}{\sqrt{1-C_T}}
$$

累计重叠项：

$$
\Lambda = \sum_{m=1}^{i-1}\lambda_m \frac{C_m}{U_\infty}, \quad
\lambda_m = \frac{\sigma_m^2}{\sigma_n^2 + \sigma_m^2}\exp\left(-\frac{Y_m^2 + Z_m^2}{2(\sigma_n^2+\sigma_m^2)}\right)
$$

超高斯亏损形式：

$$
\frac{\Delta U}{U_\infty} = C\exp\left(-\frac{\tilde{r}^{\,n}}{2\sigma_n^2}\right), \quad n = a_f\exp(b_f\tilde{x}) + c_f
$$

工程价值：相比标准 Gauss，对偏航诱导旋转、卷吸、复杂横向结构和近-远尾流过渡表达更强，适合偏航控制和复杂尾流研究。但参数更多、计算更重、标定要求更高。

#### 4.1.5 TurbOPark / TurbOParkGauss（`turbopark.py`, `turboparkgauss.py`）

面向大尺度风电场尾流相互作用，强调长距离尾流恢复与风场整体背景效应。适合海上大型风电场或长列阵风机。

### 4.2 偏转模型

偏转模型计算尾流中心线偏移量 $\delta(x) = f(x, \gamma, C_T, TI, \ldots)$，其中 $\gamma$ 为偏航角。

#### 4.2.1 Jimenez 偏转模型（`jimenez.py`）

用较低计算成本把偏航造成的横向动量偏置转化为尾流中心线位移：

$$
\xi_{\mathrm{init}} = \frac{1}{2}C_T\cos\gamma\sin\gamma
$$

$$
\delta(\Delta x) = \frac{\xi_{\mathrm{init}}A}{B} - \frac{C}{D} + a_d + b_d\Delta x
$$

$$
A = 15\left(2k_d\frac{\Delta x}{D}+1\right)^4 + \xi_{\mathrm{init}}^2
$$

$$
B = \frac{30k_d}{D}\left(2k_d\frac{\Delta x}{D}+1\right)^5
$$

$$
C = \xi_{\mathrm{init}}D(15+\xi_{\mathrm{init}}^2), \quad D = 30k_d
$$

适合快速估算偏航对下游风机入流的侧向影响、早期偏航控制研究或批量扫描。

#### 4.2.2 Gauss 偏转模型（`gauss.py`）

通常与 Gauss 速度亏损模型配套，将偏转过程分为近尾流和远尾流两阶段。

近尾流终点：

$$
x_0 = D\frac{\cos\gamma(1+\sqrt{1-C_T\cos\gamma})}{\sqrt{2}(4\alpha I + 2\beta(1-\sqrt{1-C_T}))} + x_i
$$

近尾流偏转：

$$
\delta_{nw}(x) = \frac{x - x_i}{x_0 - x_i}\delta_0 + a_d + b_d(x - x_i)
$$

远尾流结合 $\sigma_y, \sigma_z$ 通过对数项描述偏转在下游的持续演化。优点：与 Gauss 类亏损模型耦合自然，对近-远尾流过渡表达比 Jimenez 细致。

#### 4.2.3 Empirical Gauss 偏转模型（`empirical_gauss.py`）

在高斯偏转骨架上加经验修正，便于与具体风场数据对齐。

### 4.3 湍流模型

湍流模型估算尾流附加湍流强度并反馈到尾流扩张与恢复过程：

$$
TI_{\mathrm{wake}} = f(a, TI_\infty, x/D)
$$

直观上：尾流湍流越强，混合越快，恢复也越快。

#### 4.3.1 Crespo-Hernandez（`crespo_hernandez.py`）

工程中最常见的尾流附加湍流模型之一：

$$
I_{\mathrm{add}} = C \cdot a^{p_a} \cdot I_0^{p_I} \cdot \left(\frac{\Delta x}{D}\right)^{p_x}
$$

参数形式简单，便于与速度亏损模型耦合，常作为默认基线。

#### 4.3.2 Wake-induced mixing（`wake_induced_mixing.py`）

构造尾流诱导混合强度并修正尾流扩张与恢复：

$$
M_i = \frac{a_i}{(x_i/D)^2}
$$

上游机组诱导越强、距离越近，混合修正越明显。更适用于经验高斯类模型或需要更灵活处理尾流恢复速度的场景。

#### 4.3.3 None 模型（`none.py`）

不显式计算尾流附加湍流。适合快速初筛、模型对比基线、湍流不敏感场景。**高密度布局或低环境湍流场景下不应使用**，否则会显著降低结果可信度。

#### 4.3.4 选择建议

| 场景 | 推荐 |
|------|------|
| 常规 AEP 评估或布局比选 | Crespo-Hernandez（基线） |
| 经验高斯模型下需细致描述混合 | Wake-induced mixing |
| 速度优先的初步筛选 | None（候选方案复核时恢复显式建模） |

### 4.4 叠加模型

多股尾流同时作用于同一下游风机时，需要定义总亏损的合成方式。FLORIS 提供：

- **FLS**（Freestream Linear Superposition，`fls.py`）：

$$
\Delta U_{\mathrm{tot}} = \sum_{i=1}^n \Delta U_i
$$

- **SOSFS**（Sum of Squares Freestream Superposition，`sosfs.py`）：

$$
\Delta U_{\mathrm{tot}} = \sqrt{\sum_{i=1}^n (\Delta U_i)^2}
$$

- **MAX**（`max.py`）：

$$
\Delta U_{\mathrm{tot}} = \max(\Delta U_1, \ldots, \Delta U_n)
$$

工程差异：FLS 倾向给出较大总亏损（可能高估），MAX 倾向给出较小总亏损（可能低估），SOSFS 介于两者之间且更稳健，工程应用较多。

### 4.5 尾流模型选型、组合与参数设定

FLORIS 的尾流模型由**四个独立分量**组成：**速度亏损（velocity deficit）+ 偏转（deflection）+ 湍流（turbulence）+ 叠加（combination）**。每个分量都有多个候选实现，可独立选型、自由组合。这一节讲清三件事：**怎么选分量、怎么组合、怎么设参数**；具体模型的公式细节见 §4.1–§4.4。

#### 4.5.1 四分量框架

一个完整的 FLORIS 尾流模型 = `velocity_model` + `deflection_model` + `turbulence_model` + `combination_model`。四者职责分明、物理独立：

| 分量 | 职责 | 关键输入 |
|------|------|----------|
| 速度亏损 | 尾流区风速相对自由流降低了多少，如何扩张/恢复 | $C_T$、风机间距、TI |
| 偏转 | 偏航失配后尾流中心线的横向偏移 | 偏航角 $\gamma$、$C_T$ |
| 湍流 | 尾流诱导湍流的增长 | $C_T$、风机间距、TI |
| 叠加 | 多尾流如何合成为总亏损 | 各尾流的局部速度场 |

模块化的灵活性与出错风险都在这里：换分量要确认彼此的物理兼容性（见 §4.5.6）。

#### 4.5.2 分量一：速度亏损模型选型

**可用实现**（详见 §4.1）：`jensen` / `gauss`（GCH）/ `empirical_gauss` / `cc`（Cumulative Curl）/ `turbopark` / `turboparkgauss`。

| 模型 | 横向分布 | 适用场景 | 主要代价 |
|------|---------|---------|---------|
| **Jensen** | 顶帽 | 前期筛选、教学、规则均匀布局 | 横向/偏航表达较粗 |
| **Gauss / GCH** | 高斯 | 通用 AEP 评估、偏航研究 | 参数多，对输入一致性敏感 |
| **Empirical Gauss** | 高斯（参数化重组） | 有 SCADA / LES / CFD 校准数据 | 数据不足易过拟合 |
| **Cumulative Curl** | 高斯 + 卷吸累积项 | 偏航诱导弯曲、旋转结构 | 计算重、参数多、标定要求高 |
| **TurbOPark** | 顶帽 | 超大海上风场、长距离尾流背景 | 局部小尺度尾流细节不一定最优 |
| **TurbOParkGauss** | 高斯 | TurbOPark 同 + 更高保真 | 与 Gauss 共享参数 + 标定 |

**决策规则**（按目标 → 规模 → 细节 → 数据条件递进）：

1. **看目标**：快速筛选 / 标准 AEP 评估 / 偏航控制 / 风场尺度研究 / 复杂旋转研究
2. **看规模**：场区大、关心整体尾流背景时优先 TurbOPark / TurbOParkGauss
3. **看细节需求**：关心偏航后尾流中心线迁移优先 Gauss；关心复杂旋转与卷吸再升到 Cumulative Curl
4. **看数据条件**：有实测/项目经验要吸收选 Empirical Gauss；数据不足选参数更克制的 Jensen / Gauss

**关键参数与调参建议**：

| 模型 | 主要参数 | 默认值 | 调参建议 |
|------|---------|-------|---------|
| Jensen | `we`（wake expansion coefficient） | 0.04 | 陆上 0.04–0.05；海上 0.05–0.08；不规则布局可微调 |
| Gauss / GCH | `a_s`, `b_s`, `c_s1`, `c_s2`（近尾流）+ `a_f`, `b_f`, `c_f`（远尾流） | FLORIS 默认 | **强烈建议保持默认**；自定义需 SCADA / LES 校准 |
| Empirical Gauss | 重新组织的 `alpha`, `beta` 类参数 | FLORIS 默认 | 适合有项目特定数据的微调 |
| Cumulative Curl | Gauss 全部 + 卷吸系数 | FLORIS 默认 | 任何自定义都需高质量 SCADA / LES 支撑 |
| TurbOPark | `we` + 远场恢复系数 | FLORIS 默认 | 仅在远场 AEP 与观测显著偏离时调整 |
| TurbOParkGauss | Gauss 类参数 + 远场恢复 | FLORIS 默认 | 与 Gauss 同 |

**速查原则**（呼应 §2.8.3.4）：

- 没有 SCADA 校准、LES 或 CFD 数据时，**优先保证 $C_T$ 曲线和 TI 准确**，尾流参数保持默认即可；
- 不要同时改多个分量参数——无法判断每个参数的贡献；
- 改一个分量前，先在 §4.5.8 的“工作流”中用旧值 vs 新值做对照实验。

#### 4.5.3 分量二：偏转模型选型

**可用实现**（详见 §4.2）：`jimenez` / `gauss`（高斯偏转）/ `empirical_gauss`（empirical 偏转）。

| 模型 | 公式依据 | 适用场景 |
|------|---------|---------|
| **Jimenez** | Jiménez et al. 经验式 | 与 Jensen 速度亏损配套 |
| **Gauss deflection** | Bastankhah & Porté-Agel + King et al. 混合 | 与 Gauss 速度亏损配套；偏航研究 |
| **Empirical Gauss deflection** | 经验重组 | 有偏航控制实测数据 |

**决策规则**：

- 与**速度亏损模型配套使用**是默认选择（Jensen → Jimenez、Gauss → Gauss 偏转、Empirical Gauss → Empirical Gauss 偏转）；
- **偏航控制研究**必须用 Gauss 偏转或 Empirical Gauss 偏转——Jimenez 偏转表达较粗，难以捕捉小幅偏航的 AEP 增益；
- **不偏航工况下**（所有 $\gamma_i = 0$），偏转模型不影响 AEP；可保持默认即可。

**关键参数**：

| 模型 | 主要参数 | 调参建议 |
|------|---------|---------|
| Jimenez | 经验系数（无量纲） | 保持 FLORIS 默认；非偏航工况下不敏感 |
| Gauss | 偏转增益（与速度亏损共享部分参数） | 保持默认；有 SCADA 偏航响应数据时再考虑微调 |
| Empirical Gauss | 重新组织的偏转参数 | 适合有项目特定数据；无数据保持默认 |

#### 4.5.4 分量三：湍流模型选型

**可用实现**（详见 §4.3）：`crespo_hernandez` / `wake_induced_mixing` / `none`。

| 模型 | 适用场景 |
|------|---------|
| **Crespo-Hernandez** | 通用；TI 显著影响尾流恢复时**必选** |
| **wake-induced mixing** | 与 Gauss 配套；尾流叠加研究 |
| **none** | TI 影响不敏感时的轻量场景（教学、对尾流叠加细节不敏感） |

**决策规则**：

- **TI 是尾流恢复的关键驱动**——大多数工程场景下 `crespo_hernandez` 是默认选择；
- 海上长尾流、TI 跨度大的项目：用 `crespo_hernandez`；
- 教学演示、对尾流叠加细节不敏感：用 `none` 可加速计算；
- **使用 WindTIRose**（TI 作为第三维）时，必须有湍流模型才能体现 TI 的影响——选 `crespo_hernandez` 或 `wake_induced_mixing`。

**关键参数**：

| 模型 | 主要参数 | 调参注意 |
|------|---------|---------|
| Crespo-Hernandez | `crespo_hernandez_*` 类参数 | FLORIS 默认值经过标定；Zehtabiyan-Rezaie & Abkar 指出某些参数符号与原始论文不一致——见 `CrespoHernandez` 类 docstring |
| wake-induced mixing | 混合系数 | 与 Gauss 速度亏损协同性好 |
| none | — | — |

#### 4.5.5 分量四：叠加模型选型

**可用实现**（详见 §4.4）：`fls`（freestream linear superposition）/ `max`（取大值）/ `sosfs`（平方和开方）。

| 模型 | 叠加方式 | 物理含义 | 适用场景 |
|------|---------|---------|---------|
| **FLS**（默认） | 线性叠加 | 各尾流亏损直接相加 | 通用；多数工程评估 |
| **MAX** | 取所有亏损的最大值 | 防止“线性叠加导致负速度” | 深阵列、风机数量多 |
| **SOSFS** | 平方和开方 | 比 FLS 略保守（Katic 推荐） | 历史 Katic 推荐 |

**决策规则**：

- 默认 `fls`——线性叠加在多数场景下足够；
- 风机数量 >50、深阵列、担心“线性叠加导致下游风速变负”——换 `max` 或 `sosfs`；
- 与**速度亏损模型的选择无关**——任何速度亏损模型都可以配任何叠加模型。

**关键参数**：FLS / MAX / SOSFS 通常**无用户可调参数**，内部逻辑固定。

#### 4.5.6 组合规则与兼容性

四分量原则上独立可选，但实际中有**“配套”和“避坑”**两条经验：

**常见配套组合**（推荐起点）：

| 组合 | velocity | deflection | turbulence | combination | 场景 |
|------|----------|------------|------------|-------------|------|
| 教学 / 快速筛选 | jensen | jimenez | crespo_hernandez | fls | 入门、规则均匀布局 |
| 通用 AEP 评估 | gauss | gauss | crespo_hernandez | fls | **FLORIS 默认**；推荐作为主评估 |
| 偏航控制研究 | gauss | gauss | crespo_hernandez | fls | 默认配套即可 |
| 复杂旋转 / 卷吸研究 | cc | gauss | crespo_hernandez | fls | 需要 SCADA / LES 校准 |
| 超大海上风场 | turboparkgauss | gauss | crespo_hernandez | fls 或 sosfs | 海上大场址 |
| Empirical 数据校准 | empirical_gauss | empirical_gauss | crespo_hernandez | fls | 有项目数据时 |

**避坑**：

- **不要混用不同族的偏转模型**——例如 Gauss 速度亏损 + Jimenez 偏转在数学上能跑，但偏转幅度与 Gauss 亏损的耦合关系被切断，AEP 偏差会显著；
- **不要让湍流模型与速度亏损模型相矛盾**——例如选了 `none` 湍流却要研究 TI 维度（WindTIRose）；
- **不要让叠加模型给出物理上不合理的速度**——若发现下游风速为负，**先**把 `fls` 换成 `max` 或 `sosfs`，再考虑是不是速度亏损模型本身选错了。

#### 4.5.7 参数设定总原则

| 原则 | 解释 |
|------|------|
| **默认优先** | FLORIS 默认值基于 LES 标定；在没有 SCADA / LES / CFD 校准数据时，**保持默认** |
| **不要改模型内部的固定参数** | 多数分量模型的内部参数（衰减指数、形状系数等）已固定；改它们需要重建工程经验 |
| **只改可暴露的工程参数** | `we`、偏转增益等可暴露参数；这些对应物理可解释的工程量 |
| **改一个测一个** | 每次只改一个分量参数，跑同一组风况对照；不要同时改多个 |
| **用真实数据校准** | 改任何参数前，先准备 SCADA / LES / CFD 对照基准；无对照就不要改 |
| **Cumulative Curl 必须有数据** | CC 模型的参数自由度最高，没有 SCADA / LES 支撑**强烈不建议使用** |

#### 4.5.8 典型工作流

完整的尾流模型选型与参数设定流程：

```
1. 明确目标与场景
   - 快速筛选 / 主评估 / 偏航研究 / 海上大场址 / 复杂旋转研究
   ↓
2. 默认起点
   - velocity = gauss
   - deflection = gauss
   - turbulence = crespo_hernandez
   - combination = fls
   - 所有内部参数 = FLORIS 默认
   ↓
3. 第一轮：跑一遍基线
   - 用 §3 推荐的 AEP 评估流程
   - 记录 AEP、尾流损失率、单机功率分布
   ↓
4. 第二轮：场景化调整（按需）
   - 偏航研究 → 检查 deflection 是否为 gauss
   - 海上大场址 → 试 turboparkgauss
   - 教学演示 → 试 jensen
   - 复杂旋转 → 试 cc（前提：有校准数据）
   ↓
5. 第三轮：参数校准（仅在有 SCADA / LES / CFD 时）
   - 准备基准数据
   - 一次只改一个分量
   - 对照基准，迭代到 AEP / 功率分布与观测吻合
   ↓
6. 第四轮：稳健性评估
   - 多次运行（不同风况表、不同随机种子）
   - 用 §9 UncertainFlorisModel 做参数扰动
   - 输出 AEP 区间 + 推荐尾流模型
```

**稳妥工作流**（无需 SCADA 校准时）：

- 第一轮：Jensen 或 Gauss 快速筛选；
- 第二轮：Gauss 做主评估；
- 偏航控制专题：Gauss（默认配套）；
- 超大海上风场复核：TurbOPark。

---

## 5. 布局优化

FLORIS 的布局优化模块围绕机组坐标 $(x_i, y_i)$ 这一决策变量构建，提供网格化、随机搜索与梯度三类主流方法，并支持单地块与多地块场景。本章是 §2.5 优化建模与 §2.6 标准工作流程的具体实现。

### 5.1 布局优化

目标：在场址约束下寻找更优风机坐标。决策变量是每台风机的平面位置 $(x_i, y_i)$，目标函数通常是 AEP、价值函数或附加成本/约束惩罚的综合指标：

$$
\max_{\{x_i,y_i\}} \mathrm{AEP}(\{x_i,y_i\})
$$

$$
\mathrm{s.t.}\quad (x_i, y_i) \in \Omega,\quad d_{ij} \ge d_{\min}
$$

#### 5.1.1 算法对比速查

| 算法 | 目标 | 风机数量是否可作为优化变量 | **多离散地块** | 优点 | 风险/代价 | 典型场景 |
|------|------|------|------|------|------|------|
| **Scipy Layout Optimization** | 最大化 AEP/AVP | 否（固定） | ✗ **不支持**（仅单连通区域） | 依赖简单、规则边界下收敛快 | 易陷入局部最优，复杂边界鲁棒性一般 | 中小规模、单连通场址的连续微调 |
| **Genetic Random Search** | 最大化 AEP/价值 | 否（固定） | ✓ **支持**（Point-In-Polygon 预检） | 全局搜索能力强、复杂边界鲁棒性高、并行友好 | 收敛较慢，计算轮次多 | 前期全局搜索与复杂约束筛选（含多地块） |
| **Gridded Layout Optimization** | 最大化可布机数量 | **是**（可变） | ✓ **支持**（Point-In-Polygon 检测） | 速度快、纯几何、可快速给出初始布局 | 不直接优化 AEP/价值 | 最早期容量摸底与初始布局生成（含多地块） |
| **PyOptSparse Layout Optimization** | 最大化 AEP/价值 | 否（固定） | ✗ **不支持**（与 SciPy 相同：单连通区域） | 可接入工业级求解器（SNOPT, IPOPT） | 环境配置复杂，部分求解器需许可 | 大规模、单连通工程与严苛约束优化 |

#### 5.1.2 风电场数量与布局的关系

风电场净 AEP 与风机数量之间并非单调递增：

- **初期**：增加风机数量带来发电量增长（收益递增）；
- **中期**：尾流损失上升，发电量增长变缓（收益递减）；
- **后期**：过多风机导致尾流严重，单机发电量大幅下降。

`LayoutOptimizationGridded` 通过环形距离约束（通常 2–4 倍转子直径）保证风机间距，从几何上找出可容纳风机数量的最大值；但**单纯从发电量看，放置越多并不必然带来越多 AEP**。

工程上存在最优的风机数量和排位使总发电量最大，但**也存在一个理论最优的 LCOE 解**（综合 CapEx、OpEx 与发电量）。FLORIS 核心版本主要支持发电量最大化，要支持 LCOE 优化需：

- 自定义目标函数，结合 CapEx、OpEx、AEP 计算 LCOE；
- 扩展优化器模块，集成经济模型。

#### 5.1.3 Scipy 布局优化方法

FLORIS `LayoutOptimizationScipy` 类默认使用 SLSQP。

**关键技术细节**：

1. **坐标归一化**：将风机坐标从物理空间 $[x_{\min}, x_{\max}]\times[y_{\min}, y_{\max}]$ 映射到 $[0,1]^2$，消除量纲影响；
2. **KS 函数聚合间距约束**：传统方法需 $N(N-1)/2$ 个约束，FLORIS 采用 Kreisselmeier-Steinhauser 函数聚合为单一平滑约束：

$$
g_{\mathrm{KS}}(x) = \frac{1}{\rho}\ln\left[\sum_{i<j}\exp(\rho\cdot g_{ij}(x))\right] \le 0
$$

$$
g_{ij}(x) = 1 - \frac{\|x_i - x_j\|}{d_{\min}}
$$

3. **几何偏航耦合**：`enable_geometric_yaw=True` 时在每次布局评估中自动计算最优偏航角，典型额外增益 1–3% AEP；
4. **梯度近似**：有限差分法近似梯度，对每个变量施加微小扰动 $\varepsilon$（默认 0.01）。

**求解器选择**：

| 求解器 | 适用场景 | 优势 | 劣势 |
|--------|---------|------|------|
| SLSQP（默认） | 通用带约束 | 平衡速度与精度 | 高维问题可能收敛慢 |
| trust-constr | 复杂约束、高精度 | 约束处理稳健 | 计算成本高，内存占用大 |
| L-BFGS-B | 仅边界约束 | 高效处理大规模 | 不支持不等式约束 |
| COBYLA | 无梯度可用 | 无需梯度 | 收敛慢，精度低 |

**推荐配置**：

- 中小规模（<30 台）：SLSQP，maxiter=100–150，ftol=1e-9，eps=0.01；
- 中等规模（30–60 台）：trust-constr，maxiter=200–300；
- 大规模（>60 台）：先全局预搜索，再用 L-BFGS-B 精化。

**优势**：收敛快、约束处理严谨、SciPy 成熟可靠、易集成。  
**局限**：易陷入局部最优、初始解敏感、**仅支持单连通区域**（不支持多个分离地块的"飞地"布局；FLORIS 在调用 `LayoutOptimizationScipy` 时若检测到 `boundaries` 含多个多边形，会通过 `_select_boundary_for_scipy` **静默退化为最大单地块**）。

#### 5.1.4 遗传随机搜索方法

`LayoutOptimizationRandomSearch` 采用"扰动-评估-接受"机制：

1. **种群维护**：同时维护 $n_{\mathrm{ind}}$ 个独立布局候选；
2. **随机扰动**：每代对每个个体随机选一台风机，施加随机方向和距离的位移；
3. **约束预检**：快速检查新位置是否满足边界和间距（不调用尾流模型）；
4. **目标评估**：若约束满足，计算新布局 AEP；
5. **贪婪接受**：若新 AEP 更高则接受；否则拒绝；
6. **并行演化**：所有个体独立演化，定期交换最优解信息（岛模型）。

**距离 PMF 调优**：

| 档位 | 距离范围 | 推荐概率 | 作用 |
|------|---------|---------|------|
| 小步长 | 0.5–1.0 D | 0.30–0.60 | 局部精细调整 |
| 中步长 | 2.0–5.0 D | 0.20–0.30 | 跳出局部最优 |
| 大步长 | 5.0–10.0 D | 0.05–0.20 | 全局探索 |

典型配置：

```python
distance_pmf = {
    "d": [0.5, 1.0, 2.0, 5.0, 10.0],   # 距离档位（单位 D）
    "p": [0.30, 0.30, 0.20, 0.15, 0.05]  # 对应概率
}
```

**关键参数**：

| 参数 | 推荐 | 说明 |
|------|------|------|
| `seconds_per_iteration` | 30–120 s | 每代时间预算 |
| `n_individuals` | 4–16 | 种群规模，约等于 CPU 核心数 |
| `min_dist` | 5D（推荐起始） | 最小间距（陆上 2D–3D，海上 5D–7D） |
| `enable_geometric_yaw` | True（最终阶段） | 1–3% AEP 增益，评估成本增 20–50% |
| `use_value` | False/True | 最大化 AEP 或 AVP |
| `random_seed` | 固定值 | 调试对比时确保可重复 |

**优势**：全局搜索强、并行性好、对初始解不敏感、约束处理灵活、时间可控。  
**局限**：收敛较慢、计算成本高、参数需调优、解的质量波动、缺乏理论保证。

#### 5.1.5 协同使用（强烈推荐）

```
阶段 1：全局搜索（随机搜索）
  方法：LayoutOptimizationRandomSearch
  时间预算：1800–3600 秒
  输出：layout_global

阶段 2：局部精化（SciPy）
  方法：LayoutOptimizationScipy
  初始解：layout_global
  迭代次数：50–100
  输出：layout_final
```

相比单一方法，预期改进：

- 比单用随机搜索：最终解质量 +2–5%；
- 比单用 SciPy：避免陷入劣质局部最优。

多起点策略：使用不同 `random_seed` 多次运行取最优，再进入精化阶段。

#### 5.1.6 复杂边界与多地块支持

FLORIS 的 `boundaries` 参数接受两类输入：

- **单地块**：`[(x, y), ...]`，一个多边形顶点列表；
- **多地块**（多个离散的封闭区域）：`[[(x, y), ...], [(x, y), ...]]`，嵌套的多边形列表。

各算法对多地块的支持差异显著：

| 算法 | 多离散地块支持 | 实现机制 |
|------|------|------|
| **Gridded Layout Optimization** | ✓ 支持 | `LayoutOptimizationGridded` 直接对整个 `boundaries` 列表做 `Point-In-Polygon` 检测，把风机放置在合法地块内 |
| **Genetic Random Search** | ✓ 支持 | `LayoutOptimizationRandomSearch` 在每次扰动后用 `Point-In-Polygon` 预检候选位置是否落在任一合法地块内 |
| **Scipy Layout Optimization** | ✗ **不支持** | `LayoutOptimizationScipy` 内部把整个 `boundaries` 当作单一多边形处理。**FLORIS 在调用前会通过 `_select_boundary_for_scipy` 静默退化为 `boundaries` 中面积最大的单地块**（如果原始输入是多地块），其余地块会被忽略 |
| **PyOptSparse Layout Optimization** | ✗ **不支持** | 与 SciPy 同属连续优化框架，限制相同 |

**工程含义**：

- 候选布局生成阶段（含多地块场景）：**必须使用 Gridded 或 Random Search**；
- 精化阶段如果原始边界是多地块：要么**先在合并后的单地块上做 SciPy 精化**（会失去对其他地块的优化），要么**用 Random Search 一并完成精化**；
- 多地块场景下，**不要把多地块直接交给 SciPy** —— 你可能误以为它在优化所有地块，实际它只优化了面积最大的那个。建议在调用 `LayoutOptimizationScipy` 前显式检查 `_select_boundary_for_scipy` 的退化行为。

**最佳实践**：多地块场景下采用"Random Search 单独完成全局搜索 + 局部精化"或"Gridded 单独完成初始布局"的策略，**不要在精化阶段串联 SciPy**，除非先用其他方法把结果约束到单地块上。

#### 5.1.7 优化结果评价

**发电量提升**：

- AEP 提升率：$\eta_{\mathrm{AEP}} = (AEP_{\mathrm{opt}} - AEP_{\mathrm{base}}) / AEP_{\mathrm{base}} \times 100\%$
  - 布局优化典型提升：5–20%（取决于初始布局质量）；
  - <3% 可能初始布局已较优或未充分收敛；
  - \>25% 需检查约束违反。
- 尾流损失降低：$\text{尾流损失率} = 1 - AEP_{\mathrm{actual}} / AEP_{\mathrm{no\_wake}}$，典型降低 3–10 个百分点。

**约束满足性**：边界包含性、最小间距、禁建区避让、偏航角范围。

**工程可实施性**：电缆长度估算、道路可达性、地形适应性、环境影响。

**收敛性诊断**：AEP 迭代曲线、多次运行一致性（标准差 <2% 表明稳健，>5% 表明多峰性强）。

#### 5.1.8 实战配置模板

以下 Python 模板展示"Random Search 全局搜索 + SciPy 局部精化"的标准两阶段流程，可作为工程项目的起点：

```python
import time
import numpy as np
from floris import FlorisModel
from floris.optimization.layout_optimization.layout_optimization_random_search import (
    LayoutOptimizationRandomSearch,
)
from floris.optimization.layout_optimization.layout_optimization_scipy import (
    LayoutOptimizationScipy,
)

fmodel = FlorisModel("gch.yaml")
fmodel.set(
    wind_directions=np.arange(0, 360, 5),      # 5° 步长，72 扇区
    wind_speeds=[6, 8, 10, 12],
    turbulence_intensities=0.06,
)

D = fmodel.core.farm.rotor_diameters_flat[0]
boundaries = [...]                            # 单地块或多地块

# 阶段 1：Random Search 全局搜索
t0 = time.time()
opt_rs = LayoutOptimizationRandomSearch(
    fmodel, boundaries,
    min_dist=5 * D,
    seconds_per_iteration=60,
    total_optimization_seconds=1800,          # 30 分钟
    n_individuals=8,
    random_seed=42,
    enable_geometric_yaw=True,                 # 隐含偏航优化
)
layout_global, _ = opt_rs.optimize()
print(f"Random search: {time.time()-t0:.1f}s, AEP={fmodel.get_farm_AEP()/1e6:.2f} GWh")

# 阶段 2：SciPy 精化（仅单地块；多地块跳过此步）
if isinstance(boundaries[0][0], (list, tuple)):   # 多地块检测
    print("SciPy 不支持多地块，跳过精化")
    layout_final = layout_global
else:
    opt_scipy = LayoutOptimizationScipy(
        fmodel, boundaries,
        min_dist=5 * D,
        solver="SLSQP",
        optOptions={"maxiter": 150, "ftol": 1e-9},
        enable_geometric_yaw=True,
    )
    layout_final, _ = opt_scipy.optimize()
    print(f"SciPy refine: {time.time()-t0:.1f}s, AEP={fmodel.get_farm_AEP()/1e6:.2f} GWh")
```

**模板要点**：
- `enable_geometric_yaw=True` 让布局优化中自动考虑偏航，无需独立运行偏航优化；
- 多地块自动检测并跳过 SciPy 精化（避免 SciPy 静默退化为最大单地块）；
- `random_seed=42` 保证结果可重复，对比实验时使用不同种子评估稳健性。

### 5.2 布局优化实战指南

针对**布局优化**这一核心任务的工程实施清单：

**1. 准备阶段**
- 明确场址边界、禁建区、最小间距（推荐起始 5D）；
- 选择合适的尾流模型（快速筛选用 Jensen，主评估用 Gauss）；
- 配置风况数据（建议 36 风向扇区 + 1 m/s 风速分箱）；
- 准备好几个不同 `random_seed` 用于稳健性评估。

**2. 全局搜索阶段（Random Search）**
- 时间预算：投标初筛 30 分钟 / 深化 1 小时 / 最终设计 2 小时以上；
- 种群规模 = CPU 核心数 - 1；
- 距离 PMF 起始用 `[0.5, 1.0, 2.0, 5.0, 10.0] × [0.30, 0.30, 0.20, 0.15, 0.05]`；
- **多地块场景必须用 Random Search**（其他方法不支持）；
- 启用 `enable_geometric_yaw=True` 隐含考虑偏航控制。

**3. 精化阶段（SciPy）**
- 仅适用于**单地块**场景；
- 用 Random Search 的输出作为初始解；
- 求解器：SLSQP（maxiter 100–200）或 trust-constr；
- 启用 `enable_geometric_yaw=True` 进一步挖掘潜力；
- **多地块场景跳过 SciPy 精化**（避免 SciPy 静默退化为最大单地块）。

**4. 校核阶段**
- 用更细的风况表（如 5° 风向扇区）和更精细的尾流模型（Cumulative Gauss Curl）重新计算；
- 对照 SCADA 实测（若可用）；
- 多次运行不同 `random_seed` 评估稳健性（标准差 <2% 表明稳健，>5% 需增加运行次数）。

**5. 集成阶段**
- 估算电缆长度、道路可达性等工程约束影响；
- 与运维、电网、土建团队对接；
- 输出最终推荐方案 + 不确定性区间（结合 `UncertainFlorisModel`）。

**核心原则**：不会把"某个工况下的最优"误认为"工程上最优"。

---

## 6. 风机模型

### 6.1 模型组成

风机模型连接了流场计算与发电量计算两个核心环节，包含三大类参数：

**几何参数**：

- **轮毂高度 $z_h$**（m）：决定风切变修正的参考高度；
- **转子直径 $D$**（m）：决定扫掠面积 $A = \pi D^2/4$，直接影响风能捕获能力；
- **叶尖速比 TSR**（无量纲）：叶片叶尖线速度与来流风速之比，部分尾流模型中用于尾流扩展计算。

**性能参数**：

- **功率曲线**：以查找表存储 $U \to P$ 映射；
- **推力系数曲线**：$C_T = T / (0.5\rho A U^2)$；
- **参考空气密度 $\rho_{\mathrm{ref}}$**：典型 1.225 kg/m³；
- **参考倾角 $\theta_{\mathrm{ref}}$**：固定式风机通常 5°，浮动式可能随风速变化。

**控制参数**（依赖操作模型）：

- 偏航损失指数 `cosine_loss_exponent_yaw`（典型 1.88）；
- 倾角损失指数 `cosine_loss_exponent_tilt`（典型 1.88）；
- 切入/切出风速、额定功率、额定风速（自动从功率曲线提取）。

**高级模型参数**（可选）：

- **多维 Cp/Ct 表**：与 TI、波高、波周期等耦合的性能面；
- **浮动倾角表**：浮动式风机的 $U$–$\theta$ 查找表；
- **控制器依赖参数**：额定转速、转子实度、发电机效率、桨距角-TSR-Cp/Ct 曲面。

### 6.2 内置参考机型

FLORIS 内置三种参考风机模型：

| 机型 | 轮毂高度 | 转子直径 | 额定功率 | 适用场景 |
|------|---------|---------|---------|---------|
| NREL 5MW | 90 m | 125.88 m | 5 MW | 陆上/浅水参考 |
| IEA 10MW | ~100 m | 180–200 m | 10 MW | 海上参考 |
| IEA 15MW | 150 m | 242.24 m | 15 MW | 大型海上 |

```python
from floris import FlorisModel
fmodel = FlorisModel("defaults")              # 默认 NREL 5MW
fmodel.set(turbine_type=["iea_15MW"])         # 切换 IEA 15MW
```

### 6.3 操作模型

操作模型决定风机如何响应控制指令。FLORIS 支持：

| 模型 | 类别 | 特点 | 适用场景 |
|------|------|------|---------|
| `simple` | SimpleTurbine | 不考虑偏航或倾角，直接查表 | 基准分析、无控制策略 |
| `cosine-loss`（默认） | CosineLossTurbine | 偏航和倾角的余弦幂律修正 | 偏航控制、浮动式分析 |
| `simple-derating` | SimpleDeratingTurbine | 支持功率设定点 | 降额运行、电网调度 |
| `mixed` | MixedOperationTurbine | 同时支持偏航和降额 | 混合控制策略 |
| `AWC` | AWCTurbine | 螺旋形主动尾流混合 | 主动尾流混合研究 |
| `peak-shaving` | PeakShavingTurbine | 高 TI 时降低 $C_T$ | 高湍流下载荷优化 |
| `controller-dependent` | ControllerDependentTurbine | 基于 Cp/Ct 三维曲面 | 高精度仿真、控制器验证 |
| `unified-momentum` | UnifiedMomentumModelTurbine | 基于统一动量理论 | 理论研究、模型对比 |

余弦损失模型的核心修正：

$$
P = P_0 \cdot (\cos\gamma)^{p_\gamma} \cdot \left(\frac{\cos\theta}{\cos\theta_{\mathrm{ref}}}\right)^{p_\theta}
$$

$$
C_T = C_{T0} \cdot \cos\gamma \cdot \frac{\cos\theta}{\cos\theta_{\mathrm{ref}}}
$$

### 6.4 空气密度修正

当实际密度 $\rho$ 与参考密度 $\rho_{\mathrm{ref}}$ 不同时，对有效风速进行立方根修正：

$$
U_{\mathrm{eff}} = U \cdot \left(\frac{\rho}{\rho_{\mathrm{ref}}}\right)^{1/3}
$$

密度受海拔（每升 1000 m 下降约 12%）、温度（每升 10°C 下降 3–4%）影响。典型范围 1.1–1.3 kg/m³。

### 6.5 转子面平均风速

受尾流影响时，转子扫掠面上风速分布不均匀。FLORIS 支持多种平均方法：

- **立方平均**（默认）：$U_{\mathrm{rotor}} = \left(\frac{1}{A}\int_A U^3 dA\right)^{1/3}$，与功率三次方关系最一致；
- **算术平均**：$U_{\mathrm{rotor}} = \frac{1}{A}\int_A U\,dA$；
- **最大值** / **最小值**：取转子面上的极值。

强尾流或复杂地形下，平均方法选择对结果有显著影响。

### 6.6 多机型混排

```python
# 三台风机的风场，前两台 NREL 5MW，第三台 IEA 15MW
fmodel.set(
    layout_x=[0, 500, 1000],
    layout_y=[0, 0, 0],
    turbine_type=["nrel_5MW", "nrel_5MW", "iea_15MW"]
)
```

FLORIS 自动处理不同机型的几何尺寸、性能曲线和控制参数差异，并在尾流计算中考虑各机型的推力特性。

### 6.7 机组选型对 AEP 的影响

**关键参数机理**：

1. **转子直径 $D$**：功率与 $D^2$ 成正比。增大 $D$ 提高低风速区功率输出，但扩大尾流影响范围。密集布局下过大的 $D$ 可能使尾流损失抵消单机增益。
2. **轮毂高度 $z_h$**：根据幂律 $U(z) = U_{\mathrm{ref}}(z/z_{\mathrm{ref}})^\alpha$，每升 10 m 风速约增 1–3%。高轮毂降低地面粗糙度和湍流影响，但增加塔筒成本和结构载荷。
3. **额定功率 $P_{\mathrm{rated}}$**：决定装机容量和投资规模。与 $D$ 匹配关系影响比功率（specific rating）。
4. **推力系数特性**：高 $C_T$ 增强尾流速度亏损、降低下游功率；低 $C_T$ 减弱尾流影响。额定风速以上常用降推力策略。
5. **控制策略兼容性**：支持偏航/降额的风机可获额外 2–5% 风场级 AEP 提升。

**选型建议**：投标阶段应对不同候选风场选择 2–3 种代表性机型进行对比，指标包括：AEP 和净发电量、尾流损失率、容量因子、单机发电量分布均匀性、单位千瓦投资年发电量。

---

## 7. 风况模型

### 7.1 概述

风况描述是 AEP 计算的统计基础，主要包括风速分布、风向分布、风速-风向联合频率分布以及湍流强度、风切变、风向随高度变化等参数。

工程上风况离散化的权衡：

- 风向扇区划分越细，越有利于描述尾流路径变化；
- 风速分箱越细，越有利于反映功率曲线陡变区间的输出差异；
- 计算成本随离散化精度上升。

常用方案：

- **示例 A**（经济型）：8 个风向扇区（22.5°）、1 m/s 风速分箱，约 8×8 个工况；
- **示例 B**（精细型）：36 个风向扇区（10°）、分段风速分箱，约 36×10–20 个工况。

### 7.2 TimeSeries

按时间顺序记录的逐时间步长（通常 1 小时）风能观测数据，每条记录包含风向、风速、湍流强度等。TimeSeries 保留全部时间序列信息，可与 WindRose 或 WindTIRose 相互转换。

```python
风向 = [350, 355, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45]
风速 = [6.2, 5.8, 6.0, 6.5, 7.0, 7.2, 6.9, 6.8, 6.5, 6.3, 6.1, 5.9]
TI   = [0.07] * 12
```

#### 7.2.1 逐小时 AEP 的空间差异能力边界

FLORIS 的 `TimeSeries` 表达的是一组逐时工况。对每一个时间步，FLORIS 假设整个风场共享同一个自由来流风向 `wind_direction`、一个参考风速 `wind_speed` 和一组湍流强度输入。它不支持在同一个时间步内为每台风机传入彼此独立的 `TimeSeries`，也不支持"风机 A 风向 260°、风机 B 风向 275°、风机 C 风向 290°"这样的每机位不同风向计算。

原因在于 FLORIS 的尾流坐标变换、风场旋转和 wake 传播方向都是按每个 wind condition 的单一风向建立的。它是稳态工程尾流模型，不是空间连续矢量风场求解器。

FLORIS 能可靠表达的是**每个时间步全场共享风向，但每台风机位置有不同风速**。工程上通常用 `TimeSeries + heterogeneous_inflow_config.speed_multipliers` 实现：

$$
U_m(t) = U_{\mathrm{ref}}(t) \cdot M_m(t)
$$

其中 $U_{\mathrm{ref}}(t)$ 是该小时的全场参考风速，$M_m(t)$ 是风机 $m$ 在该小时的速度乘数。若外部地形模型给出了每台风机的逐小时风速序列，可以把每小时所有风机风速的平均值作为 $U_{\mathrm{ref}}(t)$，再令：

$$
M_m(t) = \frac{U_m(t)}{U_{\mathrm{ref}}(t)}
$$

这样在每个风机点上，FLORIS 看到的自由来流风速仍等于外部模型给出的逐小时风速。若某小时所有机位平均风速为 0，则乘数可统一设为 1，该小时功率自然为 0。

工程结论：

- 支持：逐小时全场共享风向 / TI，每台风机不同风速；
- 不支持：同一小时每台风机不同风向；
- 谨慎处理：同一小时每台风机不同 TI，目前不应作为标准 FLORIS 契约承诺；
- 若外部地形模型输出了每机位风向，应先形成全场代表风向，例如风速加权平均、容量加权平均或场址中心点风向，再把风速空间差异作为 speed multipliers 输入。

### 7.3 WindRose

极坐标形式展示不同风向上的风速频率分布，主要参数：

- `ti_table`：可为常数或矩阵；
- `freq_table`：需与 wd/ws 形状匹配，且 sum=1；
- `value_table`（可选）：按价差加权能量价值；
- 方法 `downsample` / `upsample` / `resample_by_interpolation` 便于在不同精度间切换。

```python
风速 = [6, 7, 8, 9]
风向 = [260, 265, 270, 275, 280, 285, 290]
频率表 = [[...]]  # 形状 (7, 4)，sum=1
```

### 7.4 WindTIRose（TI 作为第三维）

将 TI 升级为独立维度的三维风玫瑰。适用条件：

- 尾流恢复对 TI 变化敏感；
- 风资源数据已明确将 TI 作为第三维统计；
- 优化控制策略评估（偏航等控制增益受 TI 影响）；
- 复杂山地或海上场景（局地 TI 分布差异大）。

**价值**：提高 AEP 估计精度、支持分维离散与情景分析、改善布局与机组选型鲁棒性、强化不确定性与风险分析、便于模型标定与观测对比。

### 7.5 WindRoseWRG（网格化/分区化风玫瑰）

对 WindRose 的工程化扩展，支持场内不同测点/分区/网格单元的独立风玫瑰，可按面积或装机容量加权合成总体频率。包含箱内统计与不确定性表征（样本数、均值、方差），便于识别小样本箱。

### 7.6 数据转换（TimeSeries → WindRose / WindTIRose）

**转换到 WindRose（wd × ws）**：

1. 确定离散化方案（风向扇区、风速箱边界、箱代表值规则）；
2. 对每条时序记录分箱（注意圆周平均与 0°/360° 连续性）；
3. 统计每个 $(wd, ws)$ 箱的记录数，除以总有效小时数得到 `freq_table`（sum=1）；
4. 计算代表风速（推荐能量加权平均或中位数）和代表 TI（条件均值）；
5. QC 检查：$\sum f = 1$、箱内代表值与原始时序偏差在可接受范围。

**转换到 WindTIRose（wd × ws × TI）**：

1. 在 wd × ws 基础上确定 TI 分档（低/中/高三档或基于经验物理阈值）；
2. 对每条时序记录同时分配 TI 档位；
3. 统计并归一化得三维 `freq_table`（sum=1）；
4. 代表 TI 取档位中心或箱内均值。

### 7.7 风况建模质量检查清单

- $\sum f = 1$（联合频率归一化）；
- 代表 TI 在物理合理区间（海上 0.04–0.12，复杂地形可更高）；
- 箱内代表风速与时序年均风速差异 < 1%；
- 关键工况（高频或高能量区）已做时序回放验证；
- 敏感性分析已记录并明确不确定性范围。

---

## 8. 复杂地形与异质来流

### 8.1 概述

FLORIS 不是复杂地形流动求解器。其处理复杂地形的工程做法是：

1. 由外部高保真工具（CFD、WRF、WAsP 等）求解空间非均匀来流场；
2. 归一化为速度乘数场（Speed Multiplier）；
3. 在 FLORIS 中以 `HeterogeneousMap` 形式注入；
4. FLORIS 在该非均匀背景上继续计算机组间尾流相互作用。

```
DEM / 地形
    ↓
CFD / WRF / WAsP
    ↓
空间风场（WS / WD / TI / Shear / Veer 空间分布）
    ↓
HeterogeneousMap
    ↓
FLORIS 尾流与 AEP 计算
```

复杂地形对尾流建模的影响：

| 影响 | FLORIS 处理方式 |
|------|------|
| 风速空间变化 | 通过 HeterogeneousMap 显式建模 |
| 风向空间变化 | **不原生支持同一工况内每机位不同风向**；需外部折算为全场代表风向 |
| TI 空间变化 | 不建议作为标准输入契约；通常使用全场共享 TI 或按工况统计成 WindTIRose |
| Shear 空间变化 | 可做外部预处理或分情景计算；不等同于每机位独立时序 |
| Veer 空间变化 | 可做外部预处理或分情景计算；不等同于每机位独立风向 |
| 尾流上抬、下沉、弯曲 | **不显式建模**（仍采用平坦地形工程模型） |
| 山后分离流 | **不显式建模** |
| 地形诱导尾流恢复 | **不显式建模** |

**重要经验法则**：在复杂地形下，**地形加速效应（Speed-up）通常比尾流损失更重要**。山地风场中：

- 地形增益：10–30%；
- 尾流损失：5–10%。

因此忽略了地形加速会严重低估 AEP；只关注尾流而忽略地形是常见的工程误区。

### 8.2 HeterogeneousMap 工作机制

**速度乘数定义**：

$$
M(x, y, z) = \frac{U_{\mathrm{local}}(x, y, z)}{U_{\mathrm{reference}}}
$$

**生成方法**：

- **CFD 模拟**：空域模拟（不放置风机）→ 设定基准（入口风速或虚拟测风塔）→ 逐点归一化；
- **中尺度气象模型（WRF）**：提取风场范围各点平均风速，除以参考点风速；
- **观测数据插值**：稀疏测点的空间插值（IDW/最近邻/线性），通常用作校验；
- **解析模型或经验公式**：海岸线效应、幂律/对数律高度切变调整。

**空间修正机制**：

$$
U_\infty(x, y, z) = U_{\mathrm{ref}} \cdot M(x, y, z; \text{wd}, \text{ws})
$$

然后叠加尾流亏损：

$$
U(x, y, z) = U_\infty(x, y, z) - \Delta U_{\mathrm{wake}}(x, y, z)
$$

### 8.3 HeterogeneousMap 与 WindRose 的分工

两者不是替代关系，而是互补：

| 维度 | HeterogeneousMap | WindRose / WRF 统计 |
|------|------|------|
| 空间精细度 | **强**（百米级甚至十米级） | 弱（1–3 km WRF 网格） |
| 时间统计代表性 | 弱（针对特定风向和稳定度的"快照"） | **强**（1–10 年长期数据） |
| 物理过程精度 | 强（CFD 含非线性流体力学方程） | 弱（仅概率分布，无流体机理） |
| AEP 加权 | 不直接适用 | **必需** |

**工程结论**：在 FLORIS 框架内，HeterogeneousMap 是提升"空间逼真度"的上限，但必须配合 WindRose 使用，才能具备时间上的意义。

**工业界最佳实践**：

1. WRF/WindRose 提供长期宏观统计；
2. CFD/WAsP 为 WindRose 主要风向扇区各生成一张 HeterogeneousMap；
3. FLORIS 按风向扇区调用对应地图；
4. 对多工况功率做频率加权。

### 8.4 异质地图生成方法选型

| 项目类型 | 优先方法 | 理由 |
|------|------|------|
| 普通陆上 | WAsP / 线性化模型 | 性价比高、部署快，生成的 Speed Multiplier 精度满足工程要求 |
| 复杂山地 | CFD | 解决非线性问题（分离、回流、强湍流），"一次性投资"长期复用 |
| 大型海上 | WRF / 中尺度结果 | 捕捉外海到近海风速梯度或海陆风效应 |
| 测风塔/Lidar 插值 | 不建议单独使用 | 实测点太稀疏，插值误差大；更适合作为校验和偏差修正 |

**选型建议**：

- 普通陆上项目：WAsP/线性化模型（行业标准）；
- 复杂山地项目：CFD（前期成本高但可靠性高）；
- 大型海上项目：WRF；
- 测风塔/Lidar：仅作校验。

### 8.5 HeterogeneousMap 的失效逻辑

FLORIS 是稳态模型，HeterogeneousMap 没有固定"保质期"，其"失效"由环境物理条件变化触发：

**1. 尺度有效性（10 分钟平均）**

输出数值在 10 分钟到 1 小时平均意义上有效，秒级动态响应分析不适用。

**2. 气象条件有效性（核心限制）**

- **风向**：地形加速/减速效应与风向高度相关。实际风向超出构建阈值时失效。常见工程阈值 ±2.5° 到 ±5°；
- **大气稳定度**：白天不稳定（对流强）与夜晚稳定（分层明显）的风速分布截然不同，跨稳定度使用即失效。

**3. 季节与环境长期失效**

- 地表粗糙度变化（森林落叶、大雪、农作物生长/收割）；
- 周边构筑物变化（新建风电场、砍伐森林等改变上游入流）。

**4. 外推失效**

HeterogeneousMap 基于线性缩放假设。在极高风速（接近切出）或极低风速时，非线性流场可能产生较大偏差。

**失效总结**：

- 风向偏差超 ±2.5°–±5°；
- 大气稳定度切换（晨昏转换）；
- 统计窗口失配（10 分钟平均数据用于秒级分析）；
- 长期环境变化；
- 风速外推至极端区间。

### 8.6 参考风速的获取与绑定

**构建映射表时**：

- CFD 入口边界值；
- 虚拟测风塔点（受地形干扰最小的代表性位置）；
- 区域平均值（较少用，物理意义弱）。

**FLORIS 仿真时**：

- 测风塔实测（最标准）；
- 上游自由流机组 SCADA 反推；
- 中尺度 NWP（如 WRF）预报值；
- Weibull 分布的 AEP 分箱风速。

**绑定原则**：HeterogeneousMap 的参考点坐标必须和参考风速测量点对应，否则会引入系统偏差。**工程建议**：在项目配置中显式记录参考点坐标、参考风速来源、风向扇区与地图版本号，确保可追溯。

### 8.7 FLORIS 中地形因素的工程实现

#### 8.7.1 风切变

$$
U(z) = U_{\mathrm{ref}}\left(\frac{z}{z_{\mathrm{ref}}}\right)^\alpha
$$

- $\alpha$ 平坦开阔地形约 0.10–0.15；复杂地形或高粗糙度 0.20–0.40。

#### 8.7.2 风向扭转

$$
\theta(z) = \theta_{\mathrm{ref}} + \beta(z - z_{\mathrm{ref}})
$$

- $\beta$ 典型 0–0.01°/m。
- Wind Veer 属于 `FlowField` 输入参数，**不是布局优化变量**。

#### 8.7.3 异质 inflow 实现

```python
import numpy as np
from floris import FlorisModel, HeterogeneousMap, TimeSeries

# 准备速度乘数
x_pts = np.array([0, 500, 1000, 0, 500, 1000])
y_pts = np.array([0, 0, 0, 500, 500, 500])
z_pts = np.array([90, 90, 90, 90, 90, 90])
u_local = np.array([7.5, 8.2, 8.5, 7.8, 8.0, 8.3])
u_ref = 8.0
speed_mult = u_local / u_ref

het_map = HeterogeneousMap(
    x=x_pts, y=y_pts, z=z_pts,
    speed_multipliers=speed_mult.reshape(1, -1),
    wind_directions=np.array([270.0]),
    wind_speeds=np.array([8.0])
)

# 应用
time_series = TimeSeries(
    wind_directions=[260, 270, 280],
    wind_speeds=[7.0, 8.0, 9.0],
    turbulence_intensities=0.06,
    heterogeneous_map=het_map
)

fmodel.set(wind_data=time_series)
fmodel.run()
powers = fmodel.get_turbine_powers()
```

**注意（防 WAsP/线性 FLORIS 警告）**：FLORIS 4.x 的 flow-field 网格会向布局边界外延伸数百米到几公里（覆盖远尾流区），如果 HeterogeneousMap 的 `x`/`y` 包络不够大，FLORIS 会用 freestream 填补超出的点（multiplier=1），并发出 `The calculated flow field contains points outside of the user-defined heterogeneous inflow bounds` 警告。

本仓库曾有基于粗糙度栅格生成异质地图的 CLI 辅助模块，现已删除。因此这里不再给出
本地 `floris.heterogeneous` 调用示例；直接使用上游 `HeterogeneousMap` 时，应按所用
FLORIS 版本检查地图包络和外推行为。

复杂地形导致的 AEP 变化可达 ±5–10%，平坦地形通常 < ±2%。

### 8.8 多维气象条件

当需要同时考虑多个气象变量（TI、空气密度、稳定度）时，使用 `multidim_conditions`：

```python
from floris import WindRose
import numpy as np

wind_directions = np.array([250, 260, 270, 280, 290])
wind_speeds = np.array([6, 7, 8, 9, 10, 11, 12])
turbulence_intensities = np.array([0.05, 0.08, 0.12])

freq_table = np.random.rand(5, 7, 3)
freq_table = freq_table / freq_table.sum()  # 归一化

wind_rose_ti = WindRose(
    wind_directions=wind_directions,
    wind_speeds=wind_speeds,
    turbulence_intensities=turbulence_intensities,
    freq_table=freq_table,
    ti_table=None,
    value_table=None
)

# 为不同 TI 档位指定不同空气密度
air_density_by_ti = {0.05: 1.25, 0.08: 1.225, 0.12: 1.20}
wd_u, ws_u, ti_u, freq_u, _, _ = wind_rose_ti.unpack()
air_density_array = np.array([air_density_by_ti[ti] for ti in ti_u])

fmodel.set(
    wind_data=wind_rose_ti,
    multidim_conditions={"air_density": air_density_array}
)
fmodel.run()
aep = fmodel.get_farm_AEP()
```

### 8.9 不同地形类型的实践建议

**平坦地形风场**：

- 标准风切变模型 $\alpha = 0.10$–$0.15$；
- 忽略风向扭转 $\beta = 0$；
- 单一空气密度值（1.225 kg/m³ 或场址长期平均）；
- 单一或分段 TI 常数；
- 无需异质 inflow 映射。

**复杂山地风场**：

- 优先 CFD 或 WRF 三维异质映射；
- 数据不足时按坡向/坡度分区设置不同 $\alpha$；
- 考虑风向依赖（迎风坡加速、背风坡分离）；
- TI 随地形变化大，建议用 `WindTIRose`；
- 空气密度按机位高程修正。

**海上风场**：

- 风切变指数较低（$\alpha \approx 0.08$–$0.12$）；
- TI 整体偏低（0.04–0.08），但存在波浪诱导湍流；
- 空气密度受温湿度影响小，可采用常数；
- 大型风场（>50 km）需考虑科里奥利力导致的风向扭转。

---

## 9. 不确定性量化与稳健性分析

### 9.1 概述

真实风场中，风速波动、风向误差、湍流变化和模型参数不确定性都会影响优化结果的可用性。FLORIS 提供 `UncertainFlorisModel`（`floris/uncertain_floris_model.py`）把"单一确定工况"扩展为"带概率扰动的一组工况"，从而评估方案的期望收益和波动范围。

### 9.2 UncertainFlorisModel 的应用

- 参数敏感性分析；
- 控制策略稳健性评估；
- 不同尾流模型下结果波动比较；
- AEP 或收益结果的区间化表达。

### 9.3 优化稳健性评估

控制优化（特别是偏航优化）不应只看单一工况的"最优偏航角"，还要评估：

- 对风向偏差是否敏感；
- 对湍流强度变化是否敏感；
- 对尾流模型切换是否稳健；
- 在多台机组同时控制时是否容易过拟合某一类工况。

工程做法：结合 `UncertainFlorisModel` 做输入扰动，把某个确定工况扩展成概率分布下的工况集合，再比较控制策略的期望收益和波动范围。

### 9.4 大气稳定度的间接处理

FLORIS 不直接使用稳定度参数（无 `stability`、`Monin_Obukhov_Length` 字段），稳定度通过 TI、Shear、Veer 三个变量间接影响：

```
Atmospheric Stability
        ↓
   TI / Shear / Veer
        ↓
      FLORIS
        ↓
   Wake & AEP
```

工程做法：

- 用 TI 表征：稳定层 TI 低（0.04–0.06）、不稳定层 TI 高（0.10–0.16）；
- 用 WindTIRose 把稳定度作为第三维变量分层建模。

对布局优化的间接影响：

- 稳定层：TI 低、wake 恢复慢、尾流更长 → 倾向大间距布局；
- 不稳定层：TI 高、wake 恢复快、尾流更短 → 可更紧凑布局。

---

## 10. 浮式风电场

FLORIS 官方示例（`examples/examples_floating/`）已包含浮式风机：

- `001_floating_turbine_models.py`
- `002_floating_vs_fixedbottom_farm.py`
- `003_tilt_driven_vertical_wake_deflection.py`

### 10.1 浮式风机的工程难点

浮式风机不是固定在刚性地基上，而是随平台产生俯仰、横摇、纵摇或位置变化，从而改变转子相对来流的姿态。

### 10.2 FLORIS 的处理思路

将浮式影响理解为以下几类修正：

- **风机姿态改变**：等效改变轮毂位置、转子法向和入流夹角；
- **偏航与倾斜耦合**：平台运动改变尾流偏转与尾流中心线位置；
- **多工况评估**：通过工况样本或不确定性建模评估平台运动对 AEP 和控制收益的影响。

**关键修正机制**（启用 `correct_cp_ct_for_tilt` 时）：

```yaml
floating_tilt_table:
  wind_speed: [4.0, 8.0, 12.0, 16.0]
  tilt: [5.0, 7.5, 10.0, 12.0]
correct_cp_ct_for_tilt: true
```

$$
P_{\mathrm{corrected}} = P \cdot \left(\frac{\cos\theta_{\mathrm{actual}}}{\cos\theta_{\mathrm{ref}}}\right)^{p_\theta}, \quad
C_{T,\mathrm{corrected}} = C_T \cdot \frac{\cos\theta_{\mathrm{actual}}}{\cos\theta_{\mathrm{ref}}}
$$

**注意**：FLORIS 对浮式场景的处理仍属工程级尾流建模，不等同于把浮体水动力、系泊动力学和高保真气动弹性全过程直接求解出来。

---

## 11. 高级能力

### 11.1 多维 `Cp/Ct` 与性能曲面

多维 `Cp/Ct` 允许风机性能不只是"风速-功率"曲线，而是与湍流、控制状态或运行模式耦合的性能面。`examples/examples_multidim/` 给出示例：

- `001_multi_dimensional_cp_ct.py`
- `002_multi_dimensional_cp_ct_2Hs.py`
- `003_multi_dimensional_cp_ct_TI.py`
- `examples/inputs/gch_multi_dim_cp_ct.yaml`
- `examples/inputs/gch_multi_dim_cp_ct_TI.yaml`

```python
from floris import FlorisModel

fmodel = FlorisModel("examples/inputs/gch_multi_dim_cp_ct.yaml")

fmodel.set(
    wind_directions=[270, 280, 290],
    wind_speeds=[8.0, 9.0, 10.0],
    turbulence_intensities=[0.06, 0.07, 0.08],
)

fmodel.run()
power = fmodel.get_turbine_powers()
```

这使得以下分析成为可能：

- 同一控制策略在不同运行状态下的性能差异；
- 降额策略对推力和尾流恢复的影响；
- 机型或控制模式变化对风场优化结果的传递影响。

### 11.2 多目标与复杂约束优化

FLORIS 可支持更复杂的目标组合：

- 发电量最大化与载荷最小化之间的权衡；
- 边界、多边形禁布区和最小间距约束下的布局设计；
- 异质来流条件下的稳健布局优化；
- 面向收益而非单纯发电量的价值函数优化。

特别适合承担"技术论证平台"角色，在多个方案之间快速构建可比较、可解释的工程指标。

### 11.3 控制器相关参数对布局优化的影响

| 参数 | 布局优化重要性 |
|--------|--------|
| $C_T(U)$ | ★★★★★ |
| Power Curve | ★★★★★ |
| 转子直径 | ★★★★★ |
| 轮毂高度 | ★★★★☆ |
| TI / Shear / Veer | ★★★★☆ |
| 发电机效率 | ★★☆☆☆ |
| $C_P/C_T$ 曲面 | ★★☆☆☆ |
| 额定转速 | ★☆☆☆☆ |
| 转子实度 | ★☆☆☆☆ |

布局优化最重要的是**功率曲线、$C_T$ 曲线、风资源数据**；机组控制细节（额定转速、转子实度等）影响很小。

---

## 14. 参考

参考资料与代码参考分两小节呈现：前者是官方文档与外部资料链接，后者是 FLORIS 仓库内子系统的位置与职责速查。

### 14.1 资料参考

- FLORIS 首页：https://natlabrockies.github.io/floris/index.html
- Developer guide：https://natlabrockies.github.io/floris/dev_guide.html
- Wake models：https://natlabrockies.github.io/floris/wake_models.html
- FLORIS models：https://natlabrockies.github.io/floris/floris_models.html
- Layout optimization：https://natlabrockies.github.io/floris/layout_optimization.html
- Control optimization examples：https://natlabrockies.github.io/floris/examples_control_optimization.html
- Heterogeneous map：https://natlabrockies.github.io/floris/heterogeneous_map.html
- Multidimensional wind turbine：https://natlabrockies.github.io/floris/multidimensional_wind_turbine.html
- Value functions：https://natlabrockies.github.io/floris/value_functions.html

### 14.2 代码参考

FLORIS 的能力分布在以下子系统中：

| 子系统 | 位置 | 主要职责 |
|------|------|------|
| 速度亏损模型 | `floris/core/wake_velocity/` | 尾流截面速度分布 |
| 偏转模型 | `floris/core/wake_deflection/` | 尾流中心线偏移 |
| 湍流模型 | `floris/core/wake_turbulence/` | 尾流附加湍流与恢复 |
| 叠加模型 | `floris/core/wake_combination/` | 多尾流合成 |
| 偏航优化 | `floris/optimization/yaw_optimization/` | 偏航角序列寻优 |
| 布局优化 | `floris/optimization/layout_optimization/` | 风机坐标寻优 |
| 载荷优化 | `floris/optimization/load_optimization/` | 控制与载荷权衡 |
| 并行评估 | `floris/par_floris_model.py` | 多工况并行执行 |
| 近似模型 | `examples/examples_uncertain/002_approx_floris_model.py` | 快速代理 |
| 不确定性 | `floris/uncertain_floris_model.py` | 参数扰动与稳健性 |
| 异质来流 | `floris/heterogeneous_map.py` | 空间风速修正场 |
| 可视化 | `floris/flow_visualization.py` | 流场与结果展示 |
