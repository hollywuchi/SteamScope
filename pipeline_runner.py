"""
Steam 数据管道微批次全自动调度器 (Pipeline Runner)
工作流程闭环：
  [检查 AppID 池] -> [循环开始]
    -> 采集 N 条游戏详情 (get_details.py)
    -> 数据清洗与治理 (data_clean.py)
    -> 增量同步至 Azure MySQL (app.py --sync-db)
    -> 刷新统计分析摘要 (analysis.py)
    -> 冷却等待 (避免 Steam 429 限流窗口)
    -> 进入下一轮循环
"""

import os
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime

# 基础文件路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPID_FILE = os.path.join(BASE_DIR, "data", "appids_recent.json")
STATE_FILE = os.path.join(BASE_DIR, "data", "details_recent_state.json")
RAW_CSV = os.path.join(BASE_DIR, "data", "steam_games_recent.csv")
CLEAN_CSV = os.path.join(BASE_DIR, "data", "steam_games_recent_clean.csv")


def print_banner(text, char="="):
    line = char * 60
    print(f"\n{line}\n  {text}\n{line}")


def get_progress():
    """获取当前采集进度"""
    total_appids = 0
    current_index = 0

    if os.path.exists(APPID_FILE):
        try:
            with open(APPID_FILE, "r", encoding="utf-8") as f:
                appids = json.load(f)
                total_appids = len(appids)
        except Exception:
            pass

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                current_index = state.get("index", 0)
        except Exception:
            pass

    return current_index, total_appids


def run_command(cmd, step_name):
    """运行子脚本并流式输出日志"""
    print(f"\n>>> [{datetime.now().strftime('%H:%M:%S')}] 正在执行: {step_name}")
    print(f"    命令: {' '.join(cmd)}")
    start = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"[警告] {step_name} 执行异常退出，退出码: {result.returncode}，耗时: {elapsed:.1f}s")
        return False
    print(f"[成功] {step_name} 执行完成，耗时: {elapsed:.1f}s")
    return True


def ensure_appids():
    """前置检查：确保本地已有待采集的 AppID 资产池"""
    if not os.path.exists(APPID_FILE):
        print("\n[初始化] 本地未发现 AppID 资产池，首次运行自动拉取...")
        cmd = [sys.executable, os.path.join(BASE_DIR, "get_appids.py")]
        ok = run_command(cmd, "拉取初始 AppID 清单 (get_appids.py)")
        if not ok or not os.path.exists(APPID_FILE):
            print("[错误] 获取 AppID 失败，请检查网络或 .env 中的 STEAM_API_KEY 配置！")
            return False
    return True


def countdown(seconds):
    """限流冷却友好倒计时（支持随时 Ctrl+C 退出）"""
    print(f"\n>>> 进入限流保护冷却期，等待 {seconds} 秒以重置 Steam 访问频率计数器...")
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\r    剩余冷却时间: {remaining:3d} 秒 (按 Ctrl+C 可安全中止循环)... ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r    冷却结束，开始下一轮采集！                     \n")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Steam 数据采集-清洗-入库微批次全自动调度器")
    parser.add_argument("-n", "--batch-size", type=int, default=300, help="每轮采集的 AppID 数量 (默认 300，最契合 Steam 5分钟限流窗口)")
    parser.add_argument("-c", "--cooldown", type=int, default=45, help="每轮微批次结束后的冷却秒数 (默认 45 秒)")
    parser.add_argument("-r", "--rounds", type=int, default=0, help="最大执行轮数 (0 为不限制，直到全部采集完成)")
    args = parser.parse_args()

    batch_size = args.batch_size
    cooldown_sec = args.cooldown
    max_rounds = args.rounds

    print_banner(f"Steam 微批次 ETL 调度器启动 (批次大小: {batch_size}, 冷却: {cooldown_sec}s)")

    # 1. 前置检查
    if not ensure_appids():
        sys.exit(1)

    round_count = 0

    try:
        while True:
            round_count += 1
            cur_idx, total_ids = get_progress()
            print_banner(f"第 {round_count} 轮数据流水线开始 | 全局进度: {cur_idx}/{total_ids} ({(cur_idx/total_ids*100) if total_ids else 0:.1f}%)")

            # 检查是否已经采集完成
            if total_ids > 0 and cur_idx >= total_ids:
                print("\n🎉 [完成] 所有 AppID 详情已全部采集完毕，调度器平稳退出！")
                break

            # 步骤 1: 采集 N 条详情
            crawl_cmd = [sys.executable, os.path.join(BASE_DIR, "get_details.py"), str(batch_size)]
            crawl_ok = run_command(crawl_cmd, f"1. 采集游戏详情 (限额 {batch_size} 条)")
            if not crawl_ok:
                print("[警告] 采集步骤遇到异常，可能是触发限流或网络断开。休眠 60 秒后重试...")
                time.sleep(60)
                continue

            # 步骤 2: 数据清洗与标准化
            clean_cmd = [sys.executable, os.path.join(BASE_DIR, "data_clean.py")]
            clean_ok = run_command(clean_cmd, "2. 数据质量治理与清洗 (data_clean.py)")
            if not clean_ok:
                print("[跳过] 数据清洗失败，跳过后续入库步骤，进入下一轮...")
                continue

            # 步骤 3: 增量入库至 Azure MySQL
            sync_cmd = [sys.executable, os.path.join(BASE_DIR, "app.py"), "--sync-db"]
            sync_ok = run_command(sync_cmd, "3. 同步数据至 Azure MySQL (app.py --sync-db)")

            # 步骤 4: 刷新分析摘要文件 (静默模式，仅更新 JSON 供 API 与大屏快速消费)
            analysis_cmd = [sys.executable, os.path.join(BASE_DIR, "analysis.py"), "--quiet"]
            run_command(analysis_cmd, "4. 刷新多维统计分析摘要 (analysis.py)")

            # 轮数上限检查
            if max_rounds > 0 and round_count >= max_rounds:
                print(f"\n[完成] 已达到设定的最大轮数 ({max_rounds} 轮)，调度器退出。")
                break

            # 步骤 5: 冷却等待，保护 IP 防 429
            countdown(cooldown_sec)

    except KeyboardInterrupt:
        print("\n\n[提示] 收到中断信号 (Ctrl+C)，当前批次已安全保存并入库，调度器平稳退出。")


if __name__ == "__main__":
    main()
