import requests
import uuid

user = 'testuser' + str(uuid.uuid4())[:8]
url = 'https://decentra-store-backendapi.onrender.com/auth/register'
data = {'username': user, 'password': 'password123'}
requests.post(url, json=data)

url = 'https://decentra-store-backendapi.onrender.com/auth/login'
resp = requests.post(url, json=data)
token = resp.json().get('token')

headers = {'Authorization': f'Bearer {token}'}
url = 'https://decentra-store-backendapi.onrender.com/files/upload'
files = {'file': ('test.txt', b'hello world')}
data = {'encrypted_key': 'a', 'key_iv': 'b', 'file_iv': 'c'}
resp = requests.post(url, headers=headers, files=files, data=data)
print('Upload:', resp.status_code, resp.text)
