import os
import json
import pandas as pd
import matplotlib

# 使用无头后端，避免 GUI 阻塞
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 配置中文字体，确保 Windows 下中文正常显示
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# =========================
# 文件路径配置
# =========================

INPUT_JSON = "data/analysis_summary.json"
if os.path.exists("data/steam_games_recent_clean.csv"):
    INPUT_CSV = "data/steam_games_recent_clean.csv"
else:
    INPUT_CSV = "data/steam_games_clean.csv"

CHARTS_DIR = "charts"
DASHBOARD_HTML = os.path.join(CHARTS_DIR, "steam_dashboard.html")


# =========================
# 加载分析数据
# =========================

def load_data():

    os.makedirs(CHARTS_DIR, exist_ok=True)

    # 如果没有 JSON，先提示或读取 CSV
    if not os.path.exists(INPUT_JSON):
        print("未找到 analysis_summary.json，请先运行 python analysis.py！")
        if os.path.exists(INPUT_CSV):
            import analysis
            analysis.main()
        else:
            print(f"数据文件缺失：{INPUT_CSV}")
            return None, None

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        summary = json.load(f)

    df = None
    if os.path.exists(INPUT_CSV):
        df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")

    return summary, df


# ========================================================
# 1. 生成基于 Matplotlib 的静态图表（供论文插入 Word 使用）
# ========================================================

def generate_static_charts(summary, df):

    print("\n正在生成静态图表（供毕业论文配图插入使用）...")

    # 8.1 折线图：年度游戏发行数量趋势
    market_scale = summary.get("market_scale", [])
    if market_scale:
        years = [item["year"] for item in market_scale]
        counts = [item["count"] for item in market_scale]

        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
        ax.plot(years, counts, marker="o", color="#3b82f6", linewidth=2.5, markersize=7)
        for x, y in zip(years, counts):
            ax.annotate(f"{y}款", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=10, fontweight="bold")
        ax.set_title("Steam 游戏年度发行数量走势 (8.1 折线图)", fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("发行年份", fontsize=11)
        ax.set_ylabel("游戏数量 (款)", fontsize=11)
        ax.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig1_release_trend.png"))
        plt.close(fig)
        print("  - 已生成 fig1_release_trend.png (年度趋势折线图)")

    # 8.2 柱状图：Genre TOP 10 热门类型
    genres = summary.get("genres", [])[:10]
    if genres:
        names = [item["genre"] for item in genres][::-1]
        counts = [item["count"] for item in genres][::-1]

        fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
        bars = ax.barh(names, counts, color="#0ea5e9", height=0.6)
        for bar in bars:
            w = bar.get_width()
            ax.text(w + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2, f"{int(w)}款", va="center", fontsize=9)
        ax.set_title("Steam 热门游戏类型分布 TOP 10 (8.2 柱状图)", fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("游戏数量 (款)", fontsize=11)
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig2_genres_top.png"))
        plt.close(fig)
        print("  - 已生成 fig2_genres_top.png (热门类型柱状图)")

    # 8.3 饼图：免费 vs 付费 & 操作系统平台占比
    prices = summary.get("prices", {})
    platforms = summary.get("platforms", {})
    if prices and platforms:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), dpi=200)

        # 免费/付费饼图
        free_c = prices.get("free_count", 0)
        paid_c = prices.get("paid_count", 0)
        if free_c + paid_c > 0:
            ax1.pie(
                [free_c, paid_c],
                labels=["免费游戏", "付费游戏"],
                autopct="%1.1f%%",
                colors=["#10b981", "#6366f1"],
                startangle=140,
                explode=(0.05, 0)
            )
            ax1.set_title("免费 vs 付费游戏占比 (8.3 饼图)", fontsize=11, fontweight="bold")

        # 平台支持饼图
        win_c = platforms.get("windows", 0)
        mac_c = platforms.get("mac", 0)
        linux_c = platforms.get("linux", 0)
        ax2.pie(
            [win_c, mac_c, linux_c],
            labels=["Windows", "macOS", "Linux"],
            autopct="%1.1f%%",
            colors=["#3b82f6", "#f59e0b", "#ec4899"],
            startangle=140
        )
        ax2.set_title("操作系统平台支持分布 (8.3 饼图)", fontsize=11, fontweight="bold")

        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig3_proportions_pie.png"))
        plt.close(fig)
        print("  - 已生成 fig3_proportions_pie.png (比例分布饼图)")

    # 8.4 直方图/柱状分布：价格区间与折扣分布
    price_dist = prices.get("distribution", [])
    if price_dist:
        p_ranges = [item["range"].split("(")[0] for item in price_dist]
        p_counts = [item["count"] for item in price_dist]

        fig, ax = plt.subplots(figsize=(9, 4.5), dpi=200)
        bars = ax.bar(p_ranges, p_counts, color="#8b5cf6", width=0.55)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + max(p_counts) * 0.015, f"{int(h)}款", ha="center", fontsize=9)
        ax.set_title("游戏价格区间分布特征 (8.4 直方图/柱状分布)", fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel("游戏数量 (款)", fontsize=11)
        ax.set_xticks(range(len(p_ranges)))
        ax.set_xticklabels(p_ranges, rotation=15, ha="right", fontsize=9.5)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig4_price_distribution.png"))
        plt.close(fig)
        print("  - 已生成 fig4_price_distribution.png (价格分布直方图)")

    # 8.5 箱线图/条形图：主要类型平均价格水平
    genre_price = summary.get("genre_price", [])[:8]
    if genre_price:
        gp_names = [item["genre"] for item in genre_price][::-1]
        gp_means = [item["mean_price"] for item in genre_price][::-1]
        gp_medians = [item["median_price"] for item in genre_price][::-1]

        fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
        y_pos = range(len(gp_names))
        ax.barh([p - 0.18 for p in y_pos], gp_means, height=0.35, color="#f97316", label="平均价(元)")
        ax.barh([p + 0.18 for p in y_pos], gp_medians, height=0.35, color="#14b8a6", label="中位价(元)")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(gp_names, fontsize=10)
        ax.set_xlabel("价格 (元)", fontsize=11)
        ax.set_title("主流游戏类型价格水平对比 (8.5 价格特征图)", fontsize=13, fontweight="bold", pad=12)
        ax.legend(loc="lower right")
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig5_genre_price.png"))
        plt.close(fig)
        print("  - 已生成 fig5_genre_price.png (类型价格对比图)")

    # 8.6 共现热力图：Genre x Genre
    genre_matrix = summary.get("genre_matrix", {})
    if genre_matrix and "top_genres" in genre_matrix:
        top_g = genre_matrix["top_genres"]
        mat = [[genre_matrix["matrix"][g1][g2] for g2 in top_g] for g1 in top_g]

        fig, ax = plt.subplots(figsize=(8, 7), dpi=200)
        im = ax.imshow(mat, cmap="YlGnBu")
        ax.set_xticks(range(len(top_g)))
        ax.set_yticks(range(len(top_g)))
        ax.set_xticklabels(top_g, rotation=45, ha="right", fontsize=9.5)
        ax.set_yticklabels(top_g, fontsize=9.5)
        for i in range(len(top_g)):
            for j in range(len(top_g)):
                ax.text(j, i, str(mat[i][j]), ha="center", va="center", color="black" if mat[i][j] < max(map(max, mat)) * 0.7 else "white", fontsize=8.5)
        fig.colorbar(im, ax=ax, shrink=0.75, label="共现频次")
        ax.set_title("主流游戏类型共现热力图 (8.6 热力图)", fontsize=13, fontweight="bold", pad=12)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig6_genre_cooccurrence_heatmap.png"))
        plt.close(fig)
        print("  - 已生成 fig6_genre_cooccurrence_heatmap.png (共现热力图)")

    # 8.7 商业维度一：流派商业产值矩阵 (总流水 vs 单作中位数流水)
    comm_genres = summary.get("commercial_genre_revenue", [])[:10]
    if comm_genres:
        g_names = [item["genre"] for item in comm_genres]
        tot_revs = [item["total_revenue"] / 10000 for item in comm_genres]
        med_revs = [item["median_revenue"] / 10000 for item in comm_genres]

        fig, ax1 = plt.subplots(figsize=(10, 5.2), dpi=200)
        x = range(len(g_names))
        ax1.bar(x, tot_revs, width=0.45, color="#10b981", alpha=0.85, label="流派预估总流水 (万元)")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(g_names, rotation=25, ha="right", fontsize=10)
        ax1.set_ylabel("流派总流水 (万元)", fontsize=11, color="#059669")

        ax2 = ax1.twinx()
        ax2.plot(x, med_revs, marker="o", color="#f59e0b", linewidth=2.5, label="单作中位数流水 (万元)")
        ax2.set_ylabel("单作中位数流水 (万元)", fontsize=11, color="#d97706")

        ax1.set_title("Steam 细分流派商业总产值与中位数流水对比 (8.7 双轴图)", fontsize=13, fontweight="bold", pad=12)
        ax1.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig7_commercial_genre_revenue.png"))
        plt.close(fig)
        print("  - 已生成 fig7_commercial_genre_revenue.png (流派商业产值矩阵)")

    # 8.8 商业维度二：市场二八定律与头部垄断格局
    comm_pareto = summary.get("commercial_pareto", {})
    tiers = comm_pareto.get("concentration_tiers", [])
    if tiers:
        t_labels = [f"{t['tier']}\n({t['count']}款)" for t in tiers]
        shares = [t["revenue_share"] for t in tiers]
        gini = comm_pareto.get("gini_coefficient", 0.0)

        fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=200)
        bars = ax.bar(t_labels, shares, color="#ec4899", width=0.45)
        ax.plot(range(len(t_labels)), shares, marker="s", color="#eab308", linewidth=2.2, label="累计流水集中度趋势")
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.1f}%", (bar.get_x() + bar.get_width() / 2, h), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9.5, fontweight="bold")
        ax.set_ylim(0, 112)
        ax.set_ylabel("占全平台总流水比例 (%)", fontsize=11)
        ax.set_title(f"Steam 市场二八定律与头部垄断格局 (基尼系数 Gini={gini:.4f})", fontsize=13, fontweight="bold", pad=12)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        ax.legend()
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig8_commercial_pareto.png"))
        plt.close(fig)
        print("  - 已生成 fig8_commercial_pareto.png (二八定律与长尾垄断图)")

    # 8.9 商业维度三：价格—销量弹性与黄金定价区间
    comm_elast = summary.get("commercial_price_elasticity", [])
    if comm_elast:
        p_labels = [item["tier_label"].split(" ")[0] for item in comm_elast]
        tot_rev_w = [item["total_revenue"] / 10000 for item in comm_elast]
        avg_sales = [item["avg_sales"] for item in comm_elast]

        fig, ax1 = plt.subplots(figsize=(9.5, 5), dpi=200)
        x = range(len(p_labels))
        ax1.bar(x, tot_rev_w, width=0.42, color="#f59e0b", alpha=0.85, label="区间总流水 (万元)")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels([item["tier_label"] for item in comm_elast], rotation=20, ha="right", fontsize=9.5)
        ax1.set_ylabel("区间总预估流水 (万元)", fontsize=11, color="#d97706")

        ax2 = ax1.twinx()
        ax2.plot(x, avg_sales, marker="o", color="#0284c7", linewidth=2.5, label="平均单款销量 (份)")
        ax2.set_ylabel("平均单款销量 (份)", fontsize=11, color="#0284c7")

        ax1.set_title("Steam 价格—销量弹性与黄金定价带测算 (8.9 双轴图)", fontsize=13, fontweight="bold", pad=12)
        ax1.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig9_commercial_price_elasticity.png"))
        plt.close(fig)
        print("  - 已生成 fig9_commercial_price_elasticity.png (价格弹性与黄金定价带)")

    # 8.10 商业维度四：口碑受众与销量表现相关性
    comm_rev_sales = summary.get("commercial_review_sales", {})
    s_tiers = comm_rev_sales.get("sentiment_tiers", [])
    if s_tiers:
        s_labels = [item["tier"] for item in s_tiers]
        s_avg = [item["avg_sales"] for item in s_tiers]
        s_med = [item["median_sales"] for item in s_tiers]

        fig, ax1 = plt.subplots(figsize=(9, 4.8), dpi=200)
        x = range(len(s_labels))
        ax1.bar(x, s_avg, width=0.42, color="#6366f1", alpha=0.85, label="平均预估销量 (份)")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(s_labels, rotation=15, ha="right", fontsize=9.5)
        ax1.set_ylabel("平均预估销量 (份)", fontsize=11, color="#4f46e5")

        ax2 = ax1.twinx()
        ax2.plot(x, s_med, marker="D", color="#10b981", linewidth=2.2, label="中位数销量 (份)")
        ax2.set_ylabel("中位数销量 (份)", fontsize=11, color="#059669")

        ax1.set_title("Steam 玩家口碑梯度与商业销量表现关联图 (8.10)", fontsize=13, fontweight="bold", pad=12)
        ax1.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig10_commercial_review_sales.png"))
        plt.close(fig)
        print("  - 已生成 fig10_commercial_review_sales.png (口碑与销量相关性图)")

    # 8.11 商业维度五：研发与发行生态图鉴 (自主发行 vs 商业发行)
    comm_pub = summary.get("commercial_publisher_tiers", {}).get("publishing_mode_comparison", {})
    if comm_pub:
        s_data = comm_pub.get("self_published", {})
        c_data = comm_pub.get("commercial_published", {})
        modes = [f"独立自发行\n({s_data.get('count', 0)}款)", f"商业发行商代理\n({c_data.get('count', 0)}款)"]
        med_rev_w = [s_data.get("median_revenue", 0) / 10000, c_data.get("median_revenue", 0) / 10000]
        hit_rates = [s_data.get("hit_rate_pct", 0), c_data.get("hit_rate_pct", 0)]

        fig, ax1 = plt.subplots(figsize=(7.5, 4.6), dpi=200)
        x = [0, 1]
        ax1.bar([i - 0.16 for i in x], med_rev_w, width=0.3, color="#0ea5e9", label="中位数生存线流水 (万元)")
        ax1.set_xticks(x)
        ax1.set_xticklabels(modes, fontsize=10.5, fontweight="bold")
        ax1.set_ylabel("中位数流水 (万元)", fontsize=11, color="#0284c7")

        ax2 = ax1.twinx()
        ax2.bar([i + 0.16 for i in x], hit_rates, width=0.3, color="#f59e0b", label="爆款诞生率 (% 销量≥5万)")
        ax2.set_ylabel("爆款诞生率 (%)", fontsize=11, color="#d97706")

        ax1.set_title("独立自主发行 vs 第三方商业发行生存表现对比 (8.11)", fontsize=13, fontweight="bold", pad=12)
        ax1.grid(axis="y", linestyle="--", alpha=0.4)
        plt.tight_layout()
        fig.savefig(os.path.join(CHARTS_DIR, "fig11_commercial_publisher_tiers.png"))
        plt.close(fig)
        print("  - 已生成 fig11_commercial_publisher_tiers.png (发行模式对比图)")


# ========================================================
# 2. 生成交互式 ECharts 仪表盘网页 (包含 8.1 ~ 8.6 所有图表)
# ========================================================

def generate_echarts_html(summary):

    print("\n正在生成交互式 ECharts 大屏看板网页...")

    json_str = json.dumps(summary, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Steam 电子游戏市场数据分析与可视化看板</title>
    <!-- 引入 ECharts 官方 CDN -->
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0f172a;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #1e293b;
        }}
        .header h1 {{
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header p {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}
        .badge {{
            background: #1e293b;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            border: 1px solid #334155;
            color: #38bdf8;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }}
        .card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        .card-full {{
            grid-column: span 2;
        }}
        .card-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            color: #e2e8f0;
        }}
        .card-title::before {{
            content: "";
            width: 4px;
            height: 16px;
            background: #38bdf8;
            border-radius: 2px;
            margin-right: 8px;
        }}
        .chart-box {{
            width: 100%;
            height: 340px;
        }}
        .chart-box-large {{
            width: 100%;
            height: 420px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Steam 电子游戏市场数据分析可视化看板</h1>
            <p>基于 Steam Web API 的多维度市场与关联特征研究 (满足《要求.md》第8项)</p>
        </div>
        <div class="badge">已清洗有效样本：<span id="total-games">-</span> 款</div>
    </div>

    <div class="grid">
        <!-- 8.1 折线图：年度发行数量 -->
        <div class="card">
            <div class="card-title">8.1 市场规模年度发行数量走势 (折线图)</div>
            <div id="chart-line-year" class="chart-box"></div>
        </div>

        <!-- 8.2 柱状图：热门类型排行 -->
        <div class="card">
            <div class="card-title">8.2 热门游戏类型排行榜 TOP 10 (柱状图)</div>
            <div id="chart-bar-genres" class="chart-box"></div>
        </div>

        <!-- 8.3 饼图：免费 vs 付费 -->
        <div class="card">
            <div class="card-title">8.3 免费 vs 付费游戏占比 (环形饼图)</div>
            <div id="chart-pie-free" class="chart-box"></div>
        </div>

        <!-- 8.3 饼图：平台支持 -->
        <div class="card">
            <div class="card-title">8.3 操作系统平台支持比例 (饼图)</div>
            <div id="chart-pie-platform" class="chart-box"></div>
        </div>

        <!-- 8.4 直方图：价格分布 -->
        <div class="card">
            <div class="card-title">8.4 游戏售价区间分布 (直方柱状图)</div>
            <div id="chart-bar-price-dist" class="chart-box"></div>
        </div>

        <!-- 8.5 柱线图：类型平均价格水平 -->
        <div class="card">
            <div class="card-title">8.5 主流游戏类型价格水平对比 (均价/中位价)</div>
            <div id="chart-bar-genre-price" class="chart-box"></div>
        </div>

        <!-- 8.6 热力图：类型共现矩阵 -->
        <div class="card card-full">
            <div class="card-title">8.6 游戏类型共现热力矩阵 Genre × Genre (热力图)</div>
            <div id="chart-heatmap-cooccur" class="chart-box-large"></div>
        </div>
    </div>

    <script>
        const rawData = {json_str};

        document.getElementById('total-games').innerText = rawData.total_games || 0;

        // 通用暗色系配置
        const textStyle = {{ color: '#94a3b8' }};
        const splitLineStyle = {{ lineStyle: {{ color: '#334155', type: 'dashed' }} }};

        // 1. 年度发行数量折线图 (8.1)
        const chartLineYear = echarts.init(document.getElementById('chart-line-year'));
        const ms = rawData.market_scale || [];
        chartLineYear.setOption({{
            tooltip: {{ trigger: 'axis' }},
            grid: {{ left: '4%', right: '4%', bottom: '8%', containLabel: true }},
            xAxis: {{ type: 'category', data: ms.map(i => i.year + '年'), axisLabel: textStyle }},
            yAxis: {{ type: 'value', axisLabel: textStyle, splitLine: splitLineStyle }},
            series: [{{
                name: '发行数量',
                type: 'line',
                data: ms.map(i => i.count),
                smooth: true,
                symbolSize: 8,
                lineStyle: {{ width: 3, color: '#38bdf8' }},
                itemStyle: {{ color: '#38bdf8' }},
                areaStyle: {{
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        {{ offset: 0, color: 'rgba(56, 189, 248, 0.4)' }},
                        {{ offset: 1, color: 'rgba(56, 189, 248, 0.0)' }}
                    ])
                }}
            }}]
        }});

        // 2. 热门类型排行榜 (8.2)
        const chartBarGenres = echarts.init(document.getElementById('chart-bar-genres'));
        const gs = (rawData.genres || []).slice(0, 10).reverse();
        chartBarGenres.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
            grid: {{ left: '4%', right: '8%', bottom: '5%', containLabel: true }},
            xAxis: {{ type: 'value', axisLabel: textStyle, splitLine: splitLineStyle }},
            yAxis: {{ type: 'category', data: gs.map(i => i.genre), axisLabel: textStyle }},
            series: [{{
                name: '覆盖款数',
                type: 'bar',
                data: gs.map(i => i.count),
                itemStyle: {{
                    borderRadius: [0, 4, 4, 0],
                    color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
                        {{ offset: 0, color: '#0ea5e9' }},
                        {{ offset: 1, color: '#3b82f6' }}
                    ])
                }}
            }}]
        }});

        // 3. 免费 vs 付费饼图 (8.3)
        const chartPieFree = echarts.init(document.getElementById('chart-pie-free'));
        const pr = rawData.prices || {{}};
        chartPieFree.setOption({{
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}款 ({{d}}%)' }},
            legend: {{ bottom: '5%', textStyle: textStyle }},
            series: [{{
                name: '付费属性',
                type: 'pie',
                radius: ['45%', '70%'],
                center: ['50%', '45%'],
                itemStyle: {{ borderRadius: 8, borderColor: '#1e293b', borderWidth: 2 }},
                data: [
                    {{ value: pr.free_count || 0, name: '免费游戏', itemStyle: {{ color: '#10b981' }} }},
                    {{ value: pr.paid_count || 0, name: '付费游戏', itemStyle: {{ color: '#6366f1' }} }}
                ]
            }}]
        }});

        // 4. 平台支持饼图 (8.3)
        const chartPiePlatform = echarts.init(document.getElementById('chart-pie-platform'));
        const pl = rawData.platforms || {{}};
        chartPiePlatform.setOption({{
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}款 ({{d}}%)' }},
            legend: {{ bottom: '5%', textStyle: textStyle }},
            series: [{{
                name: '操作系统',
                type: 'pie',
                radius: '65%',
                center: ['50%', '45%'],
                data: [
                    {{ value: pl.windows || 0, name: 'Windows', itemStyle: {{ color: '#3b82f6' }} }},
                    {{ value: pl.mac || 0, name: 'macOS', itemStyle: {{ color: '#f59e0b' }} }},
                    {{ value: pl.linux || 0, name: 'Linux', itemStyle: {{ color: '#ec4899' }} }}
                ]
            }}]
        }});

        // 5. 价格区间分布直方图 (8.4)
        const chartBarPriceDist = echarts.init(document.getElementById('chart-bar-price-dist'));
        const pdist = pr.distribution || [];
        chartBarPriceDist.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
            grid: {{ left: '4%', right: '4%', bottom: '15%', containLabel: true }},
            xAxis: {{ type: 'category', data: pdist.map(i => i.range.split('(')[0]), axisLabel: {{ ...textStyle, interval: 0, rotate: 20 }} }},
            yAxis: {{ type: 'value', axisLabel: textStyle, splitLine: splitLineStyle }},
            series: [{{
                name: '游戏数量',
                type: 'bar',
                data: pdist.map(i => i.count),
                itemStyle: {{
                    borderRadius: [4, 4, 0, 0],
                    color: '#8b5cf6'
                }}
            }}]
        }});

        // 6. 主流类型价格水平对比 (8.5)
        const chartBarGenrePrice = echarts.init(document.getElementById('chart-bar-genre-price'));
        const gp = (rawData.genre_price || []).slice(0, 8);
        chartBarGenrePrice.setOption({{
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
            legend: {{ top: '2%', textStyle: textStyle }},
            grid: {{ left: '4%', right: '4%', bottom: '12%', containLabel: true }},
            xAxis: {{ type: 'category', data: gp.map(i => i.genre), axisLabel: {{ ...textStyle, interval: 0, rotate: 20 }} }},
            yAxis: {{ type: 'value', name: '价格(元)', nameTextStyle: textStyle, axisLabel: textStyle, splitLine: splitLineStyle }},
            series: [
                {{
                    name: '平均价格',
                    type: 'bar',
                    data: gp.map(i => i.mean_price),
                    itemStyle: {{ color: '#f97316', borderRadius: [4, 4, 0, 0] }}
                }},
                {{
                    name: '中位价格',
                    type: 'bar',
                    data: gp.map(i => i.median_price),
                    itemStyle: {{ color: '#14b8a6', borderRadius: [4, 4, 0, 0] }}
                }}
            ]
        }});

        // 7. 类型共现热力图 (8.6)
        const chartHeatmapCooccur = echarts.init(document.getElementById('chart-heatmap-cooccur'));
        const gm = rawData.genre_matrix || {{}};
        const topG = gm.top_genres || [];
        const matrixData = [];
        let maxVal = 0;
        topG.forEach((g1, i) => {{
            topG.forEach((g2, j) => {{
                const val = (gm.matrix && gm.matrix[g1] && gm.matrix[g1][g2]) || 0;
                if (val > maxVal) maxVal = val;
                matrixData.push([j, i, val]);
            }});
        }});

        chartHeatmapCooccur.setOption({{
            tooltip: {{
                position: 'top',
                formatter: params => `${{topG[params.value[1]]}} + ${{topG[params.value[0]]}}<br/>共现频次: ${{params.value[2]}} 次`
            }},
            grid: {{ left: '10%', right: '12%', top: '5%', bottom: '15%' }},
            xAxis: {{ type: 'category', data: topG, splitArea: {{ show: true }}, axisLabel: {{ ...textStyle, interval: 0, rotate: 30 }} }},
            yAxis: {{ type: 'category', data: topG, splitArea: {{ show: true }}, axisLabel: textStyle }},
            visualMap: {{
                min: 0,
                max: maxVal || 10,
                calculable: true,
                orient: 'vertical',
                right: '2%',
                top: 'center',
                textStyle: textStyle,
                inRange: {{
                    color: ['#1e293b', '#0369a1', '#38bdf8', '#fbbf24']
                }}
            }},
            series: [{{
                name: '共现矩阵',
                type: 'heatmap',
                data: matrixData,
                label: {{ show: true, color: '#f8fafc', fontSize: 11 }},
                emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' }} }}
            }}]
        }});

        // 响应式自适应
        window.addEventListener('resize', () => {{
            chartLineYear.resize();
            chartBarGenres.resize();
            chartPieFree.resize();
            chartPiePlatform.resize();
            chartBarPriceDist.resize();
            chartBarGenrePrice.resize();
            chartHeatmapCooccur.resize();
        }});
    </script>
</body>
</html>"""

    with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"  - 已生成 {DASHBOARD_HTML} (双击即可直接在浏览器打开交互式 ECharts 看板！)")


# =========================
# 主程序
# =========================

def main():

    summary, df = load_data()
    if summary is None:
        return

    # 1. 生成可插入 Word 论文的静态 PNG 图表 (matplotlib)
    generate_static_charts(summary, df)

    # 2. 生成交互式 ECharts 网页大屏看板 (8.1 ~ 8.6 全部涵盖)
    generate_echarts_html(summary)

    print("\n================== 数据可视化生成完毕 ==================")
    print(f"1. 毕业论文插图已保存在：{CHARTS_DIR}/ 目录下（包含 fig1~fig6 高清 PNG）")
    print(f"2. 交互式 ECharts 大屏网页已生成：{DASHBOARD_HTML}")
    print("   直接在 Windows 文件管理器中双击打开该 HTML 文件即可体验交互！")


if __name__ == "__main__":
    main()
