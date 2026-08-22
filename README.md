# AFU RTM — Murojaatlar tizimi

Alfraganus University Raqamliy texnologiyalar markazi (RTM) uchun ichki murojaatlar/helpdesk tizimi: Telegram bot + veb-interfeys, HEMIS orqali xodimlar identifikatsiyasi.

## Tarkibi

| Xizmat | Tavsif | Texnologiya |
|---|---|---|
| `backend` | REST API (frontend uchun yagona HTTP interfeys) | FastAPI + SQLAlchemy (async) |
| `bot` | Telegram bot | aiogram 3 |
| `worker` | Fon vazifalari (HEMIS sinxronizatsiya, bildirishnomalar, xabarlarni avtomatik o'chirish) | arq (Redis navbat) |
| `frontend` | Veb-interfeys | React + TypeScript + Vite + Tailwind |
| `shared` | Umumiy SQLAlchemy modellari/enumlar/sozlamalar (backend, bot, worker orasida) | Python paket |
| `postgres`, `redis` | Ma'lumotlar bazasi va keshlash/navbat | — |

`bot` va `worker` ma'lumotlar bazasiga to'g'ridan-to'g'ri ulanadi (`shared` orqali) — tezlik uchun `backend` API'sini chetlab o'tadi. `backend` faqat `frontend` uchun HTTP interfeysi hisoblanadi.

## Ishga tushirish

1. `.env.example` faylini `.env` nomiga nusxalab, qiymatlarni to'ldiring:
   ```bash
   cp .env.example .env
   ```
   Majburiy maydonlar: `POSTGRES_PASSWORD`, `API_HEMIS_TOKEN`, `ADMIN_EMAIL`/`ADMIN_PASSWORD`, `JWT_SECRET`, `TELEGRAM_BOT_TOKEN` (BotFather orqali yarating), `TELEGRAM_BOT_USERNAME`.

2. Barcha xizmatlarni ishga tushiring:
   ```bash
   docker compose up -d --build
   ```
   `backend` konteyneri ishga tushganda avtomatik ravishda: Alembic migratsiyalarini bajaradi, kategoriyalarni va admin hisobini (`ADMIN_EMAIL`/`ADMIN_PASSWORD`) yaratadi/yangilaydi — qo'shimcha qadam kerak emas.

3. Manzillar:
   - Veb-interfeys: http://localhost:5173
   - Backend API: http://localhost:8000 (Swagger: http://localhost:8000/docs)
   - Telegram bot: `.env`dagi `TELEGRAM_BOT_USERNAME` bo'yicha

4. Admin sifatida `.env`dagi `ADMIN_EMAIL`/`ADMIN_PASSWORD` bilan kiring va **"HEMIS sinxronizatsiya"** sahifasidan birinchi importni bajaring (bo'limlar va xodimlarni HEMIS'dan yuklab oladi).

## Odatiy foydalanish oqimi

1. Admin HEMIS sinxronizatsiyasini ishga tushiradi → bo'limlar va faol xodimlar (status `11`) import qilinadi.
2. Admin kerakli xodimlarni **Xodimlar** sahifasida "RTM xodimi" deb belgilaydi.
3. Oddiy xodim Telegram botga (`/start`) yoki veb-interfeysga ("Men xodimman") kirib, HEMIS ID raqami orqali shaxsini tasdiqlaydi (Telegram orqali kontakt ulashish talab qilinadi).
4. Tasdiqlangan xodim murojaat yaratadi (bot yoki veb).
5. Admin murojaatni RTM xodimiga tayinlaydi, muddat belgilaydi.
6. RTM xodimi botda ishni boshlaydi, murojaatchi bilan yozishadi, ichki muhokama qiladi, bajarilgach izoh bilan yopadi.
7. Murojaatchiga bildirishnoma boradi, u 1–5 baho qo'yadi.
8. **Top xodimlar** va **Statistika** sahifalarida natijalar ko'rinadi.

## Ishlab chiqish

Har bir xizmatning kodi mos konteynerga volume orqali ulanmagan (`frontend/src` bundan mustasno — u tez HMR uchun ulangan); backend/bot/worker'da kod o'zgarishi uchun konteynerni qayta build qilish kerak:
```bash
docker compose build backend bot worker && docker compose up -d backend bot worker
```

Yangi Alembic migratsiya yaratish uchun (`shared`dagi modellarni o'zgartirgandan so'ng):
```bash
docker compose run --rm backend alembic revision --autogenerate -m "tavsif"
docker compose run --rm backend alembic upgrade head
```

## Muhim eslatmalar

- HEMIS API tokeni va admin parolini hech qachon commit qilmang — ular faqat `.env` faylida (git tomonidan e'tiborsiz qoldiriladi).
- Xodim rasmlari `image_full` HEMIS serverida topilmasa (404), sinxronizatsiya baribir muvaffaqiyatli yakunlanadi — rasmsiz.
- Bu konfiguratsiya faqat lokal/ichki tarmoq uchun (SSL, `rtm.afu.uz` domenini production serverga joylash alohida vazifa).
