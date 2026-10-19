import os
import re
import json
import pandas as pd
from collections import Counter


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
        "genre_matrix": analyze_genre_genre_matrix(df)
    }

    save_analysis_json(summary)


if __name__ == "__main__":
    main()
