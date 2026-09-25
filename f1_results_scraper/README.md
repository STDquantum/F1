# Formula 1 Results Scraper

此目录包含 Formula 1 官方 Results 页面抓取程序、静态赛果页面和页面所需的数据文件。抓取结果按 JSONL 记录保存，再生成按年份拆分的 JavaScript 数据文件。浏览器可直接读取这些文件，不需要后端服务。

## 功能范围

- 按赛季读取 `Races`、`Drivers`、`Teams` 和 `Awards` 页面。
- 从大奖赛页面发现练习赛、排位赛、起步顺序、进站摘要、最快圈、正赛结果等会话结果页面。
- 保留表头、单元格文本、官方链接、可用图片信息和表格脚注；不规则表格也会保留原始单元格内容。
- 将抓取页面缓存、表格记录和失败 URL 分别存放，便于续跑和检查网络问题。
- 从 StatsF1 读取参赛车辆底盘型号，并筛选可用于正赛表格的说明脚注。
- 按赛季生成静态结果页数据，并生成分年份搜索索引。
- 在结果页选择赛季和数据类别，或搜索车手、车队、大奖赛、底盘型号。

## 文件和目录

```text
f1_results_scraper/
├── scraper.py                 # Races 和大奖赛会话结果
├── standings_scraper.py       # Drivers、Teams 和 Awards
├── statsf1_enrich.py           # StatsF1 底盘型号与赛果说明脚注
├── build_static.py             # JSONL 记录到静态页面数据
├── search_index_builder.py     # 按年份组织搜索索引
├── action_change_report.py     # GitHub Actions 赛季表格摘要
├── template.html               # 赛果页面模板
├── index.html                  # 年份赛果浏览页
├── search.html                 # 完整搜索页
├── requirements.txt            # Python 依赖
├── data/                       # 本地抓取记录、缓存和进度
└── site_data/
    ├── index.js                # 年份清单和统计信息
    ├── YYYY.js                 # 一个赛季的结果表格
    ├── statsf1_progress.json   # StatsF1 赛事位置记录
    └── search_index/
        ├── index.js            # 搜索索引年份清单
        └── YYYY.js             # 一个赛季的搜索数据
```

`data/` 默认由 Git 忽略，包含下载页面缓存、`records.jsonl`、`failures.jsonl` 和其他运行资料。`site_data/` 是静态网页读取的数据目录，应与 `index.html`、`search.html` 放在现有相对路径下。

## 环境

项目使用 Python 3.10。依赖包括 Beautiful Soup、Requests 和 lxml：

```powershell
cd f1_results_scraper
conda activate env3.10
python -m pip install -r requirements.txt
```

## 抓取 Formula 1 页面

抓取比赛及各场次结果：

```powershell
python scraper.py --start-year 1950 --end-year 2026
```

抓取车手、车队和奖项资料：

```powershell
python standings_scraper.py --start-year 1950 --end-year 2026
```

两个脚本均默认将运行资料放入当前目录的 `data/`。比赛抓取脚本的默认起始年份为 1950，未指定结束年份时使用当前 UTC 年份；排名抓取脚本的默认年份范围为 1950 至 2026。需要明确抓取范围时，可通过年份参数指定起止赛季。

首次连接或检查单场页面结构时，可以只处理一个赛季的一场大奖赛：

```powershell
python scraper.py --start-year 2026 --end-year 2026 --limit-races 1
```

### 常用参数

| 参数 | 适用脚本 | 含义 |
| --- | --- | --- |
| `--start-year YEAR` | 两个抓取脚本 | 起始赛季，含该年份；默认 `1950`。 |
| `--end-year YEAR` | 两个抓取脚本 | 结束赛季，含该年份；比赛抓取默认当前 UTC 年，排名抓取默认 `2026`。 |
| `--limit-races N` | `scraper.py` | 每个赛季处理的大奖赛数量上限。 |
| `--delay SECONDS` | 两个抓取脚本 | 页面请求之间的间隔。比赛抓取默认 `1.0` 秒，排名抓取默认 `0.5` 秒。 |
| `--refresh` | 两个抓取脚本 | 忽略页面缓存并重新请求目标页面。 |
| `--insecure` | 两个抓取脚本 | 关闭 TLS 证书校验；仅用于本机代理证书导致连接失败的情况。 |
| `--output DIR` | 两个抓取脚本 | 抓取记录与页面缓存目录；默认 `data/`。 |

程序会对临时网络错误进行重试，并记录无法读取的 URL。再次运行时会利用已有缓存和完成记录继续处理。访问不存在的历史结果页时，脚本按官网页面内容处理，不生成虚构表格。

## StatsF1 底盘资料

`statsf1_enrich.py` 读取 StatsF1 各大奖赛的参赛车辆页面，将车手与底盘型号对应，并把适合呈现在赛果表格中的说明脚注关联到正赛结果。替补车手、第三车手等参赛身份说明不作为普通正赛车手脚注。赛事页面会缓存在 `data/statsf1_pages/`，赛事位置记录保存在 `site_data/statsf1_progress.json`。

普通的当季抓取范围可使用：

```powershell
python statsf1_enrich.py --end-year 2026
```

指定历史赛季范围：

```powershell
python statsf1_enrich.py --start-year 1950 --end-year 2026
```

不指定 `--start-year` 时，程序从目标赛季前一年的末站位置开始，沿 StatsF1 的“下一站”链接遍历目标赛季。指定 `--start-year` 可进行历史范围抓取；指定 `--start-url` 可直接设定起始 StatsF1 页面。该脚本默认请求间隔为 `1.5` 秒，结束年份默认采用当前 UTC 年份。

在生成网页数据前运行 `statsf1_enrich.py`，可以让抓取到的底盘资料和脚注进入正赛表格。之后执行 `build_static.py` 时，已有赛果中的底盘型号与脚注会纳入网页数据。

## 静态页面构建和浏览

在本目录运行：

```powershell
python build_static.py
```

构建程序读取 `data/records.jsonl` 和 `data/failures.jsonl`，生成 `index.html`、`site_data/index.js`、各年份的 `site_data/YYYY.js`，以及 `site_data/search_index/` 下的索引清单和年份分片。搜索索引也可单独从已有赛季数据生成：

```powershell
python search_index_builder.py
```

用浏览器打开本目录的 `index.html` 可查看赛果页。也可从仓库根目录运行 `py -m http.server 8000`，再访问 `http://localhost:8000/f1_results_scraper/`。页面按需读取所选赛季的数据；用 `file://` 浏览时，应保留页面与 `site_data/` 的相对目录结构。

### 页面和搜索行为

- 年份选择器列出 `site_data/index.js` 中的赛季。
- 数据类别包括比赛、车手、车队和奖项；比赛结果还可按大奖赛和会话查看。
- 主页面搜索框输入至少两个字符后显示最多八条建议，按 Enter 打开完整搜索页。
- 搜索词可匹配车手、车队、大奖赛名称和底盘型号；多词查询中的每个词都须命中这些字段中的任意一个。
- 完整搜索页读取按年份组织的索引；仅匹配大奖赛名称时，同一赛季的同一场大奖赛只列一条结果。
- 页面日期采用 F1 官方结果页的赛事级日期。较早赛季通常显示比赛日，现代赛季通常显示比赛周末日期范围；这些日期不表示单场练习、排位或正赛的实际开赛时间。

如果页面无法读取某一赛季，请确认 `site_data/index.js` 和对应的 `site_data/YYYY.js` 存在。搜索无法读取时，请检查 `site_data/search_index/index.js` 与对应年份分片。

## 数据记录格式

`data/records.jsonl` 每行是一张网页表格的记录，字段示例如下：

```json
{
  "year": 2026,
  "section": "races",
  "race": {"race_id": "1279", "slug": "australia", "url": "https://www.formula1.com/..."},
  "session": "race-result",
  "url": "https://www.formula1.com/...",
  "title": "...",
  "table_index": 0,
  "columns": ["Pos.", "No.", "Driver", "Team", "Chassis", "Laps", "Time / Retired", "Pts."],
  "rows": [
    {"Pos.": "1", "No.": "63", "Driver": "George Russell RUS", "Team": "Mercedes", "Chassis": "F1 W17"}
  ]
}
```

记录也可能包含列链接、图片、表格脚注或原始 `cells`。表格结构不规则时，原始单元格仍保存在记录中。`failures.jsonl` 每行记录一个无法读取的 URL 和对应错误。

## GitHub Actions

仓库工作流 `.github/workflows/update-f1-data.yml` 可手动启动，并按每周一 12:00（Asia/Shanghai）运行。工作流使用 UTC 当前年份抓取比赛、车手、车队和奖项资料，读取当季 StatsF1 参赛车辆信息，生成赛果页面、年度数据和搜索索引。`action_change_report.py` 将赛季表格整理为 Markdown 摘要，供工作流输出和钉钉通知使用。生成的 `index.html` 和 `site_data/` 文件由工作流提交到仓库。配置仓库密钥 `DINGTALK_WEBHOOK` 后，钉钉通知会包含运行状态和表格摘要。

该工作流负责数据抓取、静态文件构建和仓库数据提交。GitHub Pages 页面发布由仓库 Pages 配置或独立部署工作流负责。

## 来源和请求

比赛结果来自 [Formula 1 官方 Results 页面](https://www.formula1.com/en/results.html)，底盘型号资料来自 StatsF1。请遵守相关网站的使用条款并合理控制请求频率。程序访问公开页面，不绕过登录、验证码或访问控制。
