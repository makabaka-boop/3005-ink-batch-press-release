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
- 批次记录入库重量与可用重量；创建工单时填写计划用量，同一事务内校验并扣减（预占），批次列表与工单记录实时展示预占结果；编辑批次入库重量时，可用重量按差额同步增减，重量按业务精度（3 位小数）展示。
- 扣减与取消均为数据库原子操作（条件 UPDATE + BEGIN IMMEDIATE 串行化写事务）：并发预占时只有余额足够的工单成功，并发取消时只有首次请求返还用量，不产生超额预占或重复返还。
- 计划中的工单可取消，服务端仅允许首次取消并将预占用量原量返还批次，重复取消返回 409 冲突提示；已完成工单不能取消。
- 生产结束后在工单卡片登记实际用量并完成工单：服务端以原计划预占为基准在同一事务内结算批次余额——少用返还差额、超用从可用重量补扣，并记录实际用量与完成时间、把工单转为已完成；超用差额超过批次可用重量时返回 409 余额不足，工单与库存均保持原值，页面保留输入便于修正；已取消/已完成工单再次提交返回 409 冲突原因。完成结果刷新后仍可在工单卡片查看实际用量、结算差额与完成时间。
- 创建唯一工单号的上机记录，关联批次、印刷机、承印材料、计划日期、操作人与说明。
- 工单创建时检查计划日期是否过期，以及批次是否待检、不合格或隔离；不合格与待检分别记录问题类型。
- 问题可更新为待处理、已确认、特批放行、已关闭；特批放行必须填写理由。
- 首页展示批次、合格、30 天内到期、工单、未处理问题指标，支持批次及问题多条件筛选。
- 重复编号返回 409，不存在资源返回 404，停用批次上机返回 409，可用重量不足返回 409，缺失/非法字段返回 422；明确填写零计划用量的新工单按非法字段拒绝（未填写计划用量的旧请求仍按兼容默认值处理）。
- 启动时自动为既有数据库补齐重量与工单状态字段：历史批次按 `DEFAULT_RECEIVED_WEIGHT`（默认 100 kg）回填入库/可用重量，历史工单计划用量记 0、实际用量与完成时间保持为空并继续呈现计划中的未完成语义，不反向扣减；未携带新字段的旧请求按兼容默认值处理。

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
- `GET/POST /api/jobs`，`PATCH /api/jobs/{id}/cancel`，`PATCH /api/jobs/{id}/complete`
- `GET /api/issues`，`PATCH /api/issues/{id}`
- `GET /api/stats`

技术栈为 FastAPI、SQLAlchemy、SQLite、React、TypeScript、Vite 与 Nginx。标准 viewport 与断点布局保证桌面及 390px 窄屏无页面级横向溢出。
