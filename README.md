# F1 Archive

个人 Formula 1 数据与专题静态站点，包含历年比赛结果数据和 2026 赛季特殊涂装专题。项目不依赖后端服务，生成的页面可以直接用浏览器打开，也可以部署到 GitHub Pages 等静态托管服务。

## 在线入口

仓库根目录的 [`index.html`](index.html) 是项目导航页，当前包含：

- [F1 历年结果数据](f1_results_scraper/index.html)：1950 年至今的比赛、车手、车队和 Awards 数据；
- [2026 特殊涂装](26_special_livery/index.html)：按大奖赛整理的车队特殊涂装和图片；
- Spark 商店监控和 Raceland 周报的外部站点入口。

## 项目结构

```text
.
├── index.html                    # 项目总导航页
├── f1_results_scraper/            # F1 官方结果数据抓取与静态展示
│   ├── scraper.py                # 抓取比赛及各场比赛结果
│   ├── standings_scraper.py      # 抓取车手、车队和奖项
│   ├── build_static.py            # 生成按年份拆分的静态数据
│   ├── template.html              # 结果页模板
│   ├── index.html                # 结果数据页面
│   ├── site_data/                # 已构建的年份数据
│   └── README.md                 # 抓取项目的详细说明
├── 26_special_livery/             # 2026 特殊涂装专题
│   ├── index.html                # 图片卡片和灯箱浏览页面
│   ├── 26特涂统计.md             # 专题原始记录
│   └── 26特涂统计.assets/         # 专题图片资源
└── .github/workflows/             # GitHub Actions
    └── update-f1-data.yml         # 定期更新当前赛季结果数据
```

## 本地查看

无需安装依赖，直接用浏览器打开根目录的 `index.html` 即可浏览已经生成的静态页面。

如果浏览器不方便直接打开本地文件，也可以在仓库根目录启动一个简单的静态服务器：

```powershell
py -m http.server 8000
```

然后访问 <http://localhost:8000/>。

## 更新 F1 结果数据

详细说明见 [`f1_results_scraper/README.md`](f1_results_scraper/README.md)。基本流程如下：

```powershell
cd f1_results_scraper
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python scraper.py --start-year 1950 --end-year 2026
python standings_scraper.py --start-year 1950 --end-year 2026
python build_static.py
```

构建脚本会读取临时的 `data/` 目录，并更新 `index.html` 和 `site_data/`。其中 `data/` 包含缓存、记录和失败 URL，默认被 Git 忽略；`site_data/` 是静态网页实际使用的数据，应随构建结果一起保留。

首次运行或只想检查抓取结构时，可以先限制为一个赛季和一场比赛：

```powershell
python scraper.py --start-year 2026 --end-year 2026 --limit-races 1
```

## GitHub Actions

`.github/workflows/update-f1-data.yml` 支持手动触发，并按每周一 12:00（Asia/Shanghai）自动运行。工作流只抓取 UTC 当前年份，更新比赛、车手、车队和奖项数据，重新构建静态文件，并在有变化时提交回仓库。

该工作流不负责 GitHub Pages 的部署；Pages 部署应使用仓库的 Pages 设置或单独的部署工作流。

## 设计说明

- 所有页面都是静态 HTML、CSS 和 JavaScript，不需要数据库或后端；
- 结果页按年份拆分数据，切换年份时才加载对应的 `site_data/YYYY.js`，避免一次加载全部历史记录；
- 特殊涂装页面使用本地图片资源，支持图片放大、键盘切换和灯箱浏览；
- 抓取内容来自公开网页，请合理控制访问频率并遵守相关网站的使用条款。

## 许可与内容来源

本仓库主要用于个人整理、学习和展示。F1 结果数据、车队名称、图片及相关素材的版权归原权利人所有；使用或再发布前请确认相应授权和网站条款。
