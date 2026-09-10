# 油墨批次上机放行台

面向印刷生产现场的轻量全栈放行工作台。管理油墨批次、上机工单、风险检查和处置闭环；首次启动自动加入 4 个批次、1 张工单及示例问题。

## Docker 一键启动

```bash
docker compose up --build
```

浏览器打开 <http://localhost:3005>。可通过 `WEB_PORT=3105 docker compose up --build` 改端口。Compose 项目名固定为 `ink-batch-press-release`，SQLite 数据保存在命名卷中。

停止使用 `docker compose down`；需清除运行数据时使用 `docker compose down -v`。

## 业务能力

- 新增、编辑、停用批次，记录唯一编号、颜色、供应商、日期、黏度、质检状态与备注。
- 创建唯一工单号的上机记录，关联批次、印刷机、承印材料、计划日期、操作人与说明。
- 工单创建时检查计划日期是否过期，以及批次是否待检、不合格或隔离；不合格与待检分别记录问题类型。
- 问题可更新为待处理、已确认、特批放行、已关闭；特批放行必须填写理由。
- 首页展示批次、合格、30 天内到期、工单、未处理问题指标，支持批次及问题多条件筛选。
- 重复编号返回 409，不存在资源返回 404，停用批次上机返回 409，缺失/非法字段返回 422。

## 本地测试

后端（Python 3.11+，根配置已提供模块路径，无需设置 `PYTHONPATH`）：

```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements-dev.txt
./.venv/bin/pytest
```

前端（Node.js 20+）：

```bash
cd frontend
npm ci
npm test
npm run build
```

## API

- `GET /health`
- `GET/POST /api/batches`，`PUT /api/batches/{id}`，`PATCH /api/batches/{id}/deactivate`
- `GET/POST /api/jobs`
- `GET /api/issues`，`PATCH /api/issues/{id}`
- `GET /api/stats`

技术栈为 FastAPI、SQLAlchemy、SQLite、React、TypeScript、Vite 与 Nginx。标准 viewport 与断点布局保证桌面及 390px 窄屏无页面级横向溢出。
