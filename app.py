"""
Steam 游戏市场数据分析 - Flask 后端核心服务
根据《要求.md》第 9 章实现，提供数据查询、统计分析 RESTful API 接口，并挂载可视化看板。
支持【双模自适应架构】：
  1. MySQL 数据库模式（优先连接 1Panel / 本地 MySQL 服务）
  2. 本地文件容灾模式（MySQL 未配置或断开时，自动降级读取本地 CSV 与 analysis_summary.json，保证零崩溃）
"""

import os
import sys
import json
import math
import argparse
import traceback
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, render_template_string

# 加载 .env 环境变量
load_dotenv()

# ========================================================
# 基础配置
# ========================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据文件路径
CSV_PATH = os.path.join(APP_DIR, "data", "steam_games_recent_clean.csv")
if not os.path.exists(CSV_PATH):
    CSV_PATH = os.path.join(APP_DIR, "data", "steam_games_clean.csv")

SUMMARY_JSON_PATH = os.path.join(APP_DIR, "data", "analysis_summary.json")
CHARTS_DIR = os.path.join(APP_DIR, "charts")

# MySQL 配置（从 .env 读取）
MYSQL_HOST = os.getenv("MYSQL_HOST", "").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306").strip() or 3306)
MYSQL_USER = os.getenv("MYSQL_USER", "root").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "").strip()
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "steam_db").strip()
MYSQL_TABLE = os.getenv("MYSQL_TABLE", "steam_games").strip()

# 初始化 Flask 应用
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 支持中文直接显示


# ========================================================
# 跨域支持 (CORS) 与 通用响应封装
# ========================================================

@app.after_request
def add_cors_headers(response):
    """为所有响应添加 CORS 跨域头，支持前后端分离调用"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def make_response(data=None, code=200, message="success"):
    """统一 JSON 响应格式"""
    return jsonify({
        "code": code,
        "message": message,
        "data": data
    }), code


# ========================================================
# 数据库管理模块 (MySQL Manager)
# ========================================================

class MySQLManager:
    """负责 MySQL 的连接、建库、建表、数据同步与动态查询"""

    def __init__(self):
        self.available = False
        self._check_connection()

    def get_connection(self, select_db=True):
        """获取 MySQL 数据库连接"""
        if not MYSQL_HOST:
            return None
        try:
            import pymysql
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE if select_db else None,
                charset="utf8mb4",
                connect_timeout=3,
                cursorclass=pymysql.cursors.DictCursor
            )
            return conn
        except Exception:
            return None

    def _check_connection(self):
        """测试数据库是否可连通"""
        if not MYSQL_HOST:
            self.available = False
            return False
        conn = self.get_connection(select_db=False)
        if conn:
            self.available = True
            conn.close()
            return True
        else:
            self.available = False
            return False

    def init_database(self):
        """初始化数据库与数据表"""
        conn = self.get_connection(select_db=False)
        if not conn:
            raise ConnectionError(f"无法连接到 MySQL 服务器 ({MYSQL_HOST}:{MYSQL_PORT})，请检查 IP 与密码配置。")

        try:
            with conn.cursor() as cursor:
                # 1. 创建数据库
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                cursor.execute(f"USE `{MYSQL_DATABASE}`;")

                # 2. 创建 14 字段清洗后的数据表（严格对齐清洗结构）
                create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS `{MYSQL_TABLE}` (
                    `appid` BIGINT NOT NULL COMMENT 'Steam 游戏唯一标识',
                    `name` VARCHAR(255) NOT NULL COMMENT '游戏名称',
                    `type` VARCHAR(50) DEFAULT 'game' COMMENT '应用类型',
                    `release_date` VARCHAR(100) DEFAULT '' COMMENT '原始发行日期',
                    `developers` TEXT COMMENT '开发商列表(逗号分隔)',
                    `publishers` TEXT COMMENT '发行商列表(逗号分隔)',
                    `genres` TEXT COMMENT '类型分类(逗号分隔)',
                    `categories` TEXT COMMENT '功能标签(逗号分隔)',
                    `platforms` VARCHAR(100) DEFAULT '' COMMENT '支持平台(windows,mac,linux)',
                    `is_free` TINYINT(1) DEFAULT 0 COMMENT '是否免费(0付费,1免费)',
                    `initial_price` DECIMAL(10, 2) DEFAULT 0.00 COMMENT '原价(CNY)',
                    `final_price` DECIMAL(10, 2) DEFAULT 0.00 COMMENT '折后售价(CNY)',
                    `discount_percent` INT DEFAULT 0 COMMENT '折扣百分比',
                    `currency` VARCHAR(10) DEFAULT 'CNY' COMMENT '货币单位',
                    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '数据录入时间',
                    PRIMARY KEY (`appid`),
                    INDEX `idx_release_date` (`release_date`(30)),
                    INDEX `idx_is_free` (`is_free`),
                    INDEX `idx_final_price` (`final_price`),
                    INDEX `idx_discount` (`discount_percent`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Steam 清洗后游戏数据表';
                """
                cursor.execute(create_table_sql)
            conn.commit()
            self.available = True
            return True
        finally:
            conn.close()

    def sync_from_csv(self, csv_file_path=None):
        """将清洗后的 CSV 文件全量导入/更新到 MySQL 数据库中"""
        file_path = csv_file_path or CSV_PATH
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"找不到清洗后的数据文件：{file_path}，无法导入到 MySQL！")

        import pandas as pd
        df = pd.read_csv(file_path, encoding="utf-8-sig")

        # 确保数据库表已建好
        self.init_database()

        conn = self.get_connection(select_db=True)
        if not conn:
            raise ConnectionError("数据库连接失败")

        upsert_sql = f"""
        INSERT INTO `{MYSQL_TABLE}` (
            appid, name, type, release_date, developers, publishers, genres,
            categories, platforms, is_free, initial_price, final_price,
            discount_percent, currency
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name),
            type=VALUES(type),
            release_date=VALUES(release_date),
            developers=VALUES(developers),
            publishers=VALUES(publishers),
            genres=VALUES(genres),
            categories=VALUES(categories),
            platforms=VALUES(platforms),
            is_free=VALUES(is_free),
            initial_price=VALUES(initial_price),
            final_price=VALUES(final_price),
            discount_percent=VALUES(discount_percent),
            currency=VALUES(currency);
        """

        rows = []
        for _, r in df.iterrows():
            appid = int(r["appid"])
            name = str(r["name"]) if pd.notna(r["name"]) else ""
            g_type = str(r["type"]) if pd.notna(r["type"]) else "game"
            rel_date = str(r["release_date"]) if pd.notna(r["release_date"]) else ""
            devs = str(r["developers"]) if pd.notna(r["developers"]) else ""
            pubs = str(r["publishers"]) if pd.notna(r["publishers"]) else ""
            genres = str(r["genres"]) if pd.notna(r["genres"]) else ""
            cats = str(r["categories"]) if pd.notna(r["categories"]) else ""
            plats = str(r["platforms"]) if pd.notna(r["platforms"]) else ""
            is_free = 1 if bool(r["is_free"]) else 0
            init_price = float(r["initial_price"]) if pd.notna(r["initial_price"]) else 0.0
            fin_price = float(r["final_price"]) if pd.notna(r["final_price"]) else 0.0
            disc = int(r["discount_percent"]) if pd.notna(r["discount_percent"]) else 0
            curr = str(r["currency"]) if pd.notna(r["currency"]) else "CNY"

            rows.append((
                appid, name, g_type, rel_date, devs, pubs, genres,
                cats, plats, is_free, init_price, fin_price, disc, curr
            ))

        total_inserted = 0
        batch_size = 500
        try:
            with conn.cursor() as cursor:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    cursor.executemany(upsert_sql, batch)
                    total_inserted += len(batch)
            conn.commit()
            return total_inserted
        finally:
            conn.close()

    def get_games_count(self):
        """获取数据库中游戏总数"""
        conn = self.get_connection()
        if not conn:
            return 0
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{MYSQL_TABLE}`;")
                res = cursor.fetchone()
                return res["total"] if res else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def query_games_list(self, page=1, page_size=10, keyword=None, genre=None, is_free=None, sort_by=None, order="desc"):
        """动态分页与条件查询游戏列表"""
        conn = self.get_connection()
        if not conn:
            return None

        where_clauses = ["1=1"]
        params = []

        if keyword:
            where_clauses.append("(`name` LIKE %s OR `developers` LIKE %s OR `publishers` LIKE %s)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])

        if genre:
            where_clauses.append("`genres` LIKE %s")
            params.append(f"%{genre}%")

        if is_free is not None:
            where_clauses.append("`is_free` = %s")
            params.append(1 if int(is_free) == 1 else 0)

        where_sql = " AND ".join(where_clauses)

        # 安全防注入的排序字段白名单
        valid_sort_fields = {"appid", "initial_price", "final_price", "discount_percent"}
        safe_sort = sort_by if sort_by in valid_sort_fields else "appid"
        safe_order = "ASC" if order.lower() == "asc" else "DESC"

        offset = (page - 1) * page_size

        try:
            with conn.cursor() as cursor:
                # 查总数
                count_sql = f"SELECT COUNT(*) AS total FROM `{MYSQL_TABLE}` WHERE {where_sql};"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()["total"]

                # 查分页数据
                query_sql = f"""
                SELECT appid, name, type, release_date, developers, publishers,
                       genres, categories, platforms, is_free, initial_price,
                       final_price, discount_percent, currency
                FROM `{MYSQL_TABLE}`
                WHERE {where_sql}
                ORDER BY `{safe_sort}` {safe_order}
                LIMIT %s OFFSET %s;
                """
                cursor.execute(query_sql, params + [page_size, offset])
                items = cursor.fetchall()

                # 数据类型微调
                for item in items:
                    item["is_free"] = bool(item["is_free"])
                    item["initial_price"] = float(item["initial_price"])
                    item["final_price"] = float(item["final_price"])

                return {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": math.ceil(total / page_size) if total > 0 else 1,
                    "items": items
                }
        finally:
            conn.close()


# ========================================================
# 本地缓存与容灾数据管理器 (Local Fallback Manager)
# ========================================================

class LocalDataManager:
    """当 MySQL 未启用时，读取本地 analysis_summary.json 与 CSV 作为容灾备份"""

    def __init__(self):
        self._summary_cache = None
        self._summary_mtime = 0
        self._df_cache = None
        self._df_mtime = 0

    def get_summary(self):
        """读取 analysis.py 生成的预计算统计结果"""
        if not os.path.exists(SUMMARY_JSON_PATH):
            return {}
        mtime = os.path.getmtime(SUMMARY_JSON_PATH)
        if self._summary_cache is None or mtime > self._summary_mtime:
            with open(SUMMARY_JSON_PATH, "r", encoding="utf-8") as f:
                self._summary_cache = json.load(f)
            self._summary_mtime = mtime
        return self._summary_cache

    def get_dataframe(self):
        """读取清洗后的 CSV 数据集"""
        if not os.path.exists(CSV_PATH):
            return None
        mtime = os.path.getmtime(CSV_PATH)
        if self._df_cache is None or mtime > self._df_mtime:
            import pandas as pd
            self._df_cache = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
            self._df_mtime = mtime
        return self._df_cache

    def query_games_list(self, page=1, page_size=10, keyword=None, genre=None, is_free=None, sort_by=None, order="desc"):
        """本地 Pandas 内存条件查询与分页"""
        df = self.get_dataframe()
        if df is None:
            return {"total": 0, "page": page, "page_size": page_size, "total_pages": 0, "items": []}

        sub_df = df.copy()

        if keyword:
            kw = keyword.lower()
            mask = (
                sub_df["name"].astype(str).str.lower().str.contains(kw, na=False) |
                sub_df["developers"].astype(str).str.lower().str.contains(kw, na=False) |
                sub_df["publishers"].astype(str).str.lower().str.contains(kw, na=False)
            )
            sub_df = sub_df[mask]

        if genre:
            sub_df = sub_df[sub_df["genres"].astype(str).str.contains(genre, na=False)]

        if is_free is not None:
            target_free = (int(is_free) == 1)
            sub_df = sub_df[sub_df["is_free"].astype(bool) == target_free]

        valid_sort_fields = {"appid", "initial_price", "final_price", "discount_percent"}
        if sort_by in valid_sort_fields:
            ascending = (order.lower() == "asc")
            sub_df = sub_df.sort_values(by=sort_by, ascending=ascending)

        total = len(sub_df)
        offset = (page - 1) * page_size
        paged_df = sub_df.iloc[offset:offset + page_size]

        items = []
        for _, row in paged_df.iterrows():
            items.append({
                "appid": int(row["appid"]),
                "name": str(row["name"]) if str(row["name"]) != "nan" else "",
                "type": str(row["type"]) if str(row["type"]) != "nan" else "game",
                "release_date": str(row["release_date"]) if str(row["release_date"]) != "nan" else "",
                "developers": str(row["developers"]) if str(row["developers"]) != "nan" else "",
                "publishers": str(row["publishers"]) if str(row["publishers"]) != "nan" else "",
                "genres": str(row["genres"]) if str(row["genres"]) != "nan" else "",
                "categories": str(row["categories"]) if str(row["categories"]) != "nan" else "",
                "platforms": str(row["platforms"]) if str(row["platforms"]) != "nan" else "",
                "is_free": bool(row["is_free"]),
                "initial_price": float(row["initial_price"]) if str(row["initial_price"]) != "nan" else 0.0,
                "final_price": float(row["final_price"]) if str(row["final_price"]) != "nan" else 0.0,
                "discount_percent": int(row["discount_percent"]) if str(row["discount_percent"]) != "nan" else 0,
                "currency": str(row["currency"]) if str(row["currency"]) != "nan" else "CNY"
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total > 0 else 1,
            "items": items
        }


# 全局单例
db_mgr = MySQLManager()
local_mgr = LocalDataManager()


# ========================================================
# 路由 1：系统与数据库状态健康检查
# ========================================================

@app.route("/api/system/status", methods=["GET"])
def get_system_status():
    """获取系统运行状态与数据库连接情况"""
    is_mysql = db_mgr._check_connection()
    db_count = db_mgr.get_games_count() if is_mysql else 0
    df = local_mgr.get_dataframe()
    local_count = len(df) if df is not None else 0

    return make_response({
        "status": "online",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active_mode": "mysql" if is_mysql else "local_fallback",
        "mysql": {
            "connected": is_mysql,
            "host": MYSQL_HOST or "未配置",
            "port": MYSQL_PORT,
            "database": MYSQL_DATABASE,
            "table": MYSQL_TABLE,
            "records_in_table": db_count
        },
        "local_storage": {
            "csv_file": os.path.basename(CSV_PATH) if os.path.exists(CSV_PATH) else None,
            "csv_records": local_count,
            "summary_json_exists": os.path.exists(SUMMARY_JSON_PATH)
        }
    })


# ========================================================
# 路由 2：9.3 API 市场概况接口 (/api/games/overview)
# ========================================================

@app.route("/api/games/overview", methods=["GET"])
def get_games_overview():
    """《要求.md》9.3: 获取市场宏观概览统计"""
    summary = local_mgr.get_summary()
    total_games = summary.get("total_games", 0)
    prices = summary.get("prices", {})
    stats = prices.get("stats", {})
    discounts = summary.get("discounts", {})

    total_discounted = discounts.get("low_discount", 0) + discounts.get("mid_discount", 0) + discounts.get("high_discount", 0)
    discount_rate = round(total_discounted / total_games * 100, 2) if total_games > 0 else 0

    top_genre = summary.get("genres", [{}])[0].get("genre", "暂无") if summary.get("genres") else "暂无"

    overview_data = {
        "total_games": total_games,
        "free_count": prices.get("free_count", 0),
        "paid_count": prices.get("paid_count", 0),
        "free_ratio": round(prices.get("free_count", 0) / total_games * 100, 2) if total_games > 0 else 0,
        "price_stats": {
            "mean_price": stats.get("mean", 0.0),
            "median_price": stats.get("median", 0.0),
            "min_price": stats.get("min", 0.0),
            "max_price": stats.get("max", 0.0)
        },
        "discount_summary": {
            "discounted_games": total_discounted,
            "discount_rate": discount_rate,
            "no_discount_games": discounts.get("no_discount", 0)
        },
        "top_genre": top_genre,
        "platforms_summary": summary.get("platforms", {}),
        "source": "mysql" if db_mgr.available else "local_analysis_cache"
    }

    return make_response(overview_data)


# ========================================================
# 路由 3：9.3 API 年度发行走势 (/api/games/year)
# ========================================================

@app.route("/api/games/year", methods=["GET"])
def get_games_by_year():
    """《要求.md》9.3: 获取各年份发行数量走势数据 (用于折线图)"""
    summary = local_mgr.get_summary()
    data = summary.get("market_scale", [])
    return make_response(data)


# ========================================================
# 路由 4：9.3 API 游戏类型分布 (/api/games/genres)
# ========================================================

@app.route("/api/games/genres", methods=["GET"])
def get_games_genres():
    """《要求.md》9.3: 获取游戏类型排名与分布 (用于柱状图)"""
    limit = request.args.get("limit", default=None, type=int)
    summary = local_mgr.get_summary()
    data = summary.get("genres", [])
    if limit and limit > 0:
        data = data[:limit]
    return make_response(data)


# ========================================================
# 路由 5：9.3 API 价格分布与统计 (/api/games/prices)
# ========================================================

@app.route("/api/games/prices", methods=["GET"])
def get_games_prices():
    """《要求.md》9.3: 获取游戏价格区间分布与统测量 (用于直方图/饼图)"""
    summary = local_mgr.get_summary()
    data = summary.get("prices", {})
    return make_response(data)


# ========================================================
# 路由 6：9.3 API 操作系统平台支持 (/api/games/platforms)
# ========================================================

@app.route("/api/games/platforms", methods=["GET"])
def get_games_platforms():
    """《要求.md》9.3: 获取 Windows / Mac / Linux 及多平台支持情况 (用于饼图)"""
    summary = local_mgr.get_summary()
    data = summary.get("platforms", {})
    return make_response(data)


# ========================================================
# 路由 7：9.3 API 热门开发商排行 (/api/games/developers)
# ========================================================

@app.route("/api/games/developers", methods=["GET"])
def get_games_developers():
    """《要求.md》9.3: 获取开发商作品数量 TOP 排行"""
    limit = request.args.get("limit", default=10, type=int)
    summary = local_mgr.get_summary()
    data = summary.get("developers", [])
    if limit and limit > 0:
        data = data[:limit]
    return make_response(data)


# ========================================================
# 路由 8：9.3 API 热门发行商排行 (/api/games/publishers)
# ========================================================

@app.route("/api/games/publishers", methods=["GET"])
def get_games_publishers():
    """《要求.md》9.3: 获取发行商作品数量 TOP 排行"""
    limit = request.args.get("limit", default=10, type=int)
    summary = local_mgr.get_summary()
    data = summary.get("publishers", [])
    if limit and limit > 0:
        data = data[:limit]
    return make_response(data)


# ========================================================
# 路由 9：折扣特征分布 (/api/games/discounts)
# ========================================================

@app.route("/api/games/discounts", methods=["GET"])
def get_games_discounts():
    """获取无折扣、低、中、高折扣分布比例 (用于直方图)"""
    summary = local_mgr.get_summary()
    data = summary.get("discounts", {})
    return make_response(data)


# ========================================================
# 路由 10：第 7 章关联分析综合接口 (/api/games/correlations)
# ========================================================

@app.route("/api/games/correlations", methods=["GET"])
def get_games_correlations():
    """
    《要求.md》第 7 章: 关联分析数据
    参数 type: 可选 genre_price, genre_discount, genre_platform, genre_year, genre_matrix
    """
    corr_type = request.args.get("type", default="all", type=str)
    summary = local_mgr.get_summary()

    mapping = {
        "genre_price": summary.get("genre_price", []),
        "genre_discount": summary.get("genre_discount", []),
        "genre_platform": summary.get("genre_platform", []),
        "genre_year": summary.get("genre_year", {}),
        "genre_matrix": summary.get("genre_matrix", {})
    }

    if corr_type in mapping:
        return make_response(mapping[corr_type])
    else:
        return make_response(mapping)


# ========================================================
# 路由 11：游戏列表动态搜索与分页接口 (/api/games/list)
# ========================================================

@app.route("/api/games/list", methods=["GET"])
def get_games_list():
    """
    游戏详情列表查询，支持关键词搜索、类型过滤、免费过滤与排序
    Query 参数:
      - page: 页码 (默认 1)
      - page_size: 每页数量 (默认 10，最大 100)
      - keyword: 搜索名称、开发商或发行商
      - genre: 游戏类型过滤 (例如 "动作")
      - is_free: 1 (免费) 或 0 (付费)
      - sort_by: appid, initial_price, final_price, discount_percent
      - order: desc / asc
    """
    page = max(1, request.args.get("page", default=1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", default=10, type=int)))
    keyword = request.args.get("keyword", default=None, type=str)
    genre = request.args.get("genre", default=None, type=str)
    is_free = request.args.get("is_free", default=None)
    sort_by = request.args.get("sort_by", default="appid", type=str)
    order = request.args.get("order", default="desc", type=str)

    # 优先从 MySQL 查询
    if db_mgr.available:
        try:
            res = db_mgr.query_games_list(page, page_size, keyword, genre, is_free, sort_by, order)
            if res:
                return make_response(res)
        except Exception as e:
            print(f"[警告] MySQL 查询失败，降级为本地数据：{e}")

    # 降级从本地 Pandas 缓存查询
    res = local_mgr.query_games_list(page, page_size, keyword, genre, is_free, sort_by, order)
    return make_response(res)


# ========================================================
# 路由 12：单个游戏详情接口 (/api/games/<appid>)
# ========================================================

@app.route("/api/games/<int:appid>", methods=["GET"])
def get_game_detail(appid):
    """根据 AppID 获取特定游戏详细数据"""
    # 优先查 MySQL
    if db_mgr.available:
        conn = db_mgr.get_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT * FROM `{MYSQL_TABLE}` WHERE appid = %s LIMIT 1;", (appid,))
                    row = cursor.fetchone()
                    if row:
                        row["is_free"] = bool(row["is_free"])
                        row["initial_price"] = float(row["initial_price"])
                        row["final_price"] = float(row["final_price"])
                        return make_response(row)
            finally:
                conn.close()

    # 降级查本地 CSV
    df = local_mgr.get_dataframe()
    if df is not None:
        matched = df[df["appid"] == appid]
        if not matched.empty:
            row = matched.iloc[0].to_dict()
            return make_response({k: (None if str(v) == "nan" else v) for k, v in row.items()})

    return make_response(None, code=404, message=f"未找到 AppID 为 {appid} 的游戏数据")


# ========================================================
# 路由 13：手动同步数据到 MySQL (/api/db/sync)
# ========================================================

@app.route("/api/db/sync", methods=["POST"])
def sync_to_db():
    """手动触发：将清洗后的 CSV 数据同步导入到 MySQL 数据库中"""
    if not db_mgr.available and not db_mgr._check_connection():
        return make_response(None, code=500, message=f"无法连接 MySQL ({MYSQL_HOST}:{MYSQL_PORT})，请先配置 .env")

    try:
        count = db_mgr.sync_from_csv()
        return make_response({"synced_rows": count}, message=f"成功将 {count} 条数据同步至 MySQL 表 `{MYSQL_TABLE}`")
    except Exception as e:
        return make_response(None, code=500, message=f"数据同步失败：{str(e)}")


# ========================================================
# 路由 14：挂载前端可视化看板页面 (GET / 或 GET /dashboard)
# ========================================================

@app.route("/", methods=["GET"])
@app.route("/system", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
def serve_dashboard():
    """展示依据 design.md 架构规范构建的系统化 Google Labs 界面 (templates/system.html)"""
    system_file = os.path.join(APP_DIR, "templates", "system.html")
    if os.path.exists(system_file):
        return send_from_directory(os.path.join(APP_DIR, "templates"), "system.html")

    template_file = os.path.join(APP_DIR, "templates", "index.html")
    if os.path.exists(template_file):
        return send_from_directory(os.path.join(APP_DIR, "templates"), "index.html")

    dashboard_file = os.path.join(CHARTS_DIR, "steam_dashboard.html")
    if os.path.exists(dashboard_file):
        return send_from_directory(CHARTS_DIR, "steam_dashboard.html")
    else:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head><title>Steam 游戏市场分析系统后端</title></head>
        <body style="font-family: sans-serif; padding: 40px; background: #0f172a; color: #e2e8f0;">
            <h1 style="color: #38bdf8;">Steam 游戏数据分析后端已正常启动！</h1>
            <p>仪表盘页面尚未生成，请检查 templates/ 目录。</p>
        </body>
        </html>
        """)


@app.route("/labs", methods=["GET"])
def serve_labs_dashboard():
    """展示 Google Labs 浅色多巴胺原型版本 (templates/labs.html)"""
    labs_file = os.path.join(APP_DIR, "templates", "labs.html")
    if os.path.exists(labs_file):
        return send_from_directory(os.path.join(APP_DIR, "templates"), "labs.html")
    return serve_dashboard()


@app.route("/dark", methods=["GET"])
def serve_dark_dashboard():
    """展示保留的第一套深色极客控制台 (templates/index.html)"""
    dark_file = os.path.join(APP_DIR, "templates", "index.html")
    if os.path.exists(dark_file):
        return send_from_directory(os.path.join(APP_DIR, "templates"), "index.html")
    return serve_dashboard()


@app.route("/genz", methods=["GET"])
def serve_genz_dashboard():
    """展示依据 design.md 规范构建的 Gen Z Chaos / Maximalism 极繁潮流赛博界面 (templates/genz.html)"""
    genz_file = os.path.join(APP_DIR, "templates", "genz.html")
    if os.path.exists(genz_file):
        return send_from_directory(os.path.join(APP_DIR, "templates"), "genz.html")
    return serve_dashboard()


# ========================================================
# 命令行维护指令与主程序启动
# ========================================================

def cli():
    """命令行参数解析"""
    parser = argparse.ArgumentParser(description="Steam 游戏市场数据分析 - Flask 后端")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="监听端口 (默认 5000)")
    parser.add_argument("--init-db", action="store_true", help="初始化 MySQL 数据库与数据表结构")
    parser.add_argument("--sync-db", action="store_true", help="将清洗后的 CSV 文件同步导入 MySQL 数据库")
    args = parser.parse_args()

    if args.init_db:
        print("[操作] 正在初始化 MySQL 数据库结构...")
        try:
            db_mgr.init_database()
            print(f"[成功] 数据库 `{MYSQL_DATABASE}` 及表 `{MYSQL_TABLE}` 初始化完成！")
        except Exception as e:
            print(f"[错误] 初始化数据库失败：{e}")
        return

    if args.sync_db:
        print(f"[操作] 正在从 {CSV_PATH} 同步数据至 MySQL...")
        try:
            count = db_mgr.sync_from_csv()
            print(f"[成功] 成功同步 {count} 款游戏至数据库！")
        except Exception as e:
            print(f"[错误] 同步数据失败：{e}")
        return

    # 启动前状态提示
    print("=" * 60)
    print("★ Steam 电子游戏市场研究 - Flask RESTful 后端服务启动")
    print(f"★ 监听地址: http://{args.host}:{args.port}")
    if db_mgr.available:
        print(f"★ 数据模式: 【MySQL 数据库模式】 (主机: {MYSQL_HOST}:{MYSQL_PORT})")
    else:
        print(f"★ 数据模式: 【本地文件容灾模式】 (已加载本地 CSV / JSON 数据)")
        if not MYSQL_HOST:
            print("  (提示: 若需连接 MySQL，请在 .env 中配置 MYSQL_HOST 等参数)")
    print("=" * 60)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    cli()
