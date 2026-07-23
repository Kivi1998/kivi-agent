-- kivi-agent Wave 4 测试用种子数据（agent: package-e2e-real-v4）
--
-- 兼容性：使用 SQLite / Postgres 通用子集，方便 tests/e2e_real/test_db_real.py
-- 用 sqlite3 直跑 + docker-compose.test.yml 跑 Postgres 都用同一份脚本。
--
-- 通用规则：
--   - 主键用 INTEGER PRIMARY KEY（不显式 SERIAL/AUTOINCREMENT；两库都接受）
--   - 字符串用 TEXT（替代 VARCHAR；两库都支持）
--   - 金额用 NUMERIC（替代 DECIMAL；两库都支持）
--   - 时间戳用 TEXT DEFAULT CURRENT_TIMESTAMP（替代 TIMESTAMP DEFAULT NOW()）

-- ---- users 表：3 条固定用户 ----
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---- orders 表：3 条订单，关联 users.id ----
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    product_id INTEGER,
    amount NUMERIC(10, 2),
    status TEXT
);

-- ---- 种子数据 ----
-- 选取原则：姓名覆盖 ABC + 订单状态覆盖 paid/pending 组合
INSERT INTO users (id, name, email) VALUES
    (1, 'Alice', 'alice@example.com'),
    (2, 'Bob', 'bob@example.com'),
    (3, 'Charlie', 'charlie@example.com');

INSERT INTO orders (id, user_id, product_id, amount, status) VALUES
    (1, 1, 101, 99.50, 'paid'),
    (2, 2, 102, 150.00, 'pending'),
    (3, 3, 103, 250.00, 'paid');
