# F1 Archive

F1 Archive 是一个个人 Formula 1 数据与专题静态站点。仓库包含历年比赛结果、车手与车队排名、奖项资料，以及 2026 赛季特殊涂装图片记录。网页使用 HTML、CSS 和 JavaScript 呈现，不需要数据库或应用服务器。

## 网站入口

仓库根目录的 [`index.html`](index.html) 是导航页。各内容页面如下：

| 页面 | 内容 |
| --- | --- |
| [F1 历年结果数据](f1_results_scraper/index.html) | 1950 年起按赛季整理的比赛、车手、车队和奖项表格。 |
| [2026 特殊涂装](26_special_livery/index.html) | 按大奖赛浏览特殊涂装记录和本地图片。 |
| [车模商店监控](https://stdquantum.github.io/sparkmodel-monitor/) | 车模商品监控及静态目录。 |
| [Raceland 周报](https://stdquantum.github.io/raceland_newsletter/) | 按周整理的图片周报和文字搜索。 |

## 仓库内容

```text
.
├── index.html                         # 网站导航页
├── f1_results_scraper/                # F1 结果抓取程序和赛果页面
│   ├── scraper.py                     # 比赛及各场次结果抓取
│   ├── standings_scraper.py           # 车手、车队和奖项抓取
│   ├── statsf1_enrich.py              # 底盘型号和赛果说明脚注
│   ├── build_static.py                # 静态页面与年度数据生成
│   ├── search_index_builder.py        # 搜索索引生成
│   ├── action_change_report.py        # Actions 使用的赛季表格摘要
│   ├── template.html                  # 赛果页面模板
│   ├── index.html                     # 年度赛果浏览页
│   ├── search.html                    # 完整搜索页
│   ├── site_data/                     # 年度数据、清单和搜索索引
│   └── README.md                      # 抓取器、数据格式和命令说明
├── 26_special_livery/                 # 2026 特殊涂装专题
│   ├── index.html                     # 涂装浏览页
│   ├── 26特涂统计.md                  # 专题文字记录
│   └── 26特涂统计.assets/             # 图片资源
└── .github/workflows/
    └── update-f1-data.yml             # 当前赛季数据工作流
```

`f1_results_scraper/data/` 存放本地抓取缓存、记录和失败 URL，默认由 Git 忽略。`site_data/` 存放浏览器直接读取的年度文件和搜索索引，是赛果页面运行所需的静态数据。

## 浏览页面

用浏览器打开仓库根目录的 `index.html` 即可浏览现有页面。若浏览器限制本地文件访问，可在仓库根目录运行静态 HTTP 服务器：

```powershell
py -m http.server 8000
```

然后打开 <http://localhost:8000/>。部署到静态托管服务时，保留页面引用的目录结构和 `site_data/` 文件即可。仓库中的数据工作流负责抓取和生成赛果文件；GitHub Pages 的发布由 Pages 设置或独立部署工作流决定。

## F1 结果数据

抓取程序读取 Formula 1 官方公开 Results 页面，将页面表格整理成 JSONL 记录，再生成年份分片和搜索索引。安装方式、命令参数、数据结构及断点续跑说明见 [`f1_results_scraper/README.md`](f1_results_scraper/README.md)。常见的本地流程如下：

```powershell
cd f1_results_scraper
conda activate env3.10
python -m pip install -r requirements.txt

python scraper.py --start-year 1950 --end-year 2026
python standings_scraper.py --start-year 1950 --end-year 2026
python statsf1_enrich.py --start-year 1950 --end-year 2026
python build_static.py
```

`scraper.py` 收集赛季日程及大奖赛相关的练习赛、排位赛、起步顺序、进站摘要、最快圈和正赛结果等页面。`standings_scraper.py` 收集车手、车队与奖项页面。`statsf1_enrich.py` 参照 StatsF1 的参赛车辆资料，为正赛结果提供底盘型号和符合筛选条件的说明脚注。`build_static.py` 读取抓取记录并输出网页文件。

赛果页按赛季读取数据文件。搜索索引按年份分片，搜索字段包括车手、车队、大奖赛和底盘型号；多个关键词可以匹配不同字段。输入框提供匹配建议，完整搜索页列出匹配赛果。只以大奖赛名称检索时，同一赛季的同一场大奖赛只显示一条。

## GitHub Actions

`.github/workflows/update-f1-data.yml` 可由 GitHub 手动启动，也按每周一 12:00（Asia/Shanghai）运行。工作流以 UTC 当前年份为目标，安装 Python 依赖，抓取当季比赛、车手、车队和奖项资料，沿 StatsF1 的赛事链接读取底盘信息，再构建赛果页面、年度数据和搜索索引。工作流还整理赛季表格摘要；配置 `DINGTALK_WEBHOOK` 仓库密钥时，会向钉钉发送运行结果和摘要。生成的赛果页面及数据文件会由工作流写入仓库。

该工作流不负责 GitHub Pages 发布。静态页面的发布方式由仓库 Pages 配置或专门的部署工作流决定。

## 实现说明

- 网页由静态 HTML、CSS 和 JavaScript 组成，不依赖服务端数据库。
- 年份清单位于 `site_data/index.js`；各赛季表格位于 `site_data/YYYY.js`。页面选择赛季时读取对应数据文件。
- 搜索索引清单位于 `site_data/search_index/index.js`，各年份的索引单独存储。
- 特殊涂装页面引用仓库内的图片，并提供放大和灯箱浏览。
- 赛果日期沿用 F1 官方结果页显示的赛事日期；现代比赛通常显示整个周末的日期范围，并不代表各场次的实际开赛时间。

## 内容来源与使用

比赛结果来自 Formula 1 官方公开页面，底盘信息参照 StatsF1。专题图片和文字记录按大奖赛整理。抓取公开网页时应遵守对应网站的使用条款，并合理控制请求频率。数据、车队名称、图片及其他素材的权利归其各自权利人所有；转载或再发布前请确认适用的授权和网站条款。
