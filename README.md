# Powerhouse: NaSCon '26 League & Club Operations Platform

Multi-tenant sports league and club-operations platform: backend API (FastAPI + PostgreSQL + Redis) and an Android app (Kotlin).

## Run the backend

```bash
cp .env.example .env          # set DAY1_SALT
DAY1_SALT=<salt> docker compose up -d --build
curl http://localhost:8080/health   # {"status":"ok"}
```

The API listens on `http://localhost:8080`. Baseline data is seeded on first start and by `POST /audit/v1/reset`.

## Demo accounts (password `Nascon@26`)

| Role | Email |
|---|---|
| Platform Super-Admin | admin@nascon.test |
| League Organizer (league-alpha-1) | organizer@nascon.test |
| Club Manager (club-alpha-1) | manager@nascon.test |
| Player (player-alpha-1) | player@nascon.test |
| General Viewer | viewer@nascon.test |
