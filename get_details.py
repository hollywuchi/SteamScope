import os
import re
import csv
import json
import time
import datetime
import threading
import requests
import sys
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# 解决 Windows 控制台打印特殊字符编码异常问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

# =========================
# 配置
# =========================

load_dotenv()

API_KEY = os.getenv("STEAM_API_KEY")

APPID_FILE = "data/appids_recent.json"
STATE_FILE = "data/details_recent_state.json"
CSV_FILE = "data/steam_games_recent.csv"

# 0 = 不限制
if len(sys.argv) > 1 and sys.argv[1].isdigit():
    MAX_DETAILS = int(sys.argv[1])
else:
    MAX_DETAILS = int(os.getenv("MAX_DETAILS", "0"))

# 每个请求之间的间隔（秒），所有线程共用这个节奏
# Steam 大约只允许每秒 1~2 个请求，调太小会被限流
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0.5"))

# 并发线程数，1 = 一个一个慢慢来
# 线程只用来"等网络"，真正的快慢由 REQUEST_INTERVAL 决定
THREADS = int(os.getenv("THREADS", "3"))

# 一次给线程池多少任务（比线程数大，线程才不会空等）
CHUNK_SIZE = max(THREADS * 4, 1)

# 被限流（HTTP 429）之后，全场暂停多少秒
COOLDOWN = float(os.getenv("COOLDOWN", "30"))

# 被限流最多重试多少次
RATE_RETRY = int(os.getenv("RATE_RETRY", "10"))

# 只保留最近 N 年内发行的游戏
RECENT_YEARS = int(os.getenv("RECENT_YEARS", "3"))

# 也可以直接写死起始日期，留空则用 RECENT_YEARS 计算
DATE_FROM_ENV = os.getenv("DATE_FROM", "").strip()

# 请求失败重试
RETRY_TIMES = 3
RETRY_WAIT = 5

# 每处理多少个打印一次进度
PROGRESS_EVERY = 500

DETAIL_URL = "https://store.steampowered.com/api/appdetails"
REVIEW_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"


# =========================
# 采集时间范围
# =========================

def get_date_from():

    if DATE_FROM_ENV:
        return datetime.datetime.strptime(
            DATE_FROM_ENV,
            "%Y-%m-%d"
        ).date()

    today = datetime.date.today()

    try:
        return today.replace(year=today.year - RECENT_YEARS)

    except ValueError:
        # 2 月 29 日
        return today.replace(
            year=today.year - RECENT_YEARS,
            day=28
        )


DATE_FROM = get_date_from()
DATE_TO = datetime.date.today()


# =========================
# 日期解析
# =========================

# 中文格式：2024 年 1 月 29 日 / 2024 年 1 月 / 2024 年
CN_DATE_RE = re.compile(
    r"(\d{4})\s*年\s*(?:(\d{1,2})\s*月\s*(?:(\d{1,2})\s*日)?)?"
)

# 英文格式（以防接口换成英文）
EN_DATE_FORMATS = (
    "%d %b, %Y",
    "%b %d, %Y",
    "%d %B, %Y",
    "%B %d, %Y",
    "%b %Y",
    "%Y",
)


def parse_release_date(text):
    """
    把发售日期解析成 date。
    "2024 年 1 月 29 日" -> 2024-01-29
    "即将推出" / 空值 -> None
    """

    if not text:
        return None

    text = text.strip()

    match = CN_DATE_RE.search(text)

    if match:

        year = int(match.group(1))
        month = int(match.group(2) or 1)
        day = int(match.group(3) or 1)

        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None

    for fmt in EN_DATE_FORMATS:

        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return None


# =========================
# CSV字段
# =========================

CSV_FIELDS = [
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
    # "metacritic_score",
]


# =========================
# 文件操作
# =========================

def ensure_data_dir():

    os.makedirs("data", exist_ok=True)


def load_appids():

    if not os.path.exists(APPID_FILE):

        print("找不到 appids_recent.json")
        print("请先运行 get_appids.py")

        return []

    with open(APPID_FILE, "r", encoding="utf-8") as f:

        return json.load(f)


def load_index():

    if not os.path.exists(STATE_FILE):

        return 0

    with open(STATE_FILE, "r", encoding="utf-8") as f:

        data = json.load(f)

    return data.get("index", 0)


def save_index(index):

    with open(STATE_FILE, "w", encoding="utf-8") as f:

        json.dump(
            {
                "index": index
            },
            f,
            ensure_ascii=False,
            indent=2
        )


def load_done_appids():
    """
    读出 CSV 里已经采集过的 AppID。
    这样重复运行、或者以后扩大采集范围时，
    不会重复请求、也不会写出重复数据。
    """

    done = set()

    if not os.path.exists(CSV_FILE):
        return done

    with open(CSV_FILE, "r", newline="", encoding="utf-8-sig") as f:

        for row in csv.DictReader(f):

            try:
                done.add(int(row["appid"]))
            except (TypeError, ValueError, KeyError):
                continue

    return done


# =========================
# CSV初始化
# =========================

def init_csv():

    if not os.path.exists(CSV_FILE):
        with open(
            CSV_FILE,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=CSV_FIELDS
            )
            writer.writeheader()
        return

    # 检查现有文件表头，若缺少评论字段则平滑升级表头
    with open(CSV_FILE, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)

    if header and "total_reviews" not in header:
        print(f"[提示] 检测到现有 CSV ({CSV_FILE}) 缺少评论字段，正在自动升级表头...")
        rows = []
        with open(CSV_FILE, "r", newline="", encoding="utf-8-sig") as f:
            dict_reader = csv.DictReader(f)
            for row in dict_reader:
                row.setdefault("total_reviews", 0)
                row.setdefault("total_positive", 0)
                row.setdefault("total_negative", 0)
                rows.append(row)
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[提示] 现有 CSV 表头升级完成，已兼容保留 {len(rows)} 条历史记录。")


# =========================
# 全局限速
# =========================

# 所有线程共用同一个节奏，避免被 Steam 限流
RATE_LOCK = threading.Lock()
NEXT_ALLOWED = [0.0]
LAST_LIMIT_PRINT = [0.0]

# 当前实际间隔（会根据是否被限流自动调整）
CURRENT_INTERVAL = [REQUEST_INTERVAL]

# 连续成功多少次以后，试着加快一点
SUCCESS_STREAK = [0]

MIN_INTERVAL = 0.3
MAX_INTERVAL = 3.0


def pace():
    """
    全局限速：保证任意两个请求之间至少间隔 CURRENT_INTERVAL 秒。
    """

    while True:

        with RATE_LOCK:

            now = time.time()

            if now >= NEXT_ALLOWED[0]:
                NEXT_ALLOWED[0] = now + CURRENT_INTERVAL[0]
                return

            wait = NEXT_ALLOWED[0] - now

        time.sleep(min(wait, 1))


def cooldown():
    """
    被限流了：全场暂停，并且把间隔调大一点，避免一直被限流。
    """

    with RATE_LOCK:

        CURRENT_INTERVAL[0] = min(
            MAX_INTERVAL,
            CURRENT_INTERVAL[0] * 1.5
        )

        SUCCESS_STREAK[0] = 0

        NEXT_ALLOWED[0] = max(
            NEXT_ALLOWED[0],
            time.time() + COOLDOWN
        )

        interval = CURRENT_INTERVAL[0]

    now = time.time()

    # 限流信息不要刷屏，最多每 30 秒提示一次
    if now - LAST_LIMIT_PRINT[0] > 30:

        LAST_LIMIT_PRINT[0] = now

        print(
            f"  被 Steam 限流，暂停 {COOLDOWN:.0f} 秒，"
            f"间隔调整为 {interval:.2f} 秒"
        )


def relax():
    """
    连续一段时间没被限流，就试着把间隔调小一点。
    """

    with RATE_LOCK:

        SUCCESS_STREAK[0] += 1

        if SUCCESS_STREAK[0] >= 300:

            CURRENT_INTERVAL[0] = max(
                MIN_INTERVAL,
                CURRENT_INTERVAL[0] * 0.9
            )

            SUCCESS_STREAK[0] = 0


# =========================
# 获取游戏详情
# =========================

def get_detail(appid):
    """
    返回 (状态, 数据)
    状态：ok / nodata / error
    ok     -> 拿到详情
    nodata -> Steam 明确说没有这个游戏（下架、锁区等）
    error  -> 网络或接口问题，停下来，避免漏数据
    """

    attempt = 0
    rate_retry = 0

    while attempt < RETRY_TIMES:

        pace()

        try:

            response = requests.get(
                DETAIL_URL,
                params={
                    "appids": appid,
                    "l": "schinese",
                    "cc": "cn"
                },
                timeout=30
            )

            if response.status_code == 429:

                rate_retry += 1

                if rate_retry > RATE_RETRY:
                    return "error", None

                cooldown()

                continue

            response.raise_for_status()

            app_data = response.json().get(str(appid))

            relax()

            if not app_data or not app_data.get("success"):
                return "nodata", None

            return "ok", app_data.get("data")

        except Exception as e:

            attempt += 1

            print(f"  AppID {appid} 第 {attempt} 次请求失败：{e}")

            if attempt < RETRY_TIMES:
                time.sleep(RETRY_WAIT)

    return "error", None


# =========================
# 获取评论统计 (Boxleiter 模型数据源)
# =========================

def get_review_summary(appid):
    """
    获取游戏的评论统计数据：总评论数、好评数、差评数。
    接口: https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/
    """
    attempt = 0
    rate_retry = 0

    while attempt < RETRY_TIMES:

        pace()

        try:
            params = {
                "appid": appid,
                "language": "all",
                "purchase_type": "all",
                "num_per_page": 0,
            }
            if API_KEY:
                params["key"] = API_KEY

            response = requests.get(
                REVIEW_URL,
                params=params,
                timeout=15
            )

            if response.status_code == 429:

                rate_retry += 1

                if rate_retry > RATE_RETRY:
                    break

                cooldown()

                continue

            response.raise_for_status()

            summary = response.json().get("response", {}).get("query_summary", {})

            relax()

            return {
                "total_reviews": int(summary.get("total_reviews", 0) or 0),
                "total_positive": int(summary.get("total_positive", 0) or 0),
                "total_negative": int(summary.get("total_negative", 0) or 0),
            }

        except Exception as e:

            attempt += 1

            if attempt < RETRY_TIMES:
                time.sleep(RETRY_WAIT)

    return {"total_reviews": 0, "total_positive": 0, "total_negative": 0}


# =========================
# 数据处理
# =========================

def parse_game(data, reviews=None):

    reviews = reviews or {}

    # 开发商
    developers = data.get("developers", [])

    developers = ";".join(developers)

    # 发行商
    publishers = data.get("publishers", [])

    publishers = ";".join(publishers)

    # 游戏类型
    genres = data.get("genres", [])

    genres = ";".join(
        item.get("description", "")
        for item in genres
    )

    # 游戏分类
    categories = data.get("categories", [])

    categories = ";".join(
        item.get("description", "")
        for item in categories
    )

    # 平台
    platforms_data = data.get("platforms", {})

    platforms = []

    for platform, enabled in platforms_data.items():

        if enabled:
            platforms.append(platform)

    platforms = ";".join(platforms)

    # 价格
    price = data.get("price_overview")

    if price:

        initial_price = price.get("initial", 0) / 100

        final_price = price.get("final", 0) / 100

        discount_percent = price.get(
            "discount_percent",
            0
        )

        currency = price.get(
            "currency",
            ""
        )

    else:

        initial_price = 0
        final_price = 0
        discount_percent = 0
        currency = ""

    # # Metacritic
    # metacritic = data.get("metacritic", {})

    # metacritic_score = metacritic.get(
    #     "score",
    #     None
    # )

    # 最终数据
    game = {

        "appid": data.get("steam_appid"),

        "name": data.get("name"),

        "type": data.get("type"),

        "release_date": data.get(
            "release_date",
            {}
        ).get("date"),

        "developers": developers,

        "publishers": publishers,

        "genres": genres,

        "categories": categories,

        "platforms": platforms,

        "is_free": data.get(
            "is_free",
            False
        ),

        "initial_price": initial_price,

        "final_price": final_price,

        "discount_percent": discount_percent,

        "currency": currency,

        "total_reviews": reviews.get("total_reviews", 0),

        "total_positive": reviews.get("total_positive", 0),

        "total_negative": reviews.get("total_negative", 0),

        # "metacritic_score": metacritic_score
    }

    return game


def in_date_range(data, release_date):
    """
    判断游戏是否在采集时间范围内。
    还没发售的游戏（即将推出）直接不要。
    """

    if data.get("release_date", {}).get("coming_soon"):
        return False

    if release_date is None:
        return False

    return DATE_FROM <= release_date <= DATE_TO


# =========================
# 写入CSV
# =========================

def save_game(game):

    with open(
        CSV_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS
        )

        writer.writerow(game)


# =========================
# 进度显示
# =========================

def format_seconds(seconds):

    seconds = int(seconds)

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    return f"{hours:02d}:{minutes:02d}:{seconds % 60:02d}"


def print_progress(done, total, kept, skipped, elapsed, last_name):

    remaining = 0

    if done > 0:
        remaining = (total - done) * elapsed / done

    print(
        f"[进度] {done}/{total} | "
        f"保留 {kept} | "
        f"跳过 {skipped} | "
        f"已用 {format_seconds(elapsed)} | "
        f"剩余约 {format_seconds(remaining)} | "
        f"间隔 {CURRENT_INTERVAL[0]:.2f}s | "
        f"最近：{last_name}"
    )


# =========================
# 主程序
# =========================

def main():

    ensure_data_dir()

    init_csv()

    appids = load_appids()

    if not appids:
        return

    start_index = load_index()

    done_appids = load_done_appids()

    print("========== 采集范围 ==========")
    print(f"只保留 {DATE_FROM} ~ {DATE_TO} 发行的游戏")
    print(f"AppID 总数：{len(appids)}")
    print(f"从第 {start_index + 1} 个开始")
    print(f"CSV 里已经有：{len(done_appids)} 个游戏")
    print(f"并发线程：{THREADS}")
    print(
        f"本次最多获取："
        f"{MAX_DETAILS if MAX_DETAILS > 0 else '不限制'}"
    )
    print()

    kept = 0
    skipped = 0
    processed = 0
    start_time = time.time()
    last_name = ""
    index = start_index
    next_progress = PROGRESS_EVERY
    total = len(appids) - start_index

    try:

        with ThreadPoolExecutor(max_workers=THREADS) as pool:

            while index < len(appids):

                if MAX_DETAILS > 0 and processed >= MAX_DETAILS:
                    print("已达到本次采集上限。")
                    break

                size = CHUNK_SIZE

                if MAX_DETAILS > 0:
                    size = min(size, MAX_DETAILS - processed)

                chunk = appids[index:index + size]

                # 已经采集过的直接跳过，不再请求
                pending = [
                    appid
                    for appid in chunk
                    if appid not in done_appids
                ]

                if pending:

                    results = list(pool.map(get_detail, pending))

                    if any(status == "error" for status, _ in results):

                        # 不推进断点，下次运行从这一批重新开始
                        print(
                            "请求一直失败，先停下来，"
                            "下次运行会从这一批继续。"
                        )
                        break

                    for appid, (status, data) in zip(pending, results):

                        if status != "ok":
                            skipped += 1
                            print(f"AppID {appid}：网络请求失败")
                            continue

                        name = data.get("name") or f"AppID {appid}"

                        if data.get("type") != "game":
                            skipped += 1
                            g_type = data.get("type", "未知")
                            print(f"{name}：跳过 (非纯游戏/类型: {g_type})")
                            continue

                        release_date = parse_release_date(
                            data.get("release_date", {}).get("date")
                        )

                        if not in_date_range(data, release_date):
                            skipped += 1
                            raw_date = data.get("release_date", {}).get("date", "未知")
                            if data.get("release_date", {}).get("coming_soon"):
                                print(f"{name}：跳过 (未发售/即将推出)")
                            else:
                                print(f"{name}：跳过 (发售日期 {raw_date} 不在近3年范围)")
                            continue

                        # 仅对已确认符合条件的纯游戏拉取评论数据，节约网络请求
                        reviews = get_review_summary(appid)

                        game = parse_game(data, reviews)

                        save_game(game)

                        done_appids.add(appid)

                        kept += 1
                        last_name = (
                            f"{game['name']}"
                            f"（{game['release_date']} | 评论:{game['total_reviews']}）"
                        )

                        print(
                            f"{game['name']}：获取成功 "
                            f"(总评: {game['total_reviews']}, 好评: {game['total_positive']})"
                        )

                processed += len(chunk)
                index += len(chunk)

                # 立即保存断点
                save_index(index)

                if processed >= next_progress or index >= len(appids):

                    print_progress(
                        processed,
                        total,
                        kept,
                        skipped,
                        time.time() - start_time,
                        last_name
                    )

                    next_progress += PROGRESS_EVERY

    except KeyboardInterrupt:

        print("\n手动中断，进度已保存。")

    elapsed = time.time() - start_time

    print()
    print("========== 完成 ==========")
    print(f"本次处理：{processed}")
    print(f"保留游戏：{kept}")
    print(f"跳过（不在时间范围 / 没有数据）：{skipped}")
    print(f"本次用时：{format_seconds(elapsed)}")
    print(f"当前进度：{load_index()}/{len(appids)}")
    print(f"保存到：{CSV_FILE}")


if __name__ == "__main__":
    main()
