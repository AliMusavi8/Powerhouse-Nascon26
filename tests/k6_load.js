import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    guest_viewers: {
      executor: 'constant-vus',
      vus: 500,
      duration: '15s',
      exec: 'viewStream',
    },
    chat_posters: {
      executor: 'constant-vus',
      vus: 50,
      duration: '15s',
      exec: 'postChat',
    },
  },
  thresholds: {
    http_req_failed: ['rate==0.00'],
    http_req_duration: ['p(95)<800'],
  },
};

export function viewStream() {
  const res = http.get('http://localhost:8080/audit/v1/qr/match-m1?inspect=true');
  check(res, {
    'guest QR status is 200': (r) => r.status === 200,
    'has target_route': (r) => r.json('target_route') !== undefined,
  });
  sleep(0.1);
}

export function postChat() {
  const payload = JSON.stringify({
    chat_room_id: 'chat-cs-session-101',
    incoming_messages: [
      { message_id: `k6-${__VU}-${__ITER}`, sender: `user-${__VU}`, text: 'Live reaction' }
    ],
    check_dlq: false,
  });
  const res = http.post('http://localhost:8080/audit/v1/moderation/test', payload, {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'chat status is 200 or 201': (r) => r.status === 200 || r.status === 201,
  });
  sleep(0.2);
}
