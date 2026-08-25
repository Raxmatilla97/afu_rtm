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
4. Tasdiqlangan xodim murojaat yaratadi (bot yoki veb). Muammoni yozib ham, **ovozli xabar**, **video**, **aylana video**, rasm yoki hujjat yuborib ham tushuntirishi mumkin.
5. Murojaat **RTM guruhiga** kartochka bo'lib tushadi. Xodim «✋ Men bajaraman» tugmasini bosib o'zi olishi mumkin, yoki admin veb-paneldan tayinlaydi. Bir murojaatni bir necha xodim birgalikda olishi mumkin.
6. Tayinlangan xodimga Telegramda to'liq brifing keladi: murojaatchi (bo'lim, telefon, Telegram), muddat, tavsif — va murojaatchi yuborgan **barcha materiallar o'z ko'rinishida** qayta yuboriladi (ovozli xabar ovozli xabar bo'lib, aylana video aylana bo'lib qoladi).
7. RTM xodimi botda ishni boshlaydi, murojaatchi bilan yozishadi (matn yoki media), ichki muhokama qiladi, bajarilgach hisobot bilan yopadi — hisobotni ham ovozli xabar yoki video ko'rinishida qoldirishi mumkin.
8. Murojaatchiga bildirishnoma va hisobot materiallari boradi, u 1–5 baho qo'yadi.
9. **Top xodimlar** va **Statistika** sahifalarida natijalar ko'rinadi. Botdagi statistika bo'limlarga bo'lingan (Umumiy / Men / Ishim / Top) va diagrammalar bilan ko'rsatiladi.

### Rollar va bloklash

**Xodimlar** sahifasidagi «Amallar» ustunida to'rtta belgi bor:

| Belgi | Nima beradi |
|---|---|
| **RTM xodimi** | Murojaatlarni bajaradi, guruhda «Men bajaraman» tugmasi ishlaydi |
| **Boshliq** | Guruhdagi «👤 Tayinlash» tugmasi ishlaydi; veb-saytda bajaruvchini olib tashlay oladi |
| **Admin** | Boshliq huquqlari + **veb-saytdagi to'liq admin panel**: Xodimlar, Bo'limlar, HEMIS sinxronizatsiya. HEMIS orqali kirganda ochiladi, alohida parol kerak emas |
| **Bloklash** | Xodim botga ham, veb-saytga ham kira olmaydi. Botda «🚫 Siz botdan foydalana olmaysiz!» degan xabar chiqadi |

Bloklash HEMIS sinxronizatsiyasidan mustaqil saqlanadi — aks holda keyingi importda o'zi
ochilib ketardi.

**Admin panelga ikkita yo'l bor.** `.env` dagi `ADMIN_EMAIL`/`ADMIN_PASSWORD` hisobi —
hech kim hali hech nima deb belgilanmagan paytdagi zaxira kirish. **Admin** deb belgilangan
xodim esa o'z HEMIS hisobi bilan kirib, xuddi shu huquqlarni oladi.

Bu qulaylik uchun emas: ikkala kirish **bitta sessiya cookie**'sini bo'lishadi, ya'ni
HEMIS orqali kirish admin sessiyasini almashtirib yuboradi. Rolni odamning o'ziga
biriktirish tanlash zaruratini yo'q qiladi. Yon panelda qaysi hisob bilan
kirganingiz va rollaringiz doim ko'rinib turadi.

**Murojaatni olgan xodim undan voz kecha olmaydi** — na botda, na vebda. Bu guruh oldida
olingan majburiyat, va bir bosishlik bekor qilish uni taxminga aylantiradi. Faqat Boshliq
yoki Admin veb-saytdagi tayinlash formasidan xodimni olib tashlay oladi.

### RTM guruhi

Bot alohida emas — **xuddi shu bot** guruhga qo'shiladi. RTM xodimi botni guruhga qo'shsa
(yoki guruhda `/rtm_on` yozsa), guruh ro'yxatga olinadi. Faqat RTM xodimi ula oladi: aks
holda istalgan odam botni o'z guruhiga qo'shib, murojaatchilarning ismi va telefoni bilan
birga barcha murojaatlarni olib turgan bo'lardi.

Har bir murojaat guruhda **bitta kartochka** bo'lib chiqadi va butun umri davomida o'sha
kartochka tahrirlanadi — kim olgani, ish holati, yakuniy hisobot, sarflangan vaqt va baho
shu yerda ko'rinadi. Har bir voqea uchun esa kartochkaga qisqa javob-xabar yoziladi, chunki
tahrirlash bildirishnoma bermaydi.

Kartochkadagi tugmalar: «✋ Men bajaraman» / «🤝 Men ham qo'shilaman», «👤 Tayinlash»,
«📎 Materiallar» va «💬 Botda ochish». Oxirgisi shaxsiy chatda o'sha murojaatni ochadi —
yozishmalar, hisobot va yakunlash o'sha yerda, chunki bularning hammasi matn kiritishni
talab qiladi va guruhga tegishli emas.

«👤 Tayinlash» bosilganda kartochkaning o'z tugmalari RTM xodimlari ro'yxatiga almashadi;
F.I.Sh. tanlansa, murojaat o'sha xodimga topshiriladi va unga to'liq brifing yuboriladi.
Tugma hammaga ko'rinadi (kartochka — umumiy xabar, tugmalari har kimga boshqacha bo'la
olmaydi), lekin faqat Boshliq yoki Admin foydalana oladi — boshqasi bossa, faqat o'ziga
ko'rinadigan qalqib chiquvchi xabar chiqadi, chat esa toza qoladi.

Guruhda ko'rsatilgan materiallar **10 daqiqadan so'ng avtomatik o'chiriladi** (bu haqda
o'sha postning izohida kichkina qilib yozilgan). Fayllar yo'qolmaydi — kartochkadagi tugma
ularni qayta chaqiradi, veb-saytda esa doim turadi.

Guruhni o'chirish: `/rtm_off`.

### Yozishmalar

Har bir bildirishnoma o'zi tegishli murojaatga bog'lab qo'yiladi. Shuning uchun botda
xabarga oddiy **«reply»** qilib javob yozish yetarli — javob to'g'ri murojaat ipiga
tushadi va ikkinchi tomonga boradi. Bu ikkala yo'nalishda ham ishlaydi: murojaatchi
RTM xabariga javob bersa mas'ul xodimga, xodim javob bersa murojaatchiga.

Vebda esa o'ng tomondagi chat har 5 soniyada o'zi yangilanadi, butun ekranga
kengaytiriladi (yoki `Esc` bilan yopiladi) va Telegramdagidek ko'rinadi: **murojaatchi
chapda, RTM o'ngda** — kim qarayotganidan qat'i nazar, ya'ni ikki kishi bir xil manzarani
ko'radi. Ovozli xabar, video va rasm o'sha yerda ochiladi.

### Muddat va kechikish

Muddat qo'yilgan murojaat sahifasida katta **jonli sanoq** turadi: yashil → sutkadan kam
qolganda sariq → muddat o'tsa qizil ogohlantirish.

Har yarim soatda fon vazifasi kechikkanlarni tekshiradi va uch tomonga uch xil xabar
yuboradi — har biriga bir marta:

| Kimga | Nima |
|---|---|
| RTM guruhi | 🔴🚨 qizil signal, kartochka sarlavhasi ham qizilga o'zgaradi |
| Bajaruvchi xodim | shaxsiy chatga eslatma + «Bajarish» va «Javob berish» tugmalari |
| Murojaatchi | 🙏 uzr so'rash: ish unutilmagani va kim ustida ishlayotgani |

RTM xodimining **bosh sahifasida** ham kechikkan va muddati yaqinlashgan topshiriqlar
ro'yxati chiqadi. Muddat o'zgartirilsa, ogohlantirish qaytadan berilishi mumkin bo'ladi.

Bajarilganda murojaatchiga 🎉🟢 yashil, tabriklovchi xabar boradi — sarflangan vaqt va
baholash tugmalari bilan.

### Veb-interfeys

Sayt telefonda ham to‘liq ishlaydi. Yon menyu `lg` dan kichik ekranlarda yuqoridagi ☰ tugmasi orqali ochiladigan panelga aylanadi (sahifa tanlangach o‘zi yopiladi, orqa fon esa aylanmaydi). Jadvallar telefonda kartochkalarga aylanadi — olti ustunli jadval yonga siljib, kerakli ustunni yashirib qo‘yishdan ko‘ra, har bir satr o‘z sarlavhasi va nomlangan qatorlari bilan ko‘rinadi.

Jadval ustunlari **bir marta** e’lon qilinadi va ikkala ko‘rinishga ham o‘sha ta’rifdan chiziladi ([ResponsiveTable](frontend/src/components/ResponsiveTable.tsx)) — aks holda jadvalga qo‘shilgan, kartochkaga qo‘shilmagan ustun aynan telefondan foydalanuvchilarga ko‘rinmay qolardi.

### RTM Inventar

Ombor hisobi: asbob-uskunalar va tez ketadigan rasxodniklar (toner, baraban, kabel).
Kategoriyalar tayyor holda keladi, ularga inventar qo'shiladi.

**Qoldiq hech qachon to'g'ridan-to'g'ri tahrirlanmaydi.** Har bir o'zgarish sababi bilan
yoziladi (kirim / ishlatildi / hisobdan chiqarish / tuzatish), qoldiq esa shu yozuvlarning
yig'indisi. Shuning uchun «martda 12 ta toner olindik, 3 tasi qoldi — qolgani qayerga
ketdi?» degan savolga javob bor. Tahrirlanadigan raqam faqat bugungi holatni biladi.

Narx va chek — **ixtiyoriy**. Ko'p rasxodnik narxi yozilmagan holda keladi, va narx
yozilmaguncha inventarni ro'yxatga olmaslik registrni aynan kerakli joyda foydasiz qiladi.
Rejalashtirilgan xaridlar ham yuritiladi (📝 Rejalashtirilgan / 🚚 Buyurtma qilingan).

**Botda:** RTM xodimi murojaatni yakunlaganda hisobotdan keyin bitta ekran chiqadi —
«Bu ishda biror inventar ishlatildimi?». Ishlatilmagan bo'lsa **bitta tugma** («Yo'q,
yakunlash») va tamom. Ishlatilgan bo'lsa: kategoriya → qism → soni (1/2/3/5 yoki qo'lda).
Har bir tanlovdan keyin ro'yxat ko'rinadi, yana qo'shish yoki yakunlash mumkin. Sarf faqat
yakunlash bosilganda hisobdan yechiladi — yarim yo'lda tashlab ketilgan oqim omborni
buzmaydi.

Kerakli qism yo'q bo'lsa — **«⏸ Inventar kutish»**: muddat tanlanadi (1 kun … 1 oy) va nima
kutilayotgani yoziladi. Murojaat `⏸ Inventar kutilmoqda` holatiga o'tadi, murojaatchiga
sabab va taxminiy muddat bilan xabar boradi, guruhga qisqa xabar tushadi. Kutayotgan
murojaat **kechikkan deb hisoblanmaydi** — kechikish ta'minotga tegishli, uni ushlab turgan
odamga emas. Xodim ro'yxatida esa qolaveradi, aks holda unutiladi.

### RTM Soft

Drayverlar va dasturlar. Fayllar **veb-saytdan** yuklanadi (kategoriyalar bilan), botda esa
`/help` → **«💿 Soft va drayverlar»** tugmasidan olinadi: kategoriya → fayl → chatga
yuboriladi.

Bot faylni hech qachon qayta yuklamaydi: birinchi yuborishda Telegram qaytargan `file_id`
saqlanadi va keyingi barcha so'rovlar bir zumda bajariladi. Yuborilgan fayl **10 daqiqadan
so'ng o'chiriladi**, boshqa ekranga o'tilsa esa darhol — chat fayl menejeriga aylanmasligi
uchun.

### Materiallar qanday saqlanadi

Har bir fayl ikki xil saqlanadi: **diskda** (`STORAGE_ROOT` — veb-interfeys shu nusxani ko'rsatadi) va **Telegram `file_id`** sifatida. Botning har qanday qayta yuborishi `file_id` orqali ketadi — bu tezkor va fayl turi (ovozli xabar, aylana video) o'zgarmaydi. 20 MB dan katta fayllarni Bot API yuklab bera olmaydi: bunday fayl faqat Telegramda qoladi, veb-interfeysda esa "faqat Telegramda mavjud" deb ko'rsatiladi.

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
