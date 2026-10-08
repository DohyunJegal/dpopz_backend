# DPOPz backend

DPOPz(Double Play Optionz) API 서버

FastAPI + SQLite(WAL)

```
main.py     앱 진입점 (uvicorn main:app)
app/        API 구현 내용
schema.sql  DB 스키마 (처음 접속 시 자동 적용)
```

## 로컬 작업

```bash
pip install -r requirements-dev.txt

# 채보 목록/Lv.x를 zasa에서 가져와 dpopz.db 생성
python -m app.zasa 

uvicorn main:app --port 8000 --reload
```

## 서버 배포

- `pip install -r requirements.txt` 수행, DB 경로는 환경변수 `DPOPZ_DB`(기본 `./dpopz.db`)
- `DPOPZ_COOKIE_SECURE=1` - HTTPS 필수
- 실행: `uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1`(systemd 서비스를 권장)
- nginx(HTTPS) 뒤에 두고, 로그인 시도 제한에 쓸 실제 클라이언트 IP는 Vercel이 넣어 준 값을 그대로 전달
  ```nginx
  location /api/ {
      proxy_pass http://127.0.0.1:8000;
      proxy_set_header Host $host;
      # $proxy_add_x_forwarded_for를 쓰면 Vercel IP가 끼어들음
      proxy_set_header X-Forwarded-For $http_x_forwarded_for;   
      proxy_set_header X-Forwarded-Proto $scheme;
  }
  ```
- 백업: `sqlite3 dpopz.db ".backup '/backup/dpopz-$(date +%F).db'"`
