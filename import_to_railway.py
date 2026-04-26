import pymysql
import ssl

# Railway MySQL credentials
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

config = {
    'host': 'shortline.proxy.rlwy.net',
    'port': 29384,
    'user': 'root',
    'password': 'hgPEpDdNfePTVYkMrvfqIRAMqlUVDjML',
    'database': 'railway',
    'charset': 'utf8mb4',
    'ssl': ssl_ctx,
}

print("Reading SQL file...")
with open(r'd:\thesis_db_backup.sql', 'r', encoding='utf-16') as f:
    sql_content = f.read()

print("Connecting to Railway MySQL...")
conn = pymysql.connect(**config)
cursor = conn.cursor()

# Split by semicolons and execute each statement
cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
statements = sql_content.split(';\n')
total = len(statements)

for i, stmt in enumerate(statements):
    stmt = stmt.strip()
    if stmt and not stmt.startswith('--') and not stmt.startswith('/*'):
        try:
            cursor.execute(stmt)
            if (i + 1) % 10 == 0:
                print(f"  Executed {i + 1}/{total} statements...")
        except Exception as e:
            print(f"  Warning at statement {i + 1}: {e}")

cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
conn.commit()
conn.close()
print(f"\nDone! Imported {total} statements to Railway MySQL.")
