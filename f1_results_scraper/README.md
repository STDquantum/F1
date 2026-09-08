# Formula 1 Results Scraper

抓取 [Formula 1 官方 Results 页面](https://www.formula1.com/en/results.html) 的历史数据，并生成一个按年份懒加载的静态结果页。

## 功能

- 抓取每个赛季的 `Races`、`Drivers`、`Teams` 和 `Awards` 页面；
- 自动发现每场大奖赛页面中的 Practice、Qualifying、Starting Grid、Pit Stop Summary、Fastest Laps、Race Result 等结果页；
- 保存表头、单元格文本、官方链接，以及可用的图片信息；
- 对成功响应进行缓存，并记录失败 URL，便于断点续跑；
- 构建时将数据拆分为 `site_data/index.js` 和每个年份一个的 `site_data/YYYY.js`，浏览器只在切换年份时加载对应文件。

## 目录结构

```text
f1_results_scraper/
├── scraper.py             # Races 及各场比赛结果
├── standings_scraper.py   # Drivers、Teams、Awards
├── build_static.py        # 将 data/ 构建为静态网页数据
├── template.html          # 静态网页模板
├── index.html             # 构建生成的结果页
├── site_data/
│   ├── index.js            # 年份清单和统计信息
│   └── YYYY.js             # 对应年份的数据
├── requirements.txt
└── data/                  # 本地抓取缓存，默认被 Git 忽略
```

## 安装

需要 Python 3.10 或更高版本：

```powershell
cd f1_results_scraper
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果系统没有 `py`，创建虚拟环境时使用 `python -m venv .venv` 即可。

## 抓取数据

抓取比赛及赛季结果：

```powershell
python scraper.py --start-year 1950 --end-year 2026
```

抓取车手、车队和奖项：

```powershell
python standings_scraper.py --start-year 1950 --end-year 2026
```

建议先用一个赛季和一场比赛验证连接及页面结构：

```powershell
python scraper.py --start-year 2026 --end-year 2026 --limit-races 1
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--start-year YEAR` | 起始年份，包含该年份；默认 `1950` |
| `--end-year YEAR` | 结束年份，包含该年份；不指定时由脚本使用当前年份 |
| `--limit-races N` | 每年最多抓取 N 场比赛，仅 `scraper.py` 支持 |
| `--delay SECONDS` | 请求间隔，默认 `1.0` 秒；Actions 使用 `0.5` 秒 |
| `--refresh` | 忽略已有缓存并重新请求 |
| `--insecure` | 关闭 TLS 证书校验，仅在本机代理导致证书错误时使用 |
| `--output DIR` | 输出目录，默认当前目录下的 `data` |

脚本会自动重试临时网络错误，并在再次运行时复用已完成页面。历史年份或个别赛事如果没有某类结果，会按官方页面实际内容保存，不会补造空数据。

## 构建和查看静态网页

完成抓取后，在本目录执行：

```powershell
python build_static.py
```

该命令会读取 `data/records.jsonl` 和 `data/failures.jsonl`，更新 `index.html`、`site_data/index.js` 和对应年份的 `site_data/YYYY.js`。然后用浏览器打开本目录下的 `index.html`。

如果页面提示无法读取年份数据，请确认 `site_data/index.js` 和所选年份的 `site_data/YYYY.js` 都存在；通过 `file://` 打开时不要移动或拆散这些文件。

## 数据格式

`data/records.jsonl` 每行代表一张表格，例如：

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

对于列数不规则的表格，程序会保存原始 `cells`，不会因为无法规整成统一列数而丢弃数据。

## GitHub Actions

`.github/workflows/update-f1-data.yml` 会在每周一 12:00（Asia/Shanghai）运行，也可以手动触发。它只抓取 UTC 当前年份，依次更新比赛、车手、车队和奖项数据，重新构建 `index.html` 与 `site_data/`，最后在有变化时提交并推送。

GitHub Pages 的部署需由仓库自身的 Pages 配置或其他工作流负责；本工作流只负责更新并提交数据文件。

## 合规说明

请遵守 Formula 1 官方网站的使用条款，并合理控制请求频率。本工具只访问公开页面，不绕过登录、验证码或访问控制。
