import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
  vus: 10,
  duration: '10s',
};

export default function () {
  http.get('http://127.0.0.1:8000/health');
  sleep(1);
}
