import os
import re
import datetime
import pandas as pd


import sys

# 解决 Windows 控制台打印特殊字符编码异常问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =========================
# 文件路径配置
# =========================

import sys

# 支持命令行参数指定输入文件：python data_clean.py [input_file] [output_file]
if len(sys.argv) > 1:
    INPUT_FILE = sys.argv[1]
    OUTPUT_FILE = sys.argv[2] if len(sys.argv) > 2 else INPUT_FILE.replace(".csv", "_clean.csv")
elif os.path.exists("data/steam_games_recent.csv"):
    INPUT_FILE = "data/steam_games_recent.csv"
    OUTPUT_FILE = "data/steam_games_recent_clean.csv"
else:
    INPUT_FILE = "data/steam_games.csv"
    OUTPUT_FILE = "data/steam_games_clean.csv"


# =========================
# 读取数据
# =========================

def load_data():

    if not os.path.exists(INPUT_FILE):
        print(f"找不到文件：{INPUT_FILE}")
        return None

    df = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig"
    )

    print(f"读取原始数据文件：{INPUT_FILE}")
    print(f"原始数据量：{len(df)} 条")

    return df


# =========================
# 4.1 数据基本信息检查
# =========================

def show_basic_info(df):

    print("\n========== 4.1 数据基本信息 ==========")

    print(f"数据总量：{len(df)}")
    print(f"字段数量：{len(df.columns)}")

    print("\n字段列表：")
    for column in df.columns:
        print(f"- {column}")


# =========================
# 4.2 删除重复数据
# =========================

def remove_duplicates(df):

    before = len(df)

    df = df.drop_duplicates(
        subset=["appid"]
    )

    after = len(df)

    print(
        f"\n========== 4.2 重复数据处理 ==========\n"
        f"删除重复 AppID：{before - after} 条"
    )

    return df


# =========================
# 删除 tags 与 metacritic_score 等非必要字段
# =========================

def remove_unwanted_columns(df):

    drop_cols = [c for c in ["tags", "metacritic_score"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
        print(f"\n========== 剔除非必要字段 ==========\n已剔除字段：{', '.join(drop_cols)}")

    return df


# =========================
# 布尔值安全转换
# =========================

def to_bool(value):

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in (
        "true",
        "1",
        "yes",
        "是"
    )


# =========================
# 4.4 处理数据类型
# =========================

def convert_types(df):

    # AppID 转换为数值
    df["appid"] = pd.to_numeric(
        df["appid"],
        errors="coerce"
    )

    # 初始价格
    if "initial_price" in df.columns:
        df["initial_price"] = pd.to_numeric(
            df["initial_price"],
            errors="coerce"
        )

    # 最终价格
    if "final_price" in df.columns:
        df["final_price"] = pd.to_numeric(
            df["final_price"],
            errors="coerce"
        )

    # 折扣百分比
    if "discount_percent" in df.columns:
        df["discount_percent"] = pd.to_numeric(
            df["discount_percent"],
            errors="coerce"
        )

    # 是否免费
    if "is_free" in df.columns:
        df["is_free"] = df["is_free"].map(to_bool)

    # 评论字段数值转换
    for col in ["total_reviews", "total_positive", "total_negative"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        else:
            df[col] = 0

    # Metacritic 评分（若以后需要可启用）
    # if "metacritic_score" in df.columns:
    #     df["metacritic_score"] = pd.to_numeric(
    #         df["metacritic_score"],
    #         errors="coerce"
    #     )

    return df


# =========================
# 4.6 处理日期数据
# =========================

def clean_dates(df):
    """
    严格按照《要求.md》4.6节：
    保留：release_date
    注意：
    - 不删除原始 release_date（绝不使用破坏性的转换，保留原字符串如 '2024 年 2 月 29 日'）
    - 不在清洗阶段强制增加 release_year（后续分析时根据需要从 release_date 提取年份）
    """
    if "release_date" not in df.columns:
        return df

    # 清洗首尾空白字符，保留原始日期字符串
    df["release_date"] = (
        df["release_date"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # 清除无效字符串表示
    df.loc[
        df["release_date"].str.lower().isin(["nan", "none", "nat"]),
        "release_date"
    ] = ""

    # 严格确保清洗阶段不产生 release_year 字段
    if "release_year" in df.columns:
        df = df.drop(columns=["release_year"])

    return df


# =========================
# 4.5 清理文本字段
# =========================

def clean_text(df):

    text_columns = [
        "name",
        "type",
        "release_date",
        "developers",
        "publishers",
        "genres",
        "categories",
        "platforms",
        "currency"
    ]

    for column in text_columns:

        if column not in df.columns:
            continue

        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        df.loc[
            df[column].str.lower().isin(["nan", "none"]),
            column
        ] = ""

    return df


# =========================
# 4.3 处理缺失值
# =========================

def handle_missing_values(df):

    print("\n========== 4.3 缺失值检查 ==========")

    check_columns = [
        "name",
        "release_date",
        "developers",
        "publishers",
        "genres",
        "categories",
        "platforms",
        "currency"
    ]

    for column in check_columns:
        if column in df.columns:
            missing_count = (
                df[column].isna()
                | (df[column].astype(str).str.strip() == "")
            ).sum()
            if missing_count > 0:
                print(f"- {column}: {missing_count} 条缺失")

    # 核心字段缺失处理原则：游戏名称缺失的数据无法使用，直接删除
    if "name" in df.columns:
        before = len(df)
        df = df[
            df["name"].notna()
            & (df["name"].astype(str).str.strip() != "")
        ]
        print(f"删除无游戏名称核心数据：{before - len(df)} 条")

    return df


# =========================
# 4.7 处理价格与 4.8 折扣异常
# =========================

def clean_prices(df):

    # 价格不能小于 0
    if "initial_price" in df.columns:
        df.loc[
            df["initial_price"] < 0,
            "initial_price"
        ] = None

    if "final_price" in df.columns:
        df.loc[
            df["final_price"] < 0,
            "final_price"
        ] = None

    # 折扣正常范围：0% ~ 100%
    if "discount_percent" in df.columns:
        df.loc[
            (df["discount_percent"] < 0)
            | (df["discount_percent"] > 100),
            "discount_percent"
        ] = None

    return df


# =========================
# 4.7 统一免费游戏价格
# =========================

def clean_free_games(df):

    if "is_free" not in df.columns:
        return df

    free_games = df["is_free"] == True

    if "initial_price" in df.columns:
        df.loc[free_games, "initial_price"] = 0.0

    if "final_price" in df.columns:
        df.loc[free_games, "final_price"] = 0.0

    if "discount_percent" in df.columns:
        df.loc[free_games, "discount_percent"] = 0.0

    return df


# =========================
# 删除无法用于分析的无效数据
# =========================

def remove_invalid_data(df):

    before = len(df)

    # 必须有合法 AppID
    df = df[
        df["appid"].notna() & (df["appid"] > 0)
    ].copy()
    df["appid"] = df["appid"].astype(int)

    # 必须有发售日期
    if "release_date" in df.columns:
        has_date = (
            df["release_date"]
            .fillna("")
            .astype(str)
            .str.strip() != ""
        )
        df = df[has_date]

    # 必须是游戏
    if "type" in df.columns:
        df = df[
            df["type"].str.lower() == "game"
        ]

    print(
        f"\n========== 删除无效数据 ==========\n"
        f"删除无效数据：{before - len(df)} 条"
    )

    return df


# =========================
# 4.8 评论治理与 Boxleiter 销量模型测算
# =========================

def calculate_sales_metrics(df):
    """
    基于数字游戏经济学公认的 Boxleiter 评论乘数模型构建销量与流水衍生指标：
    1. 评论数据清洗与纠偏：确保非负，好评数与差评数逻辑闭环
    2. 计算好评率 positive_ratio (%)
    3. 测算预估销量 estimated_sales：
       - 付费游戏乘数 M = 30（Jake Birkett / VGInsights 中位数经验值）
       - 免费游戏乘数 M = 60（免费玩家评论转化率通常约为付费玩家的一半）
    4. 测算预估总流水 estimated_revenue（CNY）：
       - 免费游戏基础销售流水计 0
       - 付费游戏按折后实际售价 final_price 测算商业现金流
    """
    # 1. 确保评论字段均为非负整数
    for col in ["total_reviews", "total_positive", "total_negative"]:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = df[col].fillna(0).clip(lower=0).astype(int)

    # 2. 纠偏：若 total_reviews 小于好评+差评之和，则按两者之和校准
    sum_reviews = df["total_positive"] + df["total_negative"]
    df["total_reviews"] = df["total_reviews"].clip(lower=sum_reviews)

    # 3. 计算好评率 positive_ratio (0.0% ~ 100.0%)
    df["positive_ratio"] = 0.0
    has_reviews = df["total_reviews"] > 0
    df.loc[has_reviews, "positive_ratio"] = (
        (df.loc[has_reviews, "total_positive"] / df.loc[has_reviews, "total_reviews"]) * 100
    ).round(2)

    # 4. Boxleiter 评论乘数估算销量 (份)
    # 付费游戏 M=30，免费游戏 M=60
    multiplier = df["is_free"].apply(lambda is_free: 60 if is_free else 30)
    df["estimated_sales"] = (df["total_reviews"] * multiplier).astype(int)

    # 5. 测算折后预估商业流水 (CNY)
    df["estimated_revenue"] = 0.0
    paid_mask = (~df["is_free"]) & (df["final_price"] > 0)
    df.loc[paid_mask, "estimated_revenue"] = (
        df.loc[paid_mask, "estimated_sales"] * df.loc[paid_mask, "final_price"]
    ).round(2)

    return df


# =========================
# 调整字段顺序 (严格排除 tags 与 release_year)
# =========================

def reorder_columns(df):

    columns = [
        "appid",
        "name",
        "type",
        "release_date",
        "developers",
        "publishers",
        "genres",
        "categories",
        "platforms",
        "is_free",
        "initial_price",
        "final_price",
        "discount_percent",
        "currency",
        "total_reviews",
        "total_positive",
        "total_negative",
        "positive_ratio",
        "estimated_sales",
        "estimated_revenue",
    ]

    columns = [
        col for col in columns
        if col in df.columns
    ]

    return df[columns]


# =========================
# 保存清洗后数据
# =========================

def save_data(df):

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"\n========== 保存清洗结果 ==========\n"
        f"清洗完成，保存到：{OUTPUT_FILE}\n"
        f"最终清洗后数据量：{len(df)} 条"
    )


# =========================
# 主程序
# =========================

def main():

    df = load_data()

    if df is None:
        return

    # 1. 基本信息检查
    show_basic_info(df)

    # 2. 删除重复 AppID
    df = remove_duplicates(df)

    # 3. 剔除 tags 与 metacritic_score 等非必要字段
    df = remove_unwanted_columns(df)

    # 4. 数据类型转换
    df = convert_types(df)

    # 5. 日期处理（严格保留 release_date 原始字符串，不增加 release_year）
    df = clean_dates(df)

    # 6. 文本清理
    df = clean_text(df)

    # 7. 缺失值检查与处理
    df = handle_missing_values(df)

    # 8. 价格与折扣异常处理
    df = clean_prices(df)

    # 9. 免费游戏价格统一
    df = clean_free_games(df)

    # 10. 删除明显无效数据
    df = remove_invalid_data(df)

    # 11. 评论治理与 Boxleiter 销量与流水建模
    df = calculate_sales_metrics(df)

    # 12. 调整字段顺序（确保无 tags、无 release_year，包含销量与流水字段）
    df = reorder_columns(df)

    # 13. 保存清洗后数据
    save_data(df)


if __name__ == "__main__":
    main()