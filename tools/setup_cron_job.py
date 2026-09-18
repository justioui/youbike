#!/usr/bin/env python3
"""
setup_cron_job.py

自動透過 cron-job.org REST API 建立（或更新）一個排程任務，
定時呼叫 GitHub 的 workflow_dispatch API 來觸發你的 GitHub Actions workflow。

用法範例：

    # 建議先用環境變數放密鑰，避免留在 shell history / 終端機截圖裡
    export CRONJOB_API_KEY="你的 cron-job.org API key"
    export GITHUB_TOKEN="你的 GitHub fine-grained PAT"

    python setup_cron_job.py \
        --github-owner your-github-username \
        --github-repo your-repo-name \
        --workflow-file collect-youbike.yml \
        --ref main \
        --interval 5 \
        --timezone Asia/Taipei

第一次執行會「建立」新的 cronjob；之後若帶上 --job-id 可以「更新」既有的 cronjob
（例如之後想把間隔從 5 分鐘改成 10 分鐘）。

需要的密鑰：
  1. cron-job.org API key：登入 https://console.cron-job.org -> Settings -> API 取得
  2. GitHub PAT：GitHub -> Settings -> Developer settings -> Fine-grained personal
     access tokens，Repository access 限定你的 repo，Permissions 只勾
     "Actions: Read and write"

腳本不會把任何密鑰寫進檔案或印在畫面上（只會印出前後幾碼方便你核對）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CRONJOB_API_BASE = "https://api.cron-job.org"


def mask(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def build_minutes_list(interval: int) -> list[int]:
    if interval <= 0 or interval > 59 or 60 % interval != 0:
        raise ValueError("interval 必須是可以整除 60 的正整數（例如 5、10、15、20、30）")
    return list(range(0, 60, interval))


def build_job_payload(
    *,
    title: str,
    github_owner: str,
    github_repo: str,
    workflow_file: str,
    ref: str,
    github_token: str,
    interval: int,
    timezone: str,
    enabled: bool,
) -> dict:
    dispatch_url = (
        f"https://api.github.com/repos/{github_owner}/{github_repo}"
        f"/actions/workflows/{workflow_file}/dispatches"
    )
    body = json.dumps({"ref": ref})

    return {
        "job": {
            "title": title,
            "enabled": enabled,
            "saveResponses": True,
            "url": dispatch_url,
            "requestMethod": 1,  # POST
            "requestTimeout": 30,
            "extendedData": {
                "headers": {
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
                "body": body,
            },
            "notification": {
                "onFailure": True,
                "onFailureCount": 1,
                "onSuccess": True,
                "onDisable": True,
            },
            "schedule": {
                "timezone": timezone,
                "expiresAt": 0,
                "hours": [-1],
                "mdays": [-1],
                "minutes": build_minutes_list(interval),
                "months": [-1],
                "wdays": [-1],
            },
        }
    }


def call_cronjob_api(
    method: str, path: str, api_key: str, payload: dict | None = None
) -> dict:
    url = f"{CRONJOB_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"[錯誤] cron-job.org API 回傳 HTTP {e.code}: {error_body}", file=sys.stderr)
        raise
    except URLError as e:
        print(f"[錯誤] 無法連線到 cron-job.org API: {e.reason}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="設定 cron-job.org 排程來觸發 GitHub Actions")
    parser.add_argument("--github-owner", required=True, help="GitHub 使用者名稱或組織名")
    parser.add_argument("--github-repo", required=True, help="repository 名稱")
    parser.add_argument(
        "--workflow-file",
        required=True,
        help="workflow 檔名，例如 collect-youbike.yml（.github/workflows/ 底下的檔名）",
    )
    parser.add_argument("--ref", default="main", help="要觸發的分支名稱，預設 main")
    parser.add_argument("--interval", type=int, default=5, help="間隔分鐘數，預設 5（需可整除 60）")
    parser.add_argument("--timezone", default="Asia/Taipei", help="排程時區，預設 Asia/Taipei")
    parser.add_argument("--title", default="Trigger GitHub Actions", help="cronjob 顯示名稱")
    parser.add_argument(
        "--job-id",
        type=int,
        default=None,
        help="若提供，表示更新既有的 cronjob 而非新建一個",
    )
    parser.add_argument(
        "--disabled",
        action="store_true",
        help="建立/更新後先設為停用狀態（預設是啟用）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只印出即將送出的 payload，不實際呼叫 API",
    )
    parser.add_argument(
        "--cronjob-api-key",
        default=os.environ.get("CRONJOB_API_KEY"),
        help="cron-job.org API key（建議用環境變數 CRONJOB_API_KEY 傳入）",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub PAT（建議用環境變數 GITHUB_TOKEN 傳入）",
    )

    args = parser.parse_args()

    if not args.dry_run:
        if not args.cronjob_api_key:
            parser.error("缺少 cron-job.org API key（用 --cronjob-api-key 或環境變數 CRONJOB_API_KEY）")
        if not args.github_token:
            parser.error("缺少 GitHub PAT（用 --github-token 或環境變數 GITHUB_TOKEN）")

    payload = build_job_payload(
        title=args.title,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        workflow_file=args.workflow_file,
        ref=args.ref,
        github_token=args.github_token or "PLACEHOLDER_TOKEN",
        interval=args.interval,
        timezone=args.timezone,
        enabled=not args.disabled,
    )

    print(f"目標 workflow dispatch URL: {payload['job']['url']}")
    print(f"每 {args.interval} 分鐘觸發一次（時區 {args.timezone}）")
    if args.github_token:
        print(f"GitHub token: {mask(args.github_token)}")

    if args.dry_run:
        print("\n--dry-run 模式，即將送出的 payload：")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if args.job_id is None:
        print("\n建立新的 cronjob...")
        result = call_cronjob_api("PUT", "/jobs", args.cronjob_api_key, payload)
        job_id = result.get("jobId")
        print(f"完成！新的 jobId = {job_id}")
        print("之後若要更新這個 job（例如改間隔），可加上參數：--job-id " + str(job_id))
    else:
        print(f"\n更新既有的 cronjob（jobId={args.job_id}）...")
        call_cronjob_api("PATCH", f"/jobs/{args.job_id}", args.cronjob_api_key, payload)
        print("更新完成！")

    print("\n建議接著手動觸發一次確認：")
    print(f"  curl -X GET -H 'Authorization: Bearer <你的 cronjob API key>' "
          f"{CRONJOB_API_BASE}/jobs/{args.job_id or '<新的 jobId>'}/history")


if __name__ == "__main__":
    main()
