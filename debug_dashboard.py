import os
os.chdir(r'c:\Users\VOBISSNOC\OneDrive - Vobiss Solutions limited\Desktop\PRINCE\ADUFARMS-RECOVERY')
import app

app.app.testing = True
client = app.app.test_client()
with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['username'] = 'admin'
    sess['full_name'] = 'Admin'
    sess['role'] = 'ADMIN'

resp = client.get('/dashboard')
print('STATUS', resp.status_code)
print(resp.get_data(as_text=True)[:2500])
