# AFU RTM — Production deploy (https://rtm.afu.uz)

Butun stack Docker Compose orqali ishga tushadi. Caddy SSL sertifikatni Let's Encrypt'dan
avtomatik oladi va yangilaydi — certbot yoki qo'lda sertifikat sozlash shart emas.

Faqat Caddy tashqariga port ochadi (80/443). Postgres, Redis, backend va frontend faqat
ichki tarmoqda — ular hech qachon internetdan ko'rinmaydi.

---

## 1. Oldindan tayyorgarlik

**DNS**: `rtm.afu.uz` uchun `A` yozuvi serveringizning public IP'siga qaratilgan bo'lsin.

```bash
dig +short rtm.afu.uz
```

**Firewall**: 80 va 443 portlar ochiq bo'lishi kerak.
80-port **majburiy** — Let's Encrypt sertifikat berishda (ACME HTTP challenge) shu portdan
foydalanadi, garchi keyinchalik butun trafik 443'ga o'tsa ham.

**Docker**: Docker Engine + Compose v2 o'rnatilgan bo'lsin.

```bash
docker compose version
```
`v2.x` chiqishi kerak.

**Chiquvchi ulanish**: backend konteyneri `hemis.alfraganusuniversity.uz` va
`student.alfraganusuniversity.uz` ga HTTPS orqali chiqa olishi kerak.

---

## 2. Kodni serverga olish

```bash
git clone <repo-url> afu_rtm && cd afu_rtm
```

---

## 3. `.env` faylini to'ldirish

```bash
cp .env.example .env
```

Keyin `.env` ni tahrirlab quyidagilarni to'ldiring:

| O'zgaruvchi | Izoh |
|---|---|
| `POSTGRES_PASSWORD` | Kuchli parol. `DATABASE_URL` ichidagi parol ham **aynan shunday** bo'lsin |
| `DATABASE_URL` | `postgresql+asyncpg://<user>:<parol>@postgres:5432/<db>` |
| `JWT_SECRET` | `openssl rand -hex 32` bilan generatsiya qiling |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Birinchi admin hisobi (birinchi ishga tushishda avtomatik yaratiladi) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | @BotFather'dan |
| `API_HEMIS_TOKEN` | HEMIS bulk sync tokeni |
| `EMPLOYEE_CLIENT_ID` / `EMPLOYEE_CLIENT_SECRET` | HEMIS OAuth client (id: `6`) |
| `EMPLOYEE_REDIRECT_URI` | `https://rtm.afu.uz/oauth/callback` — HEMIS'dagi bilan **belgima-belgi** bir xil |
| `PUBLIC_BASE_URL` | `https://rtm.afu.uz` |
| `COOKIE_SECURE` | `true` |
| `BACKEND_CORS_ORIGINS` | `https://rtm.afu.uz` |
| `VITE_API_BASE_URL` | **bo'sh qoldiring** |

`.env` allaqachon `.gitignore` da — hech qachon commit qilinmaydi.

**Caddy email**: `deploy/Caddyfile` ning boshidagi `email admin@rtm.afu.uz` ni o'z
manzilingizga o'zgartiring (Let's Encrypt sertifikat muddati haqida shu manzilga xabar yuboradi).

---

## 4. Birinchi ishga tushirish

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Bir necha daqiqa vaqt oladi (frontend `npm run build` qiladi).

**Sertifikat olinishini kuzating:**

```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```

`certificate obtained successfully` chiqishi kerak. Agar xato bo'lsa — deyarli har doim
sabab: DNS hali tarqalmagan yoki 80-port yopiq.

**Migratsiyalar** avtomatik ishlaydi (`backend/entrypoint.sh` → `alembic upgrade head` +
kategoriya va admin seed). Tekshirish:

```bash
docker compose -f docker-compose.prod.yml logs backend | head -50
```

Qo'lda ishga tushirish kerak bo'lsa:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## 5. Tekshirish (smoke test)

```bash
curl -I https://rtm.afu.uz/health
```
→ `200 OK`

Brauzerda:
- `https://rtm.afu.uz/` → sayt ochiladi
- `https://rtm.afu.uz/login` → login sahifasi (SPA fallback ishlayotganini bildiradi)
- `https://rtm.afu.uz/oauth/login?flow=web` → `hemis.alfraganusuniversity.uz` ga yo'naltiradi

---

## 6. Birinchi HEMIS sync — **login'dan OLDIN**

Admin sifatida kiring (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) → **HEMIS sync** sahifasi →
sync'ni ishga tushiring.

> ⚠️ Buni albatta birinchi qiling. `employees` jadvali bo'sh bo'lsa, har qanday HEMIS
> login'i "xodim topilmadi" (`unmatched`) bilan tugaydi.

---

## 7. Birinchi OAuth login

O'zingiz kirib ko'ring. Nima bo'lishidan qat'i nazar, natija bazaga yoziladi:

```bash
docker compose -f docker-compose.prod.yml logs backend | grep -i oauth
```

Agar xodim topilmasa, to'liq HEMIS javobi `oauth_login_attempts` jadvalida saqlanadi —
admin panelidagi "OAuth urinishlari" sahifasidan yoki to'g'ridan-to'g'ri ko'rish mumkin:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT state, status, match_strategy, userinfo_json FROM oauth_login_attempts ORDER BY created_at DESC LIMIT 5;"
```

Shu ma'lumot bilan xodimni topish qoidasini aniq sozlab, qayta deploy qilamiz.

---

## 8. Telegram bot

Botni oching → `/start` → "🔐 HEMIS orqali kirish" tugmasini bosing.

Agar webview ochilmasa: @BotFather → Bot Settings → Domain → `rtm.afu.uz` qo'shib ko'ring.
(Aslida `web_app` tugmalari uchun bu shart emas — bu Telegram Login Widget uchun — lekin
muammo bo'lsa birinchi shuni tekshiring.)

---

## 9. O'zgarishlardan keyin qayta deploy

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`--build` majburiy — konteynerlarda bind-mount yo'q, kod image ichida.
`caddy_data` volume saqlanib qoladi, shuning uchun yangi sertifikat so'ralmaydi.

---

## 10. Loglar

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs --tail 200 bot
```

Xizmatlar: `caddy backend frontend bot worker postgres redis`

---

## 11. Zaxira nusxa (backup)

**Baza:**
```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > backup-$(date +%F).sql.gz
```

**Fayllar** (murojaatlarga biriktirilgan rasmlar, xodim suratlari) — `afu_uploads` volume:
```bash
docker run --rm -v afu_rtm_afu_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/uploads-$(date +%F).tar.gz -C /data .
```

---

## Tez-tez uchraydigan muammolar

| Belgi | Sabab |
|---|---|
| Caddy sertifikat ololmayapti | DNS tarqalmagan yoki 80-port yopiq |
| OAuth'da `invalid_request` / `redirect_uri_mismatch` | `.env` dagi `EMPLOYEE_REDIRECT_URI` HEMIS'da ro'yxatdan o'tgani bilan aynan bir xil emas (scheme, oxiridagi `/`) |
| Har bir login `unmatched` | HEMIS sync qilinmagan — 6-bosqichga qarang |
| Frontend eski API manzilga uryapti | `VITE_API_BASE_URL` build vaqtida o'qiladi — `--build` bilan qayta yig'ing |
| Bot javob bermayapti | `docker compose -f docker-compose.prod.yml logs bot`; `TELEGRAM_BOT_TOKEN` ni tekshiring |
