import sys
import os
import re
import json
import pandas as pd
import numpy as np
from collections import Counter

# 解决 Windows 控制台打印特殊字符编码异常问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


# =========================
# 文件路径配置
# =========================

if os.path.exists("data/steam_games_recent_clean.csv"):
    INPUT_FILE = "data/steam_games_recent_clean.csv"
else:
    INPUT_FILE = "data/steam_games_clean.csv"

OUTPUT_JSON = "data/analysis_summary.json"


# =========================
# 读取清洗后数据
# =========================

def load_clean_data():

    if not os.path.exists(INPUT_FILE):
        print(f"找不到清洗后的数据文件：{INPUT_FILE}")
        print("请先运行 python data_clean.py 完成数据清洗！")
        return None

    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    print(f"成功读取数据：{INPUT_FILE}，共 {len(df)} 款有效游戏")
    return df


# ========================================================
# 第 6 章：基础描述性分析
# ========================================================

# 6.1 游戏市场规模分析（按年份）
def analyze_market_scale(df):
    print("\n================== 6.1 市场规模分析（年度发行趋势） ==================")
    years = df["release_date"].astype(str).str.extract(r"(\d{4})")[0]
    year_counts = years.value_counts().sort_index()

    results = []
    print("发行年份\t游戏数量\t占比")
    total = len(df)
    for year, count in year_counts.items():
        ratio = count / total * 100
        print(f"{year}年\t{count}款\t{ratio:.1f}%")
        results.append({
            "year": str(year),
            "count": int(count),
            "ratio": round(ratio, 2)
        })
    return results


# 6.2 游戏类型分析（Genres）
def analyze_genres(df):
    print("\n================== 6.2 游戏类型分析（Genre） ==================")
    genre_counter = Counter()
    for item in df["genres"].dropna():
        if str(item).strip():
            genres = [g.strip() for g in str(item).split(";") if g.strip()]
            genre_counter.update(genres)

    results = []
    total_games = len(df)
    print("类型名称\t\t游戏数量\t覆盖率")
    for genre, count in genre_counter.most_common(15):
        ratio = count / total_games * 100
        print(f"{genre:<16}\t{count}款\t{ratio:.1f}%")
        results.append({
            "genre": genre,
            "count": int(count),
            "ratio": round(ratio, 2)
        })
    return results


# 6.3 游戏价格分析
def analyze_prices(df):
    print("\n================== 6.3 游戏价格特征分析 ==================")
    total = len(df)
    free_games = df[df["is_free"] == True]
    paid_games = df[df["is_free"] == False]
    free_count = len(free_games)
    paid_count = len(paid_games)

    print(f"免费游戏数量：{free_count} 款 ({free_count / total * 100:.1f}%)")
    print(f"付费游戏数量：{paid_count} 款 ({paid_count / total * 100:.1f}%)")

    paid_prices = paid_games["final_price"].dropna()
    price_stats = {}
    if len(paid_prices) > 0:
        price_stats = {
            "mean": round(float(paid_prices.mean()), 2),
            "median": round(float(paid_prices.median()), 2),
            "min": round(float(paid_prices.min()), 2),
            "max": round(float(paid_prices.max()), 2)
        }
        print(f"付费游戏平均价：{price_stats['mean']} 元")
        print(f"付费游戏中位数：{price_stats['median']} 元")
        print(f"价格区间：{price_stats['min']} 元 ~ {price_stats['max']} 元")

    bins = [-0.01, 0, 30, 70, 150, 300, 10000]
    labels = ["免费", "1~30元(轻量/小品)", "31~70元(中度独立)", "71~150元(高质独立)", "151~300元(准3A/中大型)", "300元以上(3A旗舰)"]
    price_distribution = pd.cut(df["final_price"].fillna(0), bins=bins, labels=labels).value_counts()

    dist_results = []
    print("\n价格区间分布：")
    for label, count in price_distribution.items():
        ratio = count / total * 100
        print(f"- {label:<22}: {count}款 ({ratio:.1f}%)")
        dist_results.append({
            "range": str(label),
            "count": int(count),
            "ratio": round(ratio, 2)
        })

    return {
        "free_count": free_count,
        "paid_count": paid_count,
        "stats": price_stats,
        "distribution": dist_results
    }


# 6.5 游戏折扣分析
def analyze_discounts(df):
    print("\n================== 6.5 游戏折扣特征分析 ==================")
    total = len(df)
    discounts = df["discount_percent"].fillna(0)

    no_discount = (discounts == 0).sum()
    low_discount = ((discounts > 0) & (discounts <= 30)).sum()
    mid_discount = ((discounts > 30) & (discounts <= 60)).sum()
    high_discount = (discounts > 60).sum()

    print(f"原价无折扣游戏：{no_discount} 款 ({no_discount / total * 100:.1f}%)")
    print(f"低折扣 (1%~30%)：{low_discount} 款 ({low_discount / total * 100:.1f}%)")
    print(f"中折扣 (31%~60%)：{mid_discount} 款 ({mid_discount / total * 100:.1f}%)")
    print(f"深折/骨折 (>60%)：{high_discount} 款 ({high_discount / total * 100:.1f}%)")

    return {
        "no_discount": int(no_discount),
        "low_discount": int(low_discount),
        "mid_discount": int(mid_discount),
        "high_discount": int(high_discount)
    }


# 6.6 开发商分析
def analyze_developers(df):
    print("\n================== 6.6 开发商发行量分析 (TOP 10) ==================")
    dev_counter = Counter()
    for item in df["developers"].dropna():
        if str(item).strip():
            devs = [d.strip() for d in str(item).split(";") if d.strip()]
            dev_counter.update(devs)
    results = []
    print("开发商名称\t\t\t游戏款数")
    for dev, count in dev_counter.most_common(10):
        print(f"{dev:<28}\t{count} 款")
        results.append({"developer": dev, "count": count})
    return results


# 6.7 发行商分析
def analyze_publishers(df):
    print("\n================== 6.7 发行商发行量分析 (TOP 10) ==================")
    pub_counter = Counter()
    for item in df["publishers"].dropna():
        if str(item).strip():
            pubs = [p.strip() for p in str(item).split(";") if p.strip()]
            pub_counter.update(pubs)
    results = []
    print("发行商名称\t\t\t游戏款数")
    for pub, count in pub_counter.most_common(10):
        print(f"{pub:<28}\t{count} 款")
        results.append({"publisher": pub, "count": count})
    return results


# 6.8 平台支持分析
def analyze_platforms(df):
    print("\n================== 6.8 平台支持特征分析 ==================")
    total = len(df)
    platforms_series = df["platforms"].fillna("").astype(str)
    win = platforms_series.str.contains("windows", case=False).sum()
    mac = platforms_series.str.contains("mac", case=False).sum()
    linux = platforms_series.str.contains("linux", case=False).sum()
    multi_platform = platforms_series.map(lambda p: len([x for x in str(p).split(";") if x.strip()]) > 1).sum()

    print(f"Windows 支持：{win} 款 ({win / total * 100:.1f}%)")
    print(f"macOS   支持：{mac} 款 ({mac / total * 100:.1f}%)")
    print(f"Linux   支持：{linux} 款 ({linux / total * 100:.1f}%)")
    print(f"多系统跨平台支持：{multi_platform} 款 ({multi_platform / total * 100:.1f}%)")

    return {
        "windows": int(win),
        "mac": int(mac),
        "linux": int(linux),
        "multi_platform": int(multi_platform)
    }


# ========================================================
# 第 7 章：多维度关联分析 (Correlation Analysis)
# ========================================================

# 7.1 Genre × Price (类型与价格关系)
def analyze_genre_price(df):
    print("\n================== 7.1 关联分析：Genre × Price（类型与价格） ==================")
    pairs = []
    for _, row in df.iterrows():
        price = row.get("final_price", 0)
        genres_str = str(row.get("genres", ""))
        if genres_str.strip() and pd.notna(price):
            for g in genres_str.split(";"):
                g = g.strip()
                if g:
                    pairs.append({"genre": g, "price": float(price)})
    gp_df = pd.DataFrame(pairs)
    results = []
    if not gp_df.empty:
        grouped = gp_df.groupby("genre")["price"].agg(["count", "mean", "median", "max", "min"]).reset_index()
        grouped = grouped.sort_values(by="mean", ascending=False)
        print("游戏类型\t\t样本数\t平均价格\t中位价格\t价格区间")
        for _, r in grouped.iterrows():
            print(f"{r['genre']:<16}\t{int(r['count'])}款\t{r['mean']:.2f}元\t{r['median']:.2f}元\t{r['min']:.1f}~{r['max']:.1f}元")
            results.append({
                "genre": r["genre"],
                "count": int(r["count"]),
                "mean_price": round(float(r["mean"]), 2),
                "median_price": round(float(r["median"]), 2),
                "min_price": round(float(r["min"]), 2),
                "max_price": round(float(r["max"]), 2)
            })
    return results


# 7.2 Genre × Discount (类型与折扣关系)
def analyze_genre_discount(df):
    print("\n================== 7.2 关联分析：Genre × Discount（类型与折扣） ==================")
    pairs = []
    for _, row in df.iterrows():
        disc = row.get("discount_percent", 0)
        genres_str = str(row.get("genres", ""))
        if genres_str.strip() and pd.notna(disc):
            for g in genres_str.split(";"):
                g = g.strip()
                if g:
                    pairs.append({"genre": g, "discount": float(disc)})
    gd_df = pd.DataFrame(pairs)
    results = []
    if not gd_df.empty:
        grouped = gd_df.groupby("genre")["discount"].agg(
            count="count",
            mean_discount="mean",
            discounted_games=lambda s: (s > 0).sum()
        ).reset_index()
        grouped["discount_rate"] = grouped["discounted_games"] / grouped["count"] * 100
        grouped = grouped.sort_values(by="discount_rate", ascending=False)
        print("游戏类型\t\t总样本\t打折款数\t打折比例\t平均折扣率")
        for _, r in grouped.iterrows():
            print(f"{r['genre']:<16}\t{int(r['count'])}款\t{int(r['discounted_games'])}款\t{r['discount_rate']:.1f}%\t{r['mean_discount']:.1f}%")
            results.append({
                "genre": r["genre"],
                "count": int(r["count"]),
                "discounted_games": int(r["discounted_games"]),
                "discount_rate": round(float(r["discount_rate"]), 2),
                "mean_discount": round(float(r["mean_discount"]), 2)
            })
    return results


# 7.3 Genre × Platform (类型与平台支持关系)
def analyze_genre_platform(df):
    print("\n================== 7.3 关联分析：Genre × Platform（类型与平台支持） ==================")
    pairs = []
    for _, row in df.iterrows():
        plat = str(row.get("platforms", "")).lower()
        genres_str = str(row.get("genres", ""))
        if genres_str.strip():
            for g in genres_str.split(";"):
                g = g.strip()
                if g:
                    pairs.append({
                        "genre": g,
                        "win": "windows" in plat,
                        "mac": "mac" in plat,
                        "linux": "linux" in plat
                    })
    gp_df = pd.DataFrame(pairs)
    results = []
    if not gp_df.empty:
        grouped = gp_df.groupby("genre").agg(
            count=("win", "count"),
            win_count=("win", "sum"),
            mac_count=("mac", "sum"),
            linux_count=("linux", "sum")
        ).reset_index()
        grouped["mac_rate"] = grouped["mac_count"] / grouped["count"] * 100
        grouped["linux_rate"] = grouped["linux_count"] / grouped["count"] * 100
        grouped = grouped.sort_values(by="mac_rate", ascending=False)
        print("游戏类型\t\t总数\tWindows支持\tmacOS支持率\tLinux支持率")
        for _, r in grouped.iterrows():
            print(f"{r['genre']:<16}\t{int(r['count'])}\t{int(r['win_count'])}款 (100%)\t{r['mac_rate']:.1f}%\t\t{r['linux_rate']:.1f}%")
            results.append({
                "genre": r["genre"],
                "count": int(r["count"]),
                "mac_rate": round(float(r["mac_rate"]), 2),
                "linux_rate": round(float(r["linux_rate"]), 2)
            })
    return results


# 7.5 Genre × Year (类型随时间发展变化)
def analyze_genre_year(df):
    print("\n================== 7.5 关联分析：Genre × Year（类型年度演变趋势） ==================")
    years = df["release_date"].astype(str).str.extract(r"(\d{4})")[0]
    pairs = []
    for idx, row in df.iterrows():
        y = years.iloc[idx]
        genres_str = str(row.get("genres", ""))
        if pd.notna(y) and genres_str.strip():
            for g in genres_str.split(";"):
                g = g.strip()
                if g:
                    pairs.append({"genre": g, "year": str(y)})
    gy_df = pd.DataFrame(pairs)
    results = {}
    if not gy_df.empty:
        cross_tab = pd.crosstab(gy_df["genre"], gy_df["year"])
        top_genres = cross_tab.sum(axis=1).sort_values(ascending=False).head(8).index
        sub_tab = cross_tab.loc[top_genres]
        print(sub_tab.to_string())
        results = sub_tab.to_dict(orient="index")
    return results


# 7.6 Genre × Genre (类型共现关系与共现矩阵)
def analyze_genre_genre_matrix(df):
    print("\n================== 7.6 关联分析：Genre × Genre（类型共现矩阵） ==================")
    genre_list = []
    genre_counter = Counter()
    for item in df["genres"].dropna():
        genres = sorted(list(set([g.strip() for g in str(item).split(";") if g.strip()])))
        if genres:
            genre_list.append(genres)
            genre_counter.update(genres)

    top_genres = [g for g, _ in genre_counter.most_common(8)]
    matrix = {g1: {g2: 0 for g2 in top_genres} for g1 in top_genres}

    for genres in genre_list:
        sub = [g for g in genres if g in top_genres]
        for i in range(len(sub)):
            for j in range(len(sub)):
                if i != j:
                    matrix[sub[i]][sub[j]] += 1
                else:
                    matrix[sub[i]][sub[j]] += 1

    matrix_df = pd.DataFrame(matrix)
    print(matrix_df.to_string())

    return {
        "top_genres": top_genres,
        "matrix": matrix
    }


# ========================================================
# 第 8 章：数字游戏经济学与商业产值深度洞察 (5大核心商业维度)
# ========================================================

# 8.1 细分流派商业产值与吸金矩阵 (Genre Commercial Value Matrix)
def analyze_genre_revenue(df):
    print("\n================== 8.1 细分流派商业产值与吸金矩阵 ==================")
    genre_data = {}
    for _, row in df.iterrows():
        genres_str = str(row.get("genres", ""))
        if not genres_str or genres_str == "nan":
            continue
        genres = [g.strip() for g in genres_str.split(";") if g.strip()]
        sales = float(row.get("estimated_sales", 0))
        rev = float(row.get("estimated_revenue", 0))
        for g in genres:
            if g not in genre_data:
                genre_data[g] = {"sales": [], "revenue": []}
            genre_data[g]["sales"].append(sales)
            genre_data[g]["revenue"].append(rev)

    results = []
    for g, metrics in genre_data.items():
        count = len(metrics["sales"])
        total_rev = sum(metrics["revenue"])
        total_sales = sum(metrics["sales"])
        median_rev = float(pd.Series(metrics["revenue"]).median()) if count > 0 else 0.0
        avg_rev = total_rev / count if count > 0 else 0.0
        results.append({
            "genre": g,
            "game_count": count,
            "total_revenue": round(total_rev, 2),
            "total_sales": int(total_sales),
            "median_revenue": round(median_rev, 2),
            "avg_revenue": round(avg_rev, 2)
        })

    # 按总流水降序排列
    results.sort(key=lambda x: x["total_revenue"], reverse=True)
    return results[:15]


# 8.2 市场二八定律与长尾垄断格局 (Pareto Principle & Lorenz Curve)
def analyze_pareto_distribution(df):
    print("\n================== 8.2 市场二八定律与长尾垄断分析 ==================")
    if len(df) == 0:
        return {}

    sorted_rev = df["estimated_revenue"].sort_values(ascending=False).values
    total_rev = sorted_rev.sum()
    n = len(sorted_rev)

    # 计算各头部梯队的营收贡献率
    tiers = [
        {"tier": "Top 1%", "pct": 0.01},
        {"tier": "Top 5%", "pct": 0.05},
        {"tier": "Top 10%", "pct": 0.10},
        {"tier": "Top 20%", "pct": 0.20},
        {"tier": "Top 50%", "pct": 0.50},
    ]
    tier_results = []
    for t in tiers:
        k = max(1, int(n * t["pct"]))
        rev_share = (sorted_rev[:k].sum() / total_rev * 100) if total_rev > 0 else 0.0
        tier_results.append({
            "tier": t["tier"],
            "count": k,
            "revenue_share": round(rev_share, 2)
        })

    # 计算基尼系数 (Gini Coefficient)
    asc_rev = np.sort(sorted_rev)
    index = np.arange(1, n + 1)
    if total_rev > 0:
        gini = ((2 * np.sum(index * asc_rev)) / (n * total_rev)) - ((n + 1) / n)
        gini = max(0.0, min(1.0, float(gini)))
    else:
        gini = 0.0

    # 营收分位数生存线 (CNY)
    quantiles = {
        "p25": round(float(df["estimated_revenue"].quantile(0.25)), 2),
        "median": round(float(df["estimated_revenue"].median()), 2),
        "p75": round(float(df["estimated_revenue"].quantile(0.75)), 2),
        "p90": round(float(df["estimated_revenue"].quantile(0.90)), 2),
        "max": round(float(df["estimated_revenue"].max()), 2),
    }

    return {
        "gini_coefficient": round(gini, 4),
        "concentration_tiers": tier_results,
        "quantiles": quantiles
    }


# 8.3 价格—销量弹性与黄金定价区间 (Price-Sales Elasticity)
def analyze_price_elasticity(df):
    print("\n================== 8.3 价格—销量弹性与黄金定价带 ==================")
    tiers_def = [
        ("免费 (0元)", lambda p: p == 0),
        ("低价探索区 (1~20元)", lambda p: 0 < p <= 20),
        ("标准独立区 (21~45元)", lambda p: 20 < p <= 45),
        ("中端进阶区 (46~80元)", lambda p: 45 < p <= 80),
        ("高阶精品区 (81~150元)", lambda p: 80 < p <= 150),
        ("商业3A/溢价区 (>150元)", lambda p: p > 150),
    ]

    results = []
    for label, condition in tiers_def:
        sub = df[df["final_price"].apply(condition)]
        count = len(sub)
        total_rev = float(sub["estimated_revenue"].sum()) if count > 0 else 0.0
        avg_sales = float(sub["estimated_sales"].mean()) if count > 0 else 0.0
        median_sales = float(sub["estimated_sales"].median()) if count > 0 else 0.0
        avg_rev = total_rev / count if count > 0 else 0.0
        results.append({
            "tier_label": label,
            "count": count,
            "avg_sales": int(avg_sales),
            "median_sales": int(median_sales),
            "total_revenue": round(total_rev, 2),
            "avg_revenue": round(avg_rev, 2)
        })

    return results


# 8.4 口碑受众与商业表现的相关性 (Review Sentiment vs Sales Correlation)
def analyze_review_sales_correlation(df):
    print("\n================== 8.4 口碑受众与商业表现的相关性 ==================")
    active = df[df["total_reviews"] > 0].copy()
    if len(active) < 2:
        return {"pearson_corr": 0.0, "spearman_corr": 0.0, "sentiment_tiers": []}

    pearson_corr = float(active["positive_ratio"].corr(active["estimated_sales"], method="pearson"))
    spearman_corr = float(active["positive_ratio"].corr(active["estimated_sales"], method="spearman"))

    # 按好评率区间分层
    sentiment_bins = [
        ("好评如潮 (95%~100%)", lambda r: r >= 95),
        ("特别好评 (80%~94%)", lambda r: 80 <= r < 95),
        ("多半好评 (70%~79%)", lambda r: 70 <= r < 80),
        ("褒贬不一 (40%~69%)", lambda r: 40 <= r < 70),
        ("多半差评 (<40%)", lambda r: r < 40),
    ]

    tier_stats = []
    for label, cond in sentiment_bins:
        sub = active[active["positive_ratio"].apply(cond)]
        count = len(sub)
        avg_sales = float(sub["estimated_sales"].mean()) if count > 0 else 0.0
        median_sales = float(sub["estimated_sales"].median()) if count > 0 else 0.0
        tier_stats.append({
            "tier": label,
            "count": count,
            "avg_sales": int(avg_sales),
            "median_sales": int(median_sales)
        })

    return {
        "pearson_corr": round(pearson_corr, 4) if pd.notna(pearson_corr) else 0.0,
        "spearman_corr": round(spearman_corr, 4) if pd.notna(spearman_corr) else 0.0,
        "sentiment_tiers": tier_stats
    }


# 8.5 研发与发行商业生态格局 (Publishers Tier & Survival Analysis)
def analyze_publisher_tiers(df):
    print("\n================== 8.5 研发与发行商业生态图鉴 ==================")
    # 区分独立自发行与第三方商业发行
    is_self = (df["publishers"].fillna("").astype(str).str.strip().str.lower() ==
               df["developers"].fillna("").astype(str).str.strip().str.lower()) | (df["publishers"] == "")

    self_games = df[is_self]
    pub_games = df[~is_self]

    def get_group_stats(group_df):
        count = len(group_df)
        if count == 0:
            return {"count": 0, "median_revenue": 0.0, "avg_revenue": 0.0, "hit_rate_pct": 0.0}
        hits = (group_df["estimated_sales"] >= 50000).sum()
        return {
            "count": count,
            "median_revenue": round(float(group_df["estimated_revenue"].median()), 2),
            "avg_revenue": round(float(group_df["estimated_revenue"].mean()), 2),
            "hit_rate_pct": round(float(hits / count * 100), 2)
        }

    comparison = {
        "self_published": get_group_stats(self_games),
        "commercial_published": get_group_stats(pub_games)
    }

    # Top 15 发行商总流水排行
    pub_counter = Counter()
    pub_revenue = Counter()
    for _, row in df.iterrows():
        pubs = str(row.get("publishers", ""))
        rev = float(row.get("estimated_revenue", 0))
        for p in pubs.split(";"):
            p = p.strip()
            if p and p.lower() != "nan":
                pub_counter[p] += 1
                pub_revenue[p] += rev

    top_publishers = []
    for pub, total_rev in pub_revenue.most_common(15):
        top_publishers.append({
            "publisher": pub,
            "game_count": pub_counter[pub],
            "total_revenue": round(total_rev, 2)
        })

    return {
        "publishing_mode_comparison": comparison,
        "top_publishers_by_revenue": top_publishers
    }


# =========================
# 保存分析结果为 JSON (供 Flask 后端与 ECharts 使用)
# =========================

def save_analysis_json(summary_data):
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"\n================== 分析结果已全部保存 ==================")
    print(f"聚合统计数据已输出至：{OUTPUT_JSON}（供 Flask API 与前端可视化调用）")


# =========================
# 主程序
# =========================

def main():
    import io
    quiet = "-q" in sys.argv or "--quiet" in sys.argv
    old_stdout = sys.stdout

    if quiet:
        # 静默模式：拦截内部10+个分析函数的冗长表格输出
        sys.stdout = io.StringIO()

    try:
        df = load_clean_data()
        if df is None:
            return

        summary = {
            "total_games": len(df),
            # 第6章：基础描述性分析
            "market_scale": analyze_market_scale(df),
            "genres": analyze_genres(df),
            "prices": analyze_prices(df),
            "discounts": analyze_discounts(df),
            "developers": analyze_developers(df),
            "publishers": analyze_publishers(df),
            "platforms": analyze_platforms(df),
            # 第7章：多维度关联分析
            "genre_price": analyze_genre_price(df),
            "genre_discount": analyze_genre_discount(df),
            "genre_platform": analyze_genre_platform(df),
            "genre_year": analyze_genre_year(df),
            "genre_matrix": analyze_genre_genre_matrix(df),
            # 第8章：数字游戏经济学与商业产值深度分析 (5大商业维度)
            "commercial_genre_revenue": analyze_genre_revenue(df),
            "commercial_pareto": analyze_pareto_distribution(df),
            "commercial_price_elasticity": analyze_price_elasticity(df),
            "commercial_review_sales": analyze_review_sales_correlation(df),
            "commercial_publisher_tiers": analyze_publisher_tiers(df),
        }

        save_analysis_json(summary)
    finally:
        if quiet:
            sys.stdout = old_stdout
            print(f"[成功] 统计分析摘要计算完成，已更新 {OUTPUT_JSON} (覆盖 {len(df)} 款游戏)")


if __name__ == "__main__":
    main()
