# YouBike 即時資料蒐集

此專案會每 5 分鐘抓取一次：

`https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json`

並輸出到：

- 每日 CSV：`data/YYYY-MM-DD.csv`（同一天持續追加）
- SQLite 資料庫：`data/youbike.sqlite3`

## 本機執行

```bash
python scripts/collect_youbike.py
```

## GitHub Actions 自動執行

工作流程檔案：

`/.github/workflows/collect-youbike.yml`

功能：

1. 每 5 分鐘觸發一次（cron: `*/5 * * * *`）
2. 執行蒐集腳本
3. 自動提交 `data/*.csv` 與 `data/youbike.sqlite3` 到 repository
