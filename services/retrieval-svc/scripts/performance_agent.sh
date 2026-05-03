#!/bin/bash

echo "⚡ PERFORMANCE AGENT"

if ! command -v k6 >/dev/null 2>&1; then
  echo "❌ k6 not installed"
  echo "Install: sudo apt install k6 OR brew install k6"
  exit 1
fi

cat > /tmp/k6_test.js <<'JS'
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
JS

k6 run /tmp/k6_test.js
