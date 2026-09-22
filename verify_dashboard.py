import os, sqlite3
os.chdir(r'c:\Users\VOBISSNOC\OneDrive - Vobiss Solutions limited\Desktop\PRINCE\ADUFARMS-RECOVERY')
import app

app.app.testing = True
client = app.app.test_client()
with client.session_transaction() as s:
    s['user_id'] = 1
    s['username'] = 'admin'
    s['full_name'] = 'Admin'
    s['role'] = 'ADMIN'
resp = client.get('/dashboard')
print('STATUS', resp.status_code)
print(resp.get_data(as_text=True)[:2000])
