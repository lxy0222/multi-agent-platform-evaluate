import psycopg2
import pandas as pd
import json

# ================= 配置区 =================
DB_CONFIG = {
    "host": "pgm-bp179mnihnm4in80.pg.rds.aliyuncs.com",  # 替换为你的数据库IP
    "port": "5432",  # 替换为你的数据库端口
    "dbname": "dify",  # 数据库名称
    "user": "dify",  # 数据库用户名
    "password": "slPs9kS7"  # 替换为你的数据库密码
}

EXPORT_FILE_NAME = "dify_raw_logs.csv"

# SQL 查询语句：关联会话表和消息表
# 提取：会话ID、会话名称、用户提问、AI回答、创建时间
# 可选：如果你只需要特定 App 的数据，可以在 WHERE 子句中加上 c.app_id = 'xxx'
QUERY = """
        SELECT m.id         AS message_id, \
               c.id         AS conversation_id, \
               c.name       AS conversation_name, \
               m.query      AS user_query, \
               m.answer     AS ai_answer, \
               m.created_at AS message_time
        FROM messages m \
                 JOIN \
             conversations c ON m.conversation_id = c.id
        WHERE m.query IS NOT NULL
          AND m.answer IS NOT NULL
        ORDER BY m.created_at DESC; \
        """


# ==========================================

def export_logs():
    print("正在连接数据库...")
    try:
        # 1. 建立数据库连接
        conn = psycopg2.connect(**DB_CONFIG)

        print("执行查询并提取数据...")
        # 2. 使用 pandas 直接读取 SQL 查询结果
        df = pd.read_sql_query(QUERY, conn)

        # 3. 处理时间格式 (将 Unix 时间戳/或UTC时间 转为可读时间)
        if not df.empty:
            # Dify 的 created_at 通常是 timestamp 类型，直接格式化即可
            df['message_time'] = pd.to_datetime(df['message_time']).dt.strftime('%Y-%m-%d %H:%M:%S')

            # 4. 导出为 CSV
            df.to_csv(EXPORT_FILE_NAME, index=False, encoding='utf-8-sig')
            print(f"✅ 导出成功！共提取了 {len(df)} 条对话记录。")
            print(f"📁 文件已保存至: {EXPORT_FILE_NAME}")
        else:
            print("⚠️ 未查询到任何对话数据。")

    except Exception as e:
        print(f"❌ 数据库连接或查询失败: {e}")

    finally:
        # 5. 关闭连接
        if 'conn' in locals() and conn:
            conn.close()
            print("数据库连接已断开。")


if __name__ == "__main__":
    export_logs()