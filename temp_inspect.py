import sqlite3
conn = sqlite3.connect('Usuarios.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = cursor.fetchall()
print('Tables:', tables)
for table in tables:
    table_name = table[0]
    print(f'Table: {table_name}')
    cursor.execute(f'PRAGMA table_info({table_name})')
    columns = cursor.fetchall()
    print('Columns:', columns)
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
    count = cursor.fetchone()[0]
    print(f'Records: {count}')
    if count > 0:
        cursor.execute(f'SELECT * FROM {table_name} LIMIT 3')
        samples = cursor.fetchall()
        print('Samples:', samples)
conn.close()