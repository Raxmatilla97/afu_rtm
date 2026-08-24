# AFU RTM — Production deploy (https://rtm.afu.uz)

Butun stack Docker Compose orqali ishga tushadi. TLS'ni va tashqi trafikni **BunkerWeb**
boshqaradi — u alohida turadi va bu compose faylga kirmaydi.

Compose ikkita portni localhost'ga chiqaradi: backend `18081`, frontend `18080`.
BunkerWeb shu ikkalasiga proxy qiladi. Postgres va Redis umuman tashqariga chiqmaydi.

> ⚠️ **Eng muhim qadam — 4-bo'lim (BunkerWeb marshrutlari).** Agar `/api/*`, `/oauth/*`,
> `/media/*` va `/health` backend'ga yo'naltirilmasa, hammasi frontend'ga tushadi va
> tashqaridan bu shunday ko'rinadi: HEMIS tugmasi hech qayerga olib bormaydi, admin login
> esa "Email yoki parol noto'g'ri" deydi (aslida nginx `POST` ga `405` qaytaradi).

---

## 1. Oldindan tayyorgarlik

**DNS**: `rtm.afu.uz` uchun `A` yozuvi serveringizning public IP'siga qaratilgan bo'lsin.

```bash
dig +short rtm.afu.uz
```

**Firewall**: tashqariga faqat BunkerWeb'ning 80/443 portlari ochiq bo'lsin.
`18080` va `18081` **internetdan yopiq** bo'lishi shart — ularga to'g'ridan-to'g'ri
kirgan trafik WAF va TLS'ni chetlab o'tadi. `.env` da `BIND_ADDRESS=127.0.0.1` qo'ying
(BunkerWeb ham shu serverda bo'lsa).

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
| `BIND_ADDRESS` | `127.0.0.1` (BunkerWeb shu serverda bo'lsa) |

`.env` allaqachon `.gitignore` da — hech qachon commit qilinmaydi.

---

## 4. BunkerWeb marshrutlari (**majburiy**)

Bitta domen ikkita upstream'ga bo'linadi. BunkerWeb'ning `rtm.afu.uz` sayti uchun:

```
rtm.afu.uz_USE_REVERSE_PROXY=yes

rtm.afu.uz_REVERSE_PROXY_URL_1=/api/
rtm.afu.uz_REVERSE_PROXY_HOST_1=http://127.0.0.1:18081/api/

rtm.afu.uz_REVERSE_PROXY_URL_2=/oauth/
rtm.afu.uz_REVERSE_PROXY_HOST_2=http://127.0.0.1:18081/oauth/

rtm.afu.uz_REVERSE_PROXY_URL_3=/media/
rtm.afu.uz_REVERSE_PROXY_HOST_3=http://127.0.0.1:18081/media/

rtm.afu.uz_REVERSE_PROXY_URL_4=/health
rtm.afu.uz_REVERSE_PROXY_HOST_4=http://127.0.0.1:18081/health

rtm.afu.uz_REVERSE_PROXY_URL_5=/
rtm.afu.uz_REVERSE_PROXY_HOST_5=http://127.0.0.1:18080/
```

`/` eng oxirida — u SPA uchun "qolgan hammasi" qoidasi. nginx eng uzun mos prefiksni
tanlaydi, shuning uchun `/api/` `/` dan ustun turadi.

**CSP**: BunkerWeb standart holatda `frame-ancestors 'self'` qo'yadi. Telegram Web
(`web.telegram.org`) WebApp'ni iframe ichida ochadi, shuning uchun bot login'i u yerda
bloklanadi. Tuzatish:

```
rtm.afu.uz_CONTENT_SECURITY_POLICY=object-src 'none'; form-action 'self'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;
```

Sozlagandan keyin BunkerWeb'ni qayta yuklang va 6-bo'limdagi tekshiruvni bajaring.

---

## 5. Birinchi ishga tushirish

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Bir necha daqiqa vaqt oladi (frontend `npm run build` qiladi).

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

## 6. Tekshirish (smoke test)

**Marshrutlar to'g'ri ekanini shu bitta buyruq ko'rsatadi:**

```bash
for p in /health /api/auth/me "/oauth/login?flow=web" /login; do printf '%-28s' "$p"; curl -s -o /dev/null -w 'status=%{http_code} type=%{content_type}\n' "https://rtm.afu.uz$p"; done
```

Kutilgan natija:

| Yo'l | Kutilgan |
|---|---|
| `/health` | `200` + `application/json` |
| `/api/auth/me` | `401` + `application/json` |
| `/oauth/login?flow=web` | `302` (Location → `hemis.alfraganusuniversity.uz`) |
| `/login` | `200` + `text/html` |

Agar **to'rttasi ham** `200 text/html` qaytarsa — BunkerWeb hammasini frontend'ga
uzatyapti, 4-bo'limga qayting. Bu holatda web login ham, bot login ham ishlamaydi.

---

## 7. Birinchi HEMIS sync — **login'dan OLDIN**

Admin sifatida kiring (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) → **HEMIS sync** sahifasi →
sync'ni ishga tushiring.

> ⚠️ Buni albatta birinchi qiling. `employees` jadvali bo'sh bo'lsa, har qanday HEMIS
> login'i "xodim topilmadi" (`unmatched`) bilan tugaydi.

---

## 8. Birinchi OAuth login

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

## 9. Telegram bot

Botni oching → `/start` → "🔐 HEMIS orqali kirish" tugmasini bosing.

Agar webview ochilmasa: @BotFather → Bot Settings → Domain → `rtm.afu.uz` qo'shib ko'ring.
(Aslida `web_app` tugmalari uchun bu shart emas — bu Telegram Login Widget uchun — lekin
muammo bo'lsa birinchi shuni tekshiring.)

---

## 10. O'zgarishlardan keyin qayta deploy

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`--build` majburiy — konteynerlarda bind-mount yo'q, kod image ichida.
BunkerWeb alohida ishlaydi — bu buyruq unga tegmaydi.

---

## 11. Loglar

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs --tail 200 bot
```

Xizmatlar: `backend frontend bot worker postgres redis` (BunkerWeb — alohida stack)

---

## 12. Zaxira nusxa (backup)

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
| "Email yoki parol noto'g'ri", garchi parol to'g'ri bo'lsa | `/api/*` backend'ga yo'naltirilmagan — SPA nginx `POST` ga `405` qaytaryapti. 4-bo'lim |
| "HEMIS orqali kirish" bosilsa login sahifasida qolib ketadi | `/oauth/*` backend'ga yo'naltirilmagan — 4-bo'lim |
| Botda `/start` har safar qaytadan login so'raydi | Xuddi shu sabab: OAuth hech qachon yakunlanmagan, shuning uchun `employees` da telegram bog'lanish yo'q |
| Telegram Web'da WebApp oq ekran | CSP `frame-ancestors` Telegram'ga ruxsat bermayapti — 4-bo'lim |
| OAuth'da `invalid_request` / `redirect_uri_mismatch` | `.env` dagi `EMPLOYEE_REDIRECT_URI` HEMIS'da ro'yxatdan o'tgani bilan aynan bir xil emas (scheme, oxiridagi `/`) |
| Har bir login `unmatched` | HEMIS sync qilinmagan — 6-bosqichga qarang |
| Frontend eski API manzilga uryapti | `VITE_API_BASE_URL` build vaqtida o'qiladi — `--build` bilan qayta yig'ing |
| Bot javob bermayapti | `docker compose -f docker-compose.prod.yml logs bot`; `TELEGRAM_BOT_TOKEN` ni tekshiring |
