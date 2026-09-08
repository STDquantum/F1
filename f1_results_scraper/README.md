# Formula 1 Results Scraper

采集 Formula 1 官方 Results 页面（默认覆盖 1950 年至当前年份）中的：

- 每年顶层 `Races`、`Drivers`、`Teams`、`Awards` 页面；
- 每场大奖赛的所有官方结果页面（按该场页面实际出现的链接自动发现），包括 Practice、Qualifying、Starting Grid、Pit Stop Summary、Fastest Laps、Race Result 等；
- 每张表格的表头、每一行的单元格文本，以及单元格中的官方链接。

抓取运行时会在临时的 `data/` 目录生成记录和缓存；构建时会把数据拆成 `site_data/index.js` 和按年份分开的 `site_data/YYYY.js`，结果页只在切换年份时加载对应文件，因此不会再把全部历史数据塞进一个超大的 HTML。本地清理后不保留 `data/` 临时目录，GitHub Actions 每周运行时会重新生成 `site_data/`。

## 静态网页

直接双击打开最终静态页面：

```powershell
D:\conda\env3.10\python.exe D:\F1\f1_results_scraper\build_static.py
```

然后直接打开 `index.html`。GitHub Actions 会按周自动重新抓取并部署 GitHub Pages；根目录导航页会同时发布结果页和 2026 特殊涂装页。

## 安装

建议 Python 3.10+：

```powershell
cd D:\F1\f1_results_scraper
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果电脑没有 `py`，将命令中的 `py` 换成 `python`。

## 运行

```powershell
python scraper.py --start-year 1950 --end-year 2026
```

Drivers、Teams 和 Awards 使用统一脚本：

```powershell
python standings_scraper.py --start-year 1950 --end-year 2026
```

先用代表性年份试跑：

```powershell
python scraper.py --start-year 2026 --end-year 2026 --limit-races 1
```

常用参数：

- `--start-year`、`--end-year`：年份范围，包含两端；
- `--limit-races N`：每年最多采集 N 场比赛，适合检查结构；
- `--delay 1.0`：请求间隔秒数，默认 1 秒；
- `--refresh`：忽略缓存重新请求；
- `--insecure`：关闭 TLS 证书校验，仅在本机代理导致证书校验失败时使用；
- `--output DIR`：更改输出目录，默认为当前目录下 `data`。

程序会自动重试临时网络错误、缓存成功响应、记录失败 URL，并在再次运行时跳过已完成页面。官方页面的历史年份和某些赛事可能没有所有项目；这类缺失会按实际页面保存，不会伪造空数据。

## 数据结构

`records.jsonl` 每行是：

```json
{
  "year": 2026,
  "section": "races",
  "race": {"race_id": "1279", "slug": "australia", "url": "..."},
  "session": "race-result",
  "url": "...",
  "title": "...",
  "table_index": 0,
  "columns": ["Pos.", "No.", "Driver", "Team", "Laps", "Time / Retired", "Pts."],
  "rows": [{"Pos.": "1", "No.": "63", "Driver": "George Russell RUS", "Driver__links": ["..."], "...": "..."}]
}
```

页面内无法规整为同一列数的表格仍会原样保存为 `cells`，不会因为列数变化而丢弃。

数据版权和访问频率请遵守 Formula 1 官方网站的使用条款；本工具只访问公开页面，不绕过登录或验证码。
