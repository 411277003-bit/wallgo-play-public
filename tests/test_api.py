"""執行：python tests/test_api.py   （需要 pip install -r requirements.txt，不需要 MongoDB）

HTTP API 的單元測試、邊界測試與資安測試。資料庫用 tests/fake_mongo.py 的記憶體版本。
分成四組：
  1. 正常流程   註冊、登入、重設密碼、改資料、戰績、好友
  2. 邊界值     欄位缺漏、空白、長度上下限、型別錯誤、格式錯誤
  3. 資安       密碼雜湊、救援碼、暴力破解限制、冒用身分、XSS 字元
  4. 模糊測試   對每支 API 亂送各種型別的資料，伺服器都不能回 500
"""
import itertools
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import fake_mongo  # noqa: E402
users, history, friends = fake_mongo.install()

from server.app_factory import create_app  # noqa: E402
from server.auth_token import issue  # noqa: E402
from server.ratelimit import login_limiter, reset_limiter  # noqa: E402

app = create_app()
c = app.test_client()
failed = 0
total = 0


def check(name, ok, detail=''):
    global failed, total
    total += 1
    print(f'  {"✓" if ok else "✗"} {name}' + (f'   ← {detail}' if not ok and detail else ''))
    failed += 0 if ok else 1


def section(title):
    print(f'\n【{title}】')


def post(path, body=None, token=None, **kw):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    if 'data' in kw:                      # 直接送原始內容（測非 JSON）
        return c.post(path, headers=headers, **kw)
    return c.post(path, json=body, headers=headers)


def register(uid, name='Tester', pwd='pass1234'):
    r = post('/api/register', {'id': uid, 'username': name, 'password': pwd})
    return r.get_json()


# ════════════════════════════════════════════════════════════
section('1. 正常流程')

res = register('#1001', 'Alice', 'alicepw')
check('註冊成功', res['success'] is True)
check('註冊回傳登入 token', isinstance(res.get('token'), str) and len(res['token']) > 20)
check('註冊回傳救援碼（XXXX-XXXX）', isinstance(res.get('recovery_code'), str) and len(res['recovery_code']) == 9)
alice_token, alice_code = res['token'], res['recovery_code']
stored = users.find_one({'id': '#1001'})
check('密碼以雜湊儲存，資料庫看不到原文', stored['password'] != 'alicepw' and stored['password'].startswith(('scrypt:', 'pbkdf2:')))
check('救援碼也只存雜湊', alice_code.replace('-', '') not in json.dumps(stored))
check('同一個 ID 不能註冊兩次', register('#1001', 'Fake', 'xxxx')['success'] is False)

r = post('/api/login', {'id': '#1001', 'password': 'alicepw'}).get_json()
check('正確密碼可以登入並拿到 token', r['success'] and r.get('token'))
check('一般登入不會重發救援碼', 'recovery_code' not in r)
check('錯誤密碼不能登入', post('/api/login', {'id': '#1001', 'password': 'wrong'}).get_json()['success'] is False)
check('不存在的 ID 不能登入', post('/api/login', {'id': '#9999', 'password': 'x'}).get_json()['success'] is False)

# 舊版留下的明文密碼帳號
users.insert_one({'id': '#0007', 'username': 'Old', 'password': 'oldpw', 'avatar': 'O', 'is_online': 0})
r = post('/api/login', {'id': '#0007', 'password': 'oldpw'}).get_json()
check('舊帳號（明文密碼）仍然可以登入', r['success'] is True)
check('舊帳號登入後密碼自動換成雜湊', users.find_one({'id': '#0007'})['password'].startswith(('scrypt:', 'pbkdf2:')))
check('舊帳號第一次登入會補發救援碼', bool(r.get('recovery_code')))
check('換成雜湊後用同一個密碼還能登入', post('/api/login', {'id': '#0007', 'password': 'oldpw'}).get_json()['success'])

r = post('/api/reset_password', {'id': '#1001', 'recovery_code': alice_code, 'new_password': 'newpass'}).get_json()
check('用救援碼可以重設密碼', r['success'] is True)
check('重設後發一組新的救援碼', r.get('recovery_code') and r['recovery_code'] != alice_code)
check('新密碼可以登入', post('/api/login', {'id': '#1001', 'password': 'newpass'}).get_json()['success'])
check('舊密碼不能再登入', not post('/api/login', {'id': '#1001', 'password': 'alicepw'}).get_json()['success'])
check('用過的救援碼不能再用', not post('/api/reset_password', {'id': '#1001', 'recovery_code': alice_code,
                                                       'new_password': 'again1'}).get_json()['success'])
check('救援碼不分大小寫、可省略減號', post('/api/reset_password', {
    'id': '#1001', 'recovery_code': r['recovery_code'].replace('-', '').lower(), 'new_password': 'newpass'}).get_json()['success'])

r = post('/api/update_profile', {'username': 'Alice2', 'avatar': '🐱'}, alice_token).get_json()
check('帶 token 可以改自己的資料', r['success'] and users.find_one({'id': '#1001'})['username'] == 'Alice2')
r = post('/api/update_profile', {'username': 'Alice3'}, alice_token).get_json()
check('沒填頭像時用暱稱第一個字', r['user']['avatar'] == 'A')

game = {'date': '2026/11/25 下午10:00:00', 'winner': 'Alice(你)', 'winScore': 20,
        'details': '紅(你):20 | 藍:10', 'game_id': 'abc-123', 'replayData': '[]'}
check('存戰績成功', post('/api/save_history', game, alice_token).get_json()['success'])
post('/api/save_history', game, alice_token)
check('同一局重送只會存一筆', len(history.find({'user_id': '#1001'})) == 1)
h = post('/api/get_history', {}, alice_token).get_json()
check('讀得到自己的戰績', h['success'] and len(h['history']) == 1 and h['history'][0]['winScore'] == 20)
g = c.get('/api/global_stats').get_json()
check('全站統計不需登入就能看', g['success'] and g['totalGames'] == 1 and g['bestScore'] == 20)

bob = register('#2002', 'Bob', 'bobpass')
carol = register('#3003', 'Carol', 'carolpw')
r = post('/api/send_friend_request', {'receiver_id': '#2002'}, alice_token).get_json()
check('送出好友邀請', r['success'])
check('重複邀請會被擋', not post('/api/send_friend_request', {'receiver_id': '#2002'}, alice_token).get_json()['success'])
check('反方向的重複邀請也會被擋', not post('/api/send_friend_request', {'receiver_id': '#1001'}, bob['token']).get_json()['success'])
check('不能加自己', not post('/api/send_friend_request', {'receiver_id': '#1001'}, alice_token).get_json()['success'])
check('不存在的玩家不能加', not post('/api/send_friend_request', {'receiver_id': '#8888'}, alice_token).get_json()['success'])
fl = post('/api/get_friends', {}, bob['token']).get_json()
check('對方看得到待審核邀請', [f['id'] for f in fl['pending_received']] == ['#1001'])
check('收到邀請的人可以同意', post('/api/handle_friend_request', {'requester_id': '#1001', 'action': 'accept'},
                                 bob['token']).get_json()['success'])
check('同意後雙方都是好友', [f['id'] for f in post('/api/get_friends', {}, alice_token).get_json()['friends']] == ['#2002'])
check('不合法的 action 被拒絕', not post('/api/handle_friend_request', {'requester_id': '#1001', 'action': 'hack'},
                                     bob['token']).get_json()['success'])

# ════════════════════════════════════════════════════════════
section('2. 邊界值')


def status(path, body, token=None):
    return post(path, body, token).status_code


check('註冊缺 username → 400（以前是 500）', status('/api/register', {'id': '#5001', 'password': 'abcd'}) == 400)
check('註冊 username 是空字串 → 400（以前是 500）', status('/api/register', {'id': '#5001', 'username': '', 'password': 'abcd'}) == 400)
check('註冊 username 只有空白 → 400', status('/api/register', {'id': '#5001', 'username': '   ', 'password': 'abcd'}) == 400)
check('註冊 username 是數字 → 400', status('/api/register', {'id': '#5001', 'username': 123, 'password': 'abcd'}) == 400)
check('註冊缺 id → 400（以前會存成 null）', status('/api/register', {'username': 'x', 'password': 'abcd'}) == 400)
check('暱稱剛好 20 字 → 可以', status('/api/register', {'id': '#5002', 'username': 'A' * 20, 'password': 'abcd'}) == 200)
check('暱稱 21 字 → 400', status('/api/register', {'id': '#5003', 'username': 'A' * 21, 'password': 'abcd'}) == 400)
check('暱稱 10 萬字 → 400（以前照收）', status('/api/register', {'id': '#5003', 'username': 'A' * 100000, 'password': 'abcd'}) == 400)
check('暱稱含控制字元 → 400', status('/api/register', {'id': '#5003', 'username': 'a\x00b', 'password': 'abcd'}) == 400)
check('暱稱含中文與 emoji → 可以', status('/api/register', {'id': '#5004', 'username': '牆壁大師🧱', 'password': 'abcd'}) == 200)
check('密碼 3 字 → 400', status('/api/register', {'id': '#5005', 'username': 'x', 'password': 'abc'}) == 400)
check('密碼剛好 4 字 → 可以', status('/api/register', {'id': '#5005', 'username': 'x', 'password': 'abcd'}) == 200)
check('密碼剛好 64 字 → 可以', status('/api/register', {'id': '#5006', 'username': 'x', 'password': 'p' * 64}) == 200)
check('密碼 65 字 → 400', status('/api/register', {'id': '#5007', 'username': 'x', 'password': 'p' * 65}) == 400)
check('ID 沒有 # → 400', status('/api/register', {'id': '5008', 'username': 'x', 'password': 'abcd'}) == 400)
check('ID 只有 # → 400', status('/api/register', {'id': '#', 'username': 'x', 'password': 'abcd'}) == 400)
check('ID # 加 16 碼 → 可以', status('/api/register', {'id': '#' + 'a' * 16, 'username': 'x', 'password': 'abcd'}) == 200)
check('ID # 加 17 碼 → 400', status('/api/register', {'id': '#' + 'a' * 17, 'username': 'x', 'password': 'abcd'}) == 400)
check('ID 含中文 → 400', status('/api/register', {'id': '#玩家', 'username': 'x', 'password': 'abcd'}) == 400)
check('ID 含空白 → 400', status('/api/register', {'id': '#12 34', 'username': 'x', 'password': 'abcd'}) == 400)
check('body 不是 JSON → 400', post('/api/login', data='hello', content_type='text/plain').status_code == 400)
check('body 是 JSON 陣列 → 400', status('/api/login', [1, 2, 3]) == 400)
check('body 是 null → 400', post('/api/login', data='null', content_type='application/json').status_code == 400)
check('錯誤回應也是 JSON（前端讀得到訊息）', post('/api/login', [1]).get_json()['success'] is False)
check('頭像 4 字以內 → 可以', status('/api/update_profile', {'username': 'A', 'avatar': '👨‍👩'}, alice_token) == 200)
check('頭像太長 → 400', status('/api/update_profile', {'username': 'A', 'avatar': 'ABCDE'}, alice_token) == 400)
for score, ok in ((0, True), (49, True), (-1, False), (50, False), ('10', False), (True, False), (None, False), (3.5, False)):
    check(f'winScore = {score!r} → {"可以" if ok else "400"}',
          (status('/api/save_history', {**game, 'game_id': f'g{random.random()}'[:20].replace('.', ''),
                                         'winScore': score}, alice_token) == 200) == ok)
check('覆盤資料超過 1.5 MB → 400', status('/api/save_history', {**game, 'replayData': 'x' * 1_600_000}, alice_token) == 400)
check('整個請求超過 2 MB → 413', status('/api/save_history', {**game, 'replayData': 'x' * 2_200_000}, alice_token) == 413)
check('game_id 含奇怪字元 → 400', status('/api/save_history', {**game, 'game_id': '../../etc'}, alice_token) == 400)
check('不存在的網址 → 404 JSON', c.get('/api/nope').status_code == 404 and c.get('/api/nope').get_json()['success'] is False)

# ════════════════════════════════════════════════════════════
section('3. 資安')

check('不帶救援碼不能重設密碼（以前任何人都能改別人密碼）',
      status('/api/reset_password', {'id': '#2002', 'new_password': 'hacked'}) == 400)
check('救援碼錯誤不能重設', not post('/api/reset_password', {'id': '#2002', 'recovery_code': 'AAAA-AAAA',
                                                          'new_password': 'hacked'}).get_json()['success'])
check('Bob 的密碼沒有被改掉', post('/api/login', {'id': '#2002', 'password': 'bobpass'}).get_json()['success'])
check('帳號不存在與救援碼錯誤回一樣的訊息（不洩漏帳號是否存在）',
      post('/api/reset_password', {'id': '#7777', 'recovery_code': 'AAAA-AAAA', 'new_password': 'xxxx'}).get_json()['message']
      == post('/api/reset_password', {'id': '#2002', 'recovery_code': 'AAAA-AAAA', 'new_password': 'xxxx'}).get_json()['message'])

reset_limiter.reset()
for _ in range(5):
    post('/api/reset_password', {'id': '#3003', 'recovery_code': 'ZZZZ-ZZZZ', 'new_password': 'hacked'})
r = post('/api/reset_password', {'id': '#3003', 'recovery_code': carol['recovery_code'], 'new_password': 'hacked'})
check('救援碼錯 5 次後，連正確的也暫時擋掉（防暴力猜測）', r.status_code == 429)

login_limiter.reset()
for _ in range(5):
    post('/api/login', {'id': '#3003', 'password': 'guess'})
check('密碼錯 5 次後暫時鎖住 → 429', post('/api/login', {'id': '#3003', 'password': 'carolpw'}).status_code == 429)
check('其他帳號不受影響', post('/api/login', {'id': '#2002', 'password': 'bobpass'}).get_json()['success'])
login_limiter.reset()
check('解鎖後正確密碼可以登入', post('/api/login', {'id': '#3003', 'password': 'carolpw'}).get_json()['success'])

check('改資料不帶 token → 401', status('/api/update_profile', {'id': '#2002', 'username': 'pwned'}) == 401)
check('偽造的 token → 401', status('/api/update_profile', {'username': 'pwned'}, 'fake.token.value') == 401)
forged = alice_token[:-4] + ('AAAA' if not alice_token.endswith('AAAA') else 'BBBB')
check('竄改過簽章的 token → 401', status('/api/update_profile', {'username': 'pwned'}, forged) == 401)
post('/api/update_profile', {'id': '#2002', 'username': 'pwned'}, carol['token'])
check('body 裡寫別人的 id 也只會改到自己', users.find_one({'id': '#2002'})['username'] == 'Bob'
      and users.find_one({'id': '#3003'})['username'] == 'pwned')

post('/api/save_history', {**game, 'game_id': 'bob-game'}, bob['token'])
post('/api/clear_history', {'user_id': '#2002'}, carol['token'])
check('不能清除別人的戰績（以前只要知道 ID 就能清）', len(history.find({'user_id': '#2002'})) == 1)
check('清除戰績不帶 token → 401', status('/api/clear_history', {'user_id': '#2002'}) == 401)
check('讀戰績不帶 token → 401', status('/api/get_history', {'user_id': '#2002'}) == 401)
post('/api/save_history', {**game, 'user_id': '#2002', 'game_id': 'spoof'}, carol['token'])
check('存戰績時 body 的 user_id 被忽略', history.find_one({'game_id': 'spoof'})['user_id'] == '#3003')

post('/api/send_friend_request', {'receiver_id': '#3003'}, bob['token'])
r = post('/api/handle_friend_request', {'requester_id': '#2002', 'action': 'accept'}, alice_token).get_json()
check('不能替別人同意好友邀請', not r['success'] and friends.find_one({'requester_id': '#2002'})['status'] == 'pending')
r = post('/api/send_friend_request', {'requester_id': '#2002', 'receiver_id': '#5004'}, carol['token']).get_json()
check('送邀請時不能冒用別人的名義', friends.find_one({'receiver_id': '#5004'})['requester_id'] == '#3003')

xss_id = "#x');alert(1);//"
check("ID 不能含引號、括號（擋掉 onclick XSS 的 payload）",
      status('/api/register', {'id': xss_id, 'username': 'x', 'password': 'abcd'}) == 400)
r = register('#6006', '<b onclick=x>hi</b>', 'abcd')
check('暱稱可以有 < >，但存的是純文字（前端一律 esc() 後顯示）', r['success'] and r['user']['name'] == '<b onclick=x>hi</b>')
check('token 是給別人的就只能代表那個人', issue('#2002') != issue('#3003'))

# ════════════════════════════════════════════════════════════
section('4. 模糊測試：亂送資料，伺服器都不能回 500')

weird = [None, True, 0, -1, 2**63, 3.14, '', ' ', 'x' * 5000, '#1234', "'\"<>", [], [1], {}, {'a': 1}, '\x00', '🧱' * 50]
endpoints = ['/api/register', '/api/login', '/api/reset_password', '/api/update_profile', '/api/save_history',
             '/api/get_history', '/api/clear_history', '/api/send_friend_request', '/api/get_friends',
             '/api/handle_friend_request']
fields = ['id', 'username', 'password', 'new_password', 'recovery_code', 'avatar', 'winScore', 'date', 'winner',
          'details', 'game_id', 'replayData', 'receiver_id', 'requester_id', 'action', 'user_id']
rng = random.Random(42)
codes = {}
n = 0
for ep, tok in itertools.product(endpoints, [None, bob['token']]):
    for _ in range(60):
        body = {f: rng.choice(weird) for f in rng.sample(fields, rng.randint(0, 6))}
        login_limiter.reset(); reset_limiter.reset()
        code = post(ep, body, tok).status_code
        codes[code] = codes.get(code, 0) + 1
        n += 1
check(f'{n} 個亂數請求沒有任何 500（狀態碼分布 {dict(sorted(codes.items()))}）', 500 not in codes)

print(f'\n共 {total} 項，{failed} 個失敗' if failed else f'\n全部 {total} 項通過')
sys.exit(1 if failed else 0)
