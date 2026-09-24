# Formula 1 Results Scraper

抓取 [Formula 1 官方 Results 页面](https://www.formula1.com/en/results.html) 的历史数据，并生成一个按年份懒加载的静态结果页。

## 功能

- 抓取每个赛季的 `Races`、`Drivers`、`Teams` 和 `Awards` 页面；
- 自动发现每场大奖赛页面中的 Practice、Qualifying、Starting Grid、Pit Stop Summary、Fastest Laps、Race Result 等结果页；
- 保存表头、单元格文本、官方链接，以及可用的图片信息；
- 对成功响应进行缓存，并记录失败 URL，便于断点续跑；
- 构建时将数据拆分为 `site_data/index.js` 和每个年份一个的 `site_data/YYYY.js`，浏览器只在切换年份时加载对应文件。
- 主页面搜索框根据输入显示匹配建议，按 Enter 可进入完整搜索页。查询字段包括车手、车队、大奖赛和底盘型号，多词可以跨字段匹配。完整搜索页展示全部匹配记录；仅按大奖赛名称检索时，每个年份的同一场比赛显示一条记录。搜索索引按年份组织。

## 目录结构

```text
f1_results_scraper/
├── scraper.py             # Races 及各场比赛结果
├── standings_scraper.py   # Drivers、Teams、Awards
├── statsf1_enrich.py       # 从 StatsF1 获取参赛车辆底盘型号和赛果说明脚注
├── build_static.py        # 将 data/ 构建为静态网页数据
├── search_index_builder.py # 从赛果表生成按年份组织的搜索索引
├── action_change_report.py # 生成赛季表格对照报告
├── template.html          # 静态网页模板
├── index.html             # 构建生成的结果页
├── search.html            # 完整搜索结果页
├── site_data/
│   ├── index.js            # 年份清单和统计信息
│   ├── YYYY.js             # 对应年份的数据
│   └── search_index/       # 按年份组织的搜索索引
├── requirements.txt
└── data/                  # 本地抓取缓存，默认被 Git 忽略
```

## 安装

使用本地 Conda 环境 `env3.10`：

```powershell
cd f1_results_scraper
conda activate env3.10
python -m pip install -r requirements.txt
```

## 抓取数据

抓取比赛及赛季结果：

```powershell
python scraper.py --start-year 1950 --end-year 2026
```

抓取车手、车队和奖项：

```powershell
python standings_scraper.py --start-year 1950 --end-year 2026
```

为各站赛果补充 StatsF1 参赛车辆的底盘型号，并合并适用于赛果页的纯说明脚注。常规运行只遍历目标赛季；从 1950 年开始的历史回填可显式指定起始年份：

```powershell
python statsf1_enrich.py --start-year 1950 --end-year 2026
```

GitHub Actions 每次从上一个赛季最后一站的记录开始，沿 StatsF1 的“下一站”链接遍历当季；赛季末站位置保存在 `site_data/statsf1_progress.json`。手动执行时省略 `--start-year` 会使用相同的当季范围。页面会缓存在 `data/statsf1_pages/`，中断后可续跑。替补车手、第三车手等参赛身份说明会跳过。运行 `build_static.py` 时，已有底盘型号与脚注会保留。

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

该命令会读取 `data/records.jsonl` 和 `data/failures.jsonl`，生成 `index.html`、`site_data/index.js`、各年份的 `site_data/YYYY.js`，以及 `site_data/search_index/` 下的搜索清单和年份索引。然后用浏览器打开本目录下的 `index.html`。

如果页面提示无法读取年份数据，请确认 `site_data/index.js` 和所选年份的 `site_data/YYYY.js` 都存在；通过 `file://` 打开时不要移动或拆散这些文件。

这里的日期与 F1 官网结果页页眉语义一致：旧比赛通常显示一个比赛日，现代比赛通常显示整个比赛周末的日期范围。官网会在同场比赛的各会话结果页重复这组赛事级信息；它不表示排位赛、练习赛等会话各自的实际日期或开赛时间。

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
  "columns": ["Pos.", "No.", "Driver", "Team", "Chassis", "Laps", "Time / Retired", "Pts."],
  "rows": [{"Pos.": "1", "No.": "63", "Driver": "George Russell RUS", "Team": "Mercedes", "Chassis": "F1 W17", "Driver__links": ["..."], "...": "..."}]
}
```

对于列数不规则的表格，程序会保存原始 `cells`，不会因为无法规整成统一列数而丢弃数据。

## GitHub Actions

`.github/workflows/update-f1-data.yml` 可手动触发，也按每周一 12:00（Asia/Shanghai）运行。工作流按 UTC 当前年份执行 `scraper.py`、`standings_scraper.py` 和 `statsf1_enrich.py`，再运行 `build_static.py`；该构建过程会调用 `search_index_builder.py`。`action_change_report.py` 生成赛季表格对照报告，最多列出 15 张表。工作流检查 `index.html` 和 `site_data/`，有文件内容待提交时会提交并推送。钉钉通知呈现运行状态与表格报告。

GitHub Pages 的部署由仓库自身的 Pages 配置或其他工作流负责；本工作流负责赛季数据抓取、静态文件构建和数据提交。

## 合规说明

请遵守 Formula 1 官方网站的使用条款，并合理控制请求频率。本工具只访问公开页面，不绕过登录、验证码或访问控制。
