# AFU RTM — Production deploy (https://rtm.afu.uz)

Butun stack Docker Compose orqali ishga tushadi. TLS'ni va tashqi trafikni **BunkerWeb**
boshqaradi — u alohida turadi va bu compose faylga kirmaydi.

Compose **bitta** portni chiqaradi: frontend `18080`. Shu konteyner saytning yagona
kirish nuqtasi — uning nginx'i SPA'ni beradi va `/api`, `/oauth`, `/media`, `/health` ni
ichki tarmoq orqali backend'ga uzatadi ([`deploy/frontend-nginx.conf`](deploy/frontend-nginx.conf)).
Shuning uchun BunkerWeb'ga faqat **bitta upstream** ko'rsatilsa yetarli — yo'llar bo'yicha
qoida yozish shart emas. Backend, worker, Postgres va Redis tashqariga umuman chiqmaydi.

---

## 1. Oldindan tayyorgarlik

**DNS**: `rtm.afu.uz` uchun `A` yozuvi serveringizning public IP'siga qaratilgan bo'lsin.

```bash
dig +short rtm.afu.uz
```

**Firewall**: tashqariga faqat BunkerWeb'ning 80/443 portlari ochiq bo'lsin.
`18080` **internetdan yopiq** bo'lishi shart — unga to'g'ridan-to'g'ri kirgan trafik WAF
va TLS'ni chetlab o'tadi.

`BIND_ADDRESS` ni qanday qo'yish kerak:
- BunkerWeb to'g'ridan-to'g'ri serverda ishlasa → `127.0.0.1` (eng xavfsiz)
- BunkerWeb o'z konteynerida ishlasa → `0.0.0.0`, va `18080` ni firewall'da tashqaridan
  yoping. Konteyner host'ning `127.0.0.1` iga kira olmaydi, shuning uchun loopback'ga
  bog'lash saytni ishlamay qo'yadi. Bu holda BunkerWeb upstream'i `127.0.0.1` emas,
  host'ning docker bridge IP'si bo'ladi (odatda `172.17.0.1`).

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
| `BIND_ADDRESS` | 1-bo'limga qarang (`127.0.0.1` yoki `0.0.0.0`) |

`.env` allaqachon `.gitignore` da — hech qachon commit qilinmaydi.

---

## 4. BunkerWeb sozlamasi

`rtm.afu.uz` sayti uchun **bitta** upstream:

```
rtm.afu.uz_USE_REVERSE_PROXY=yes
rtm.afu.uz_REVERSE_PROXY_URL_1=/
rtm.afu.uz_REVERSE_PROXY_HOST_1=http://127.0.0.1:18080/
```

BunkerWeb konteynerda bo'lsa `127.0.0.1` o'rniga host'ning bridge IP'sini yozing
(`172.17.0.1` yoki `ip -4 addr show docker0` ko'rsatgan manzil).

Yo'llar bo'yicha ajratishni frontend konteynerining o'zi qiladi, shuning uchun bu yerda
`/api/`, `/oauth/` uchun alohida qoida **kerak emas**. (Ilgari bu ajratish faqat BunkerWeb
tomonda edi — bitta qoida tushib qolgani uchun hamma so'rov SPA'ga tushib, web login ham,
bot login ham ishlamay qolgandi.)

**Muhim:** BunkerWeb'da `/` upstream'i yo'q bo'lsa yoki `USE_REVERSE_PROXY` o'chiq bo'lsa,
u o'z statik papkasini beradi va hech narsa ishlamaydi. 6-bo'limdagi tekshiruv shuni
darrov ko'rsatadi.

**CSP**: BunkerWeb standart holatda `frame-ancestors 'self'` qo'yadi. Bot login'i endi
Mini App (webview) emas, oddiy brauzer havolasi orqali ochiladi, shuning uchun bu bot uchun
majburiy emas. Lekin Telegram Web (`web.telegram.org`) saytni iframe ichida ochishi mumkin,
shuning uchun quyidagi qiymat baribir tavsiya etiladi:

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

Agar **to'rttasi ham** `200 text/html` (bir xil o'lchamda) qaytarsa — so'rovlar
backend'ga umuman yetib bormayapti. Ketma-ket tekshiring:

```bash
# 1) Frontend konteynerining o'zi to'g'ri javob beryaptimi? (BunkerWeb'ni chetlab o'tib)
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://127.0.0.1:18080/health
```

`200 application/json` bo'lsa — muammo BunkerWeb'da (4-bo'lim).
`200 text/html` bo'lsa — frontend image eski, `--build` bilan qayta yig'ing:

```bash
docker compose -f docker-compose.prod.yml up -d --build frontend
docker compose -f docker-compose.prod.yml exec frontend nginx -t
```

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

Har bir urinish — muvaffaqiyatli yoki yo'q — `oauth_login_attempts` jadvaliga to'liq
HEMIS javobi bilan yoziladi. (Admin API'da `/api/oauth-attempts` bor, lekin unga mos
sahifa hali frontend'da yo'q — hozircha to'g'ridan-to'g'ri bazadan o'qing.)

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -c "SELECT flow, status, match_strategy, matched_employee_id, error_detail, created_at FROM oauth_login_attempts ORDER BY created_at DESC LIMIT 10;"
```

`status` ustuni nima bo'lganini aytadi: `matched` (muvaffaqiyatli), `unmatched` (HEMIS
tanidi, lekin xodim topilmadi — sync qilinmagan bo'lishi mumkin), `state_expired`,
`token_error`, `userinfo_error`, `wrong_type`, `denied`, `pending` (HEMIS'ga borgan, lekin
qaytmagan). `unmatched` bo'lsa to'liq javobni ko'ring:

```bash
docker compose -f docker-compose.prod.yml exec postgres   psql -U $POSTGRES_USER -d $POSTGRES_DB   -c "SELECT userinfo_json FROM oauth_login_attempts WHERE status='unmatched' ORDER BY created_at DESC LIMIT 1;"
```

Shu ma'lumot bilan xodimni topish qoidasini aniq sozlab, qayta deploy qilamiz.

---

## 9. Telegram bot

Botni oching → `/start` → "🔐 HEMIS orqali kirish" tugmasini bosing.

Havola **brauzerda** ochiladi (Mini App/webview emas — bu ataylab shunday, pastdagi
"One-ID" izohiga qarang) → `rtm.afu.uz/oauth/login` oraliq sahifasi → "HEMIS'ga o'tish" →
HEMIS → callback → "Botga qaytish".

**One-ID haqida.** HEMIS'da sessiya bo'lmasa, u foydalanuvchini One-ID ga yuboradi va
qaytishda `/oauth/authorize` ni davom ettirmasdan HEMIS profiliga tashlab qo'yadi — bu
HEMIS tomonidagi xatti-harakat, biz tuzata olmaymiz. Yechim: o'sha oraliq sahifaga qaytib
tugmani **ikkinchi marta** bosish; endi HEMIS sessiyani taniydi va to'g'ridan-to'g'ri
callback'ga qaytaradi. Aynan shu sabab tugma Mini App emas: Mini App yopilganda cookie'lar
o'chib ketadi, shuning uchun ikkinchi urinish ham noldan boshlanardi va foydalanuvchi
cheksiz aylanib qolardi.

Foydalanuvchi qaytib kelishi uchun `TELEGRAM_BOT_USERNAME` to'g'ri to'ldirilgan bo'lishi
kerak — "Botga qaytish" tugmasi shundan `https://t.me/<username>` havolasini yasaydi.

---

## 10. O'zgarishlardan keyin qayta deploy

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`--build` majburiy — konteynerlarda bind-mount yo'q, kod image ichida.
BunkerWeb alohida ishlaydi — bu buyruq unga tegmaydi.

Migratsiyalar `backend` konteyneri ishga tushganda avtomatik bajariladi. Media
biriktirmalari uchun `b2c9d41f7a08` migratsiyasi kerak — tekshirish:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic current
```

---

## 10a. Materiallar (rasm, video, ovozli xabar)

Fayllar `afu_uploads` volume'ida (`/app/storage/requests/<id>/`) saqlanadi va uni
`backend`, `bot`, `worker` — uchalasi ham mount qiladi. Bot yozgan faylni veb-interfeys
shu volume orqali ko'rsatadi, shuning uchun bu uchtasi **bir xil volume'da** turishi shart.

Cheklovlar:

| Nima | Chegara | Qayerda belgilangan |
|---|---|---|
| Telegramdan yuklab olish | 20 MB | Bot API cheklovi (`MAX_DOWNLOAD_BYTES`) |
| Vebdan yuklash | 25 MB | `MAX_UPLOAD_BYTES` + nginx `client_max_body_size` |

20 MB dan katta fayl diskka tushmaydi, lekin Telegram `file_id` saqlanadi — bot uni
qayta yubora oladi, veb esa "faqat Telegramda mavjud" deb ko'rsatadi. Nginx chegarasini
o'zgartirsangiz, `deploy/frontend-nginx.conf` va `MAX_UPLOAD_BYTES` ni birga o'zgartiring.

Zaxira nusxa olishda `afu_uploads` ni ham qamrab oling — 12-bo'limga qarang.

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
| "Serverga ulanib bo'lmadi (405)" | `POST /api/...` SPA nginx'ining statik `index.html`iga tushyapti — backend'ga proxy qilinmayapti. 6-bo'lim |
| "HEMIS orqali kirish" bosilsa login sahifasida qolib ketadi | `/oauth/*` backend'ga proxy qilinmayapti (`index.html` qaytyapti) — 6-bo'lim |
| Botda `/start` har safar qaytadan login so'raydi | Xuddi shu sabab: OAuth hech qachon yakunlanmagan, shuning uchun `employees` da telegram bog'lanish yo'q |
| Telegram Web'da sayt oq ekran | CSP `frame-ancestors` Telegram'ga ruxsat bermayapti — 4-bo'lim |
| One-ID dan keyin HEMIS profilida qolib ketadi | HEMIS `authorize` so'rovini davom ettirmaydi. Oraliq sahifaga qaytib tugmani qayta bosing — 9-bo'lim |
| "Botga qaytish" tugmasi ko'rinmaydi | `.env` da `TELEGRAM_BOT_USERNAME` bo'sh |
| OAuth'da `invalid_request` / `redirect_uri_mismatch` | `.env` dagi `EMPLOYEE_REDIRECT_URI` HEMIS'da ro'yxatdan o'tgani bilan aynan bir xil emas (scheme, oxiridagi `/`) |
| Har bir login `unmatched` | HEMIS sync qilinmagan — 6-bosqichga qarang |
| Frontend eski API manzilga uryapti | `VITE_API_BASE_URL` build vaqtida o'qiladi — `--build` bilan qayta yig'ing |
| Bot javob bermayapti | `docker compose -f docker-compose.prod.yml logs bot`; `TELEGRAM_BOT_TOKEN` ni tekshiring |
