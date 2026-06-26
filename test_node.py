import requests

url = 'https://a476c3297c62c9.lhr.life/health'
try:
    resp = requests.get(url, timeout=5)
    print('Health:', resp.status_code, resp.text)
except Exception as e:
    print('Health error:', e)

url = 'https://a476c3297c62c9.lhr.life/store'
try:
    resp = requests.post(url, json={"chunk_hash": "testhash", "data": "dGVzdA=="}, timeout=5)
    print('Store:', resp.status_code, resp.text)
except Exception as e:
    print('Store error:', e)
