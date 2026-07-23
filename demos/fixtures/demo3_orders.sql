-- Demo 3 fixture: orders 表 + 20 行样例（agent: package-demo-v7）
-- 季度划分：Q1 = 2026-01/02/03；Q2 = 2026-04/05/06
-- 期望 Q1 总营收 = sum(amount) where month in (2026-01, 2026-02, 2026-03) = 44500
--
-- 表名 = products_<datasource_id> ：与 query_database Tool 的演示版默认 SQL 模板对齐
-- （_mock_step1_generate_sql 默认生成 `SELECT * FROM products_<ds_id> LIMIT 10`）

CREATE TABLE IF NOT EXISTS products_ds_orders (
    id INTEGER PRIMARY KEY,
    product TEXT NOT NULL,
    region TEXT NOT NULL,
    month TEXT NOT NULL,  -- YYYY-MM
    amount INTEGER NOT NULL
);

INSERT OR REPLACE INTO products_ds_orders (id, product, region, month, amount) VALUES
    (1,  'Alpha 旗舰版', '华东', '2026-01',  8000),
    (2,  'Alpha 旗舰版', '华南', '2026-01',  5000),
    (3,  'Beta 标准版',  '华东', '2026-01',  3000),
    (4,  'Gamma 入门版', '华北', '2026-01',  1500),
    (5,  'Alpha 旗舰版', '华东', '2026-02',  9000),
    (6,  'Beta 标准版',  '华南', '2026-02',  3500),
    (7,  'Gamma 入门版', '华东', '2026-02',  2000),
    (8,  'Alpha 旗舰版', '华北', '2026-03',  6000),
    (9,  'Beta 标准版',  '华东', '2026-03',  4000),
    (10, 'Gamma 入门版', '华南', '2026-03',  2500),
    -- Q2 数据（不计入 Q1 总营收）
    (11, 'Alpha 旗舰版', '华东', '2026-04',  9500),
    (12, 'Beta 标准版',  '华南', '2026-04',  3800),
    (13, 'Gamma 入门版', '华北', '2026-04',  2200),
    (14, 'Alpha 旗舰版', '华东', '2026-05',  8800),
    (15, 'Beta 标准版',  '华北', '2026-05',  4200),
    (16, 'Gamma 入门版', '华东', '2026-05',  2400),
    (17, 'Alpha 旗舰版', '华南', '2026-06',  7500),
    (18, 'Beta 标准版',  '华东', '2026-06',  3700),
    (19, 'Gamma 入门版', '华北', '2026-06',  2300),
    (20, 'Alpha 旗舰版', '华东', '2026-06',  9100);
