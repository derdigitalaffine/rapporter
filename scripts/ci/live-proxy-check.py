"""Real external-proxy -> shipped Caddy -> Daphne/Redis acceptance, no browser."""
import json
import uuid
import requests
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

base = 'http://127.0.0.1:8080'
origin = 'https://familyos.test'
session = requests.Session()
response = session.post(base + '/api/auth/login/', json={'username': 'offline-e2e', 'password': 'offline-e2e-only-password', 'legacy': True}, timeout=10)
response.raise_for_status()
families = session.get(base + '/api/families/', timeout=10).json()
family = (families.get('results', []) if isinstance(families, dict) else families)[0]
family_id = family['id']
cookie = '; '.join(f'{item.name}={item.value}' for item in session.cookies)
url = f'ws://127.0.0.1:8080/ws/sync/{family_id}/'


def rejected(target=url, *, browser_origin=origin, cookies=''):
    try:
        with connect(target, origin=browser_origin, additional_headers={'Cookie': cookies}, open_timeout=5, close_timeout=1, proxy=None):
            raise AssertionError('Unauthorized WebSocket upgrade succeeded')
    except InvalidStatus as error:
        assert error.response.status_code == 403, error.response.status_code


rejected()
rejected(browser_origin='https://attacker.example', cookies=cookie)
rejected(target=f'ws://127.0.0.1:8080/ws/sync/{uuid.uuid4()}/', cookies=cookie)
with connect(url, origin=origin, additional_headers={'Cookie': cookie}, open_timeout=5, close_timeout=1, proxy=None) as socket:
    # A successful protocol handshake here is HTTP101 through both reverse proxies.
    snapshot = session.post(base + '/api/sync/', json={'protocol_version': 1, 'family_id': family_id, 'cursor': None, 'mutations': []}, timeout=10)
    snapshot.raise_for_status(); data = snapshot.json()
    mutation = {'mutation_id': str(uuid.uuid4()), 'entity_type': 'shopping_item', 'entity_id': str(uuid.uuid4()), 'operation': 'create', 'base_version': None,
                'data': {'shopping_list': data['snapshot']['shopping_lists'][0]['id'], 'name': 'Live proxy acceptance item'}}
    result = session.post(base + '/api/sync/', json={'protocol_version': 1, 'family_id': family_id, 'cursor': data['cursor'], 'mutations': [mutation]}, timeout=10)
    result.raise_for_status(); assert result.json()['mutation_results'][0]['status'] == 'applied'
    wakeup = json.loads(socket.recv(timeout=10))
    assert set(wakeup) == {'type', 'family_id', 'cursor'}, wakeup.keys()
    assert wakeup['type'] == 'sync_available' and wakeup['family_id'] == family_id
page = session.get(base + '/', timeout=5)
assert page.status_code == 200
assert 'wss://familyos.test' in page.headers['Content-Security-Policy']
print('PASS: HTTP101 + Redis wakeup through Nginx -> shipped Caddy -> Daphne; anonymous/wrong-origin/cross-family denied; HTTP preserved')
