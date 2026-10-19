import os
import json
import requests
from dotenv import load_dotenv

# =========================
# 配置
# =========================

load_dotenv()

API_KEY = os.getenv("STEAM_API_KEY")

# 从哪个 AppID 开始采集（跳过更老的老游戏）
# 2000000 对应 2022 年中，能够完整覆盖“近 3 年”（2023-10 ~ 2026-10）发行的游戏；
# 若扩展至“近 5 年”，只需在 .env 中设置 START_APPID=1500000
START_APPID = int(os.getenv("START_APPID", "2000000"))

# 0 = 不限制
MAX_APPS = int(os.getenv("MAX_APPS", "0"))

# 每次向 Steam 请求多少个（接口最多支持 50000）
PAGE_SIZE = 50000

APPID_FILE = "data/appids_recent.json"
STATE_FILE = "data/appids_recent_state.json"

URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"


# =========================
# 文件操作
# =========================

def ensure_data_dir():
    os.makedirs("data", exist_ok=True)


def load_appids():

    if not os.path.exists(APPID_FILE):
        return []

    with open(APPID_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_appids(appids):

    # 去重并排序保存
    unique_ids = sorted(list(set(appids)))

    with open(APPID_FILE, "w", encoding="utf-8") as f:
        json.dump(
            unique_ids,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_last_appid():

    if not os.path.exists(STATE_FILE):

        # 第一次运行：从 START_APPID 开始
        return max(START_APPID - 1, 0)

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("last_appid", max(START_APPID - 1, 0))


def save_last_appid(last_appid):

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_appid": last_appid
            },
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================
# 获取一批 AppID
# =========================

def get_appids_page(last_appid):

    params = {
        "key": API_KEY,
        "include_games": "true",
        "include_dlc": "false",
        "include_software": "false",
        "include_videos": "false",
        "include_hardware": "false",
        "max_results": PAGE_SIZE,
        "last_appid": last_appid
    }

    response = requests.get(
        URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json().get("response", {})


# =========================
# 主程序
# =========================

def main():

    if not API_KEY:
        print("错误：没有找到 STEAM_API_KEY")
        return

    ensure_data_dir()

    appids = load_appids()
    min_existing = min(appids) if appids else None

    # 如果配置的 START_APPID 比本地已有最小 AppID 还小（例如从近3年扩展到了近5年）
    # 则自动从新的 START_APPID 补充采集更早的 AppID 并合并
    if min_existing is not None and START_APPID < min_existing:
        print(f"检测到起始 AppID 范围扩大（已有最小：{min_existing}，新配置：{START_APPID}）")
        print(f"将自动从 {START_APPID} 补充采集并合并入本地数据！")
        last_appid = max(START_APPID - 1, 0)
    else:
        last_appid = load_last_appid()

    print(f"起始 AppID：{START_APPID}")
    print(f"本地已有 AppID：{len(appids)}")
    print(f"从 AppID {last_appid} 后继续")
    print()

    collected = 0

    try:

        while True:

            if MAX_APPS > 0 and collected >= MAX_APPS:
                break

            response = get_appids_page(last_appid)

            apps = response.get("apps", [])

            if not apps:
                print("没有更多 AppID。")
                break

            # 如果本次剩余数量不足一页，只取需要的数量
            if MAX_APPS > 0:

                remaining = MAX_APPS - collected

                apps = apps[:remaining]

            # 添加 AppID
            for app in apps:

                appid = app.get("appid")

                if appid is not None:
                    appids.append(appid)

            # 更新断点
            last_appid = apps[-1]["appid"]

            # 立即保存
            save_appids(appids)
            save_last_appid(last_appid)

            collected += len(apps)

            print(
                f"本次新增：{len(apps)} | "
                f"本地总数：{len(appids)} | "
                f"当前断点：{last_appid}"
            )

            if MAX_APPS > 0 and collected >= MAX_APPS:
                break

            if not response.get("have_more_results", False):

                print("Steam 已经没有更多 AppID。")
                break

    except KeyboardInterrupt:

        print("\n手动中断，进度已保存。")

    print()
    print("========== 完成 ==========")
    print(f"本次新增：{collected}")
    print(f"本地总数：{len(appids)}")
    print(f"当前断点：{last_appid}")


if __name__ == "__main__":
    main()