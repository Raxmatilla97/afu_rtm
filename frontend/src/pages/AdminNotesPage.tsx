import type { ReactNode } from "react";
import { PageHeader } from "@/components/PageHeader";

/**
 * The written-down half of the system.
 *
 * Two things pushed this page into existence. The group commands that connect and
 * disconnect the RTM chat were taken out of Telegram's command menu — a menu every member
 * of a shared group can open should not offer a switch that silences the request feed — so
 * they had to be written down somewhere their owners would find them. And the flow itself,
 * bot to group to staffer to reporter, was only ever explained in person, which is exactly
 * the kind of knowledge that leaves with whoever explained it.
 *
 * The diagrams are inline SVG rather than images: they are edited in the same place as the
 * text they explain, they stay sharp at any width, and there is no asset to lose.
 */
export function AdminNotesPage() {
  return (
    <div>
      <PageHeader
        title="Admin uchun eslatmalar"
        subtitle="Tizim qanday ishlaydi, guruh qanday boshqariladi va nimalarga e'tibor berish kerak"
      />

      <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <b>Bu sahifa faqat Admin uchun ko'rinadi.</b> Bu yerdagi buyruqlar va tartiblar
        RTM guruhini boshqarish uchun kerak — ularni guruhdagi barcha xodimlarga tarqatish
        shart emas.
      </div>

      <Section
        id="guruh"
        title="1. RTM guruhi va yashirin buyruqlar"
        lead="Botni guruhga ulash va uzish tartibi. Bu buyruqlar guruh menyusida atayin ko'rsatilmaydi."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Card tone="brand" title="🔛 /rtm_on — guruhni ulash">
            <p>
              Guruhga murojaat kartochkalari tushishini yoqadi. Buyruqni <b>guruh ichida</b>{" "}
              yozish kerak.
            </p>
            <p className="mt-2">
              Faqat <b>Boshliq</b> yoki <b>Admin</b> ishlata oladi. Oddiy RTM xodimi yozsa
              ham, guruhdagi boshqa a'zo yozsa ham — bot ulanmaydi va «Ulanmadi» deb javob
              beradi.
            </p>
          </Card>
          <Card tone="red" title="🔕 /rtm_off — guruhni uzish">
            <p>
              Guruhga yangi murojaatlar yuborilishini to'xtatadi. Eski kartochkalar joyida
              qoladi, lekin yangilanmaydi.
            </p>
            <p className="mt-2">
              Bu ham faqat <b>Boshliq</b> va <b>Admin</b> uchun — bitta buyruq bilan butun
              jamoaning murojaat oqimi to'xtaydi.
            </p>
            <p className="mt-2">
              Yozuv o'chirilmaydi — qayta <code className="rounded bg-slate-100 px-1">/rtm_on</code>{" "}
              yozilsa, guruh o'sha holatida tiklanadi.
            </p>
          </Card>
        </div>

        <Callout tone="amber" title="Nega bu buyruqlar guruh menyusida ko'rinmaydi?">
          <p>
            Telegramda «/» tugmasi bosilganda chiqadigan buyruqlar ro'yxatini{" "}
            <b>guruhdagi har bir a'zo</b> ko'radi. U yerda «murojaatlarni o'chirish» degan
            buyruq turishi — kimdir qiziqib bosishi uchun taklif. Shuning uchun:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>
              guruhdagi «/» menyusi <b>butunlay bo'sh</b> — na oddiy a'zo, na guruh
              administratori hech qanday buyruq ko'rmaydi;
            </li>
            <li>
              bot guruhda administrator bo'lsa, yozilgan buyruqni chatdan <b>o'chirib
              tashlaydi</b> — tarixda ham ko'rinib qolmaydi;
            </li>
            <li>bot guruhga yozadigan xabarlarda bu buyruqlar endi eslatilmaydi;</li>
            <li>
              buyruqni <b>Boshliq yoki Admin</b> bo'lmagan odam yozsa, hech narsa
              o'zgarmaydi.
            </li>
          </ul>
          <p className="mt-2">
            Telegram «faqat Boshliq va Adminga ko'rsat» degan sozlamani bilmaydi — uning eng
            tor guruh doirasi «shu chat administratorlari», bu esa RTM boshlig'i degani emas.
            Shuning uchun menyu butunlay bo'shatildi, buyruqlar esa aynan shu sahifada yozib
            qo'yildi: menyuda ko'rinmasa ham, <b>yozilsa ishlayveradi</b>.
          </p>
        </Callout>

        <h3 className="mb-2 mt-6 text-sm font-semibold text-slate-800">
          Yangi guruhni ulash — qadamlar
        </h3>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700">
          <li>
            Guruhni ulaydigan odam avval botda shaxsan ro'yxatdan o'tgan bo'lishi kerak
            (<code className="rounded bg-slate-100 px-1">/start</code> → HEMIS orqali tasdiq →
            telefon raqamni ulashish).
          </li>
          <li>
            Admin panelidagi «Xodimlar» sahifasida o'sha odamga <b>Boshliq</b> yoki{" "}
            <b>Admin</b> belgisi qo'yilgan bo'lsin — faqat shu ikki rol guruhni ula oladi.
          </li>
          <li>
            O'sha odam botni guruhga qo'shsin. Bot avtomatik ulanadi va guruhga «ulandi»
            xabarini yozadi.
          </li>
          <li>
            Agar botni boshqa odam qo'shgan bo'lsa, guruh <b>ulanmaydi</b> — bot chatda qoladi,
            lekin unga hech narsa yubormaydi. Keyin Boshliq yoki Admin guruhda{" "}
            <code className="rounded bg-slate-100 px-1">/rtm_on</code> yozsa, ulanadi.
          </li>
          <li>
            Botni guruhda <b>administrator</b> qilib qo'ying — shunda u buyruqlarni o'chira
            oladi va kartochkalarni bemalol tahrirlaydi.
          </li>
        </ol>

        <Callout tone="slate" title="Xavfsizlik">
          Bu tekshiruvlar bejiz emas: guruhga tushadigan kartochkada murojaatchining ismi,
          bo'limi va telefon raqami bo'ladi. Shuning uchun botni istalgan odam istalgan chatga
          qo'shib, universitet bo'yicha barcha murojaatlarni o'qiy olmasligi kerak.
        </Callout>

        <h3 className="mb-2 mt-6 text-sm font-semibold text-slate-800">
          📢 Guruhdagi bot xabarlarini tozalash
        </h3>
        <p className="mb-3 text-sm text-slate-600">
          Chap menyudagi <b>«Guruhdagi xabarlar»</b> sahifasida bot guruhlarga yuborgan
          xabarlar ro'yxati turadi va ularni shu yerdan o'chirish mumkin — xato yuborilgan
          murojaat kartochkasi, bitta ish ostida yig'ilib qolgan izohlar, allaqachon hal
          bo'lgan ish bo'yicha muddat ogohlantirishi va hokazo.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card tone="brand" title="✅ Nima o'chiriladi">
            <ul className="list-disc space-y-1 pl-5">
              <li>
                <b>🎫 Murojaat kartochkasi</b> — o'chirilsa, murojaat guruhda boshqa
                ko'rinmaydi va holati o'zgarganda qayta chiqmaydi. Murojaatning o'zi saytda
                saqlanadi. Kartochka ostidagi izohlar ham birga o'chadi.
              </li>
              <li>
                <b>💬 Izohlar</b> («Falonchi o'z zimmasiga oldi»), <b>🔴 muddat
                ogohlantirishlari</b>, <b>👋 ulanish xabari</b>, <b>📎 qayta yuborilgan
                fayllar</b>.
              </li>
              <li>
                Murojaat butunlay o'chirilganda uning kartochkasi va izohlari guruhdan
                avtomatik olib tashlanadi.
              </li>
            </ul>
          </Card>
          <Card tone="red" title="⚠️ Ikki shart">
            <p>
              <b>1. Bot guruhda administrator bo'lishi kerak</b> va unda «Xabarlarni
              o'chirish» huquqi bo'lishi shart. Aks holda Telegram rad etadi — sabab
              sahifada yoziladi.
            </p>
            <p className="mt-2">
              <b>2. Ro'yxatda faqat bot yozib qolgan xabarlar bo'ladi.</b> Telegram botga
              guruh tarixini o'qishga ruxsat bermaydi, shuning uchun xabarlarni yozib borish
              qo'shilgunga qadar (2026-yil sentabr) yuborilgan <i>izohlar</i> ro'yxatga
              tushmaydi. Kartochkalar esa boshidan beri yozib kelingan — ular hammasi
              ko'rinadi.
            </p>
          </Card>
        </div>

        <Callout tone="amber" title="Eski xabarni qanday o'chirish mumkin">
          <p>
            «Guruhdagi xabarlar» sahifasining pastida <b>«🔗 Ro'yxatda yo'q xabarni havola
            orqali o'chirish»</b> bo'limi bor. Tartibi:
          </p>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>Telegramda kerakli bot xabarini bosib turing;</li>
            <li>
              <b>«Havolani nusxalash»</b> (Copy Message Link) ni tanlang;
            </li>
            <li>havolani sahifadagi maydonga qo'ying va «🗑 O'chirish» ni bosing.</li>
          </ol>
          <p className="mt-2">
            Havola <code className="rounded bg-slate-100 px-1">t.me/c/…/456</code> ko'rinishida
            bo'lsa, guruh ham o'zi aniqlanadi. Faqat raqam yozsangiz — avval guruhni
            ro'yxatdan tanlang.
          </p>
        </Callout>
      </Section>

      <Section
        id="kirish"
        title="2. Tizimga kirish: ikki yo'l"
        lead="Nega tezkor kirish qo'shildi, u qanday ishlaydi va parol unutilganda nima bo'ladi."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Card tone="brand" title="⚡ Tezkor kirish">
            <p>
              Xodim <b>ID raqami</b> va shu tizim uchun <b>parol</b>. Botda ham, saytda ham
              bir xil ishlaydi va bir xil parolni so'raydi.
            </p>
            <p className="mt-2">
              Birinchi marta: ID raqam yoziladi → ekranda <b>kimning hisobi ochilayotgani
              ko'rsatiladi</b> → parol o'ylab topiladi → elektron pochta so'raladi.
              Keyingi safar faqat ID va parol.
            </p>
          </Card>
          <Card tone="slate" title="🔐 HEMIS orqali kirish">
            <p>
              Eski yo'l. HEMIS endi login-parol o'rniga <b>One-ID</b> orqali kirishni
              so'raydi, ko'pchilikning profili unga bog'lanmagan yoki paroli esida yo'q —
              shuning uchun bu yo'l ikkinchi o'ringa tushdi.
            </p>
            <p className="mt-2">
              Ishlaganda foydasi bor: HEMIS shaxsni o'zi tasdiqlaydi. Shuning uchun u
              olib tashlanmadi.
            </p>
          </Card>
        </div>

        <Callout tone="amber" title="Xavfsizlik: ID raqam sir emas">
          <p>
            Xodim ID raqami guvohnomada yozilgan va ro'yxatlarda uchraydi. Ya'ni{" "}
            <b>hisobni birinchi bo'lib parol o'rnatgan odam egallaydi</b>. Buni kamaytirish
            uchun:
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>
              xodimlarga <b>imkon qadar tezroq</b> o'z hisobiga kirib parol o'rnatishni
              ayting — parol qo'yilgach, hisobni boshqa hech kim egallay olmaydi;
            </li>
            <li>
              HEMIS orqali kirgan Telegram hisobiga bog'langan yozuvni tezkor kirish
              <b> tortib ololmaydi</b>;
            </li>
            <li>
              «Xodimlar» sahifasidagi batafsil oynada <b>parol qachon o'rnatilgani</b> va{" "}
              <b>qaysi pochta biriktirilgani</b> ko'rinadi — shubhali holatni shu yerdan
              topasiz;
            </li>
            <li>parol 5 marta xato kiritilsa, hisob 15 daqiqaga bloklanadi.</li>
          </ul>
        </Callout>

        <Callout tone="red" title="Parolni tiklash uchun pochta sozlanishi shart">
          <p>
            Parol unutilganda tiklash havolasi elektron pochtaga yuboriladi. Buning uchun{" "}
            <code className="rounded bg-slate-100 px-1">.env</code> faylida{" "}
            <code className="rounded bg-slate-100 px-1">SMTP_HOST</code>,{" "}
            <code className="rounded bg-slate-100 px-1">SMTP_PORT</code>,{" "}
            <code className="rounded bg-slate-100 px-1">SMTP_USER</code>,{" "}
            <code className="rounded bg-slate-100 px-1">SMTP_PASSWORD</code> to'ldirilgan
            bo'lishi kerak.
          </p>
          <p className="mt-2">
            Sozlanmagan bo'lsa, xat <b>yuborilmaydi</b>: foydalanuvchiga «RTM bilan
            bog'laning» deb yoziladi va worker logida xato qoladi. Bunday hollarda parolni
            faqat RTM qo'lda yangilay oladi.
          </p>
        </Callout>

        <h3 className="mb-2 mt-6 text-sm font-semibold text-slate-800">
          Parolni unutgan xodimga nima deyish kerak
        </h3>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700">
          <li>
            Botda <code className="rounded bg-slate-100 px-1">/chiqish</code> yozsin —
            hisobdan chiqadi va kirish ekrani qaytadi.
          </li>
          <li>«⚡ Tezkor kirish» → ID raqamini yuborsin.</li>
          <li>
            Parolni xato kiritganda <b>«🔑 Parolni tiklash»</b> tugmasi chiqadi — o'sha
            tugmani bossin. Havola pochtaga ketadi va chatdagi ko'rsatma <b>o'chmay
            turadi</b>.
          </li>
          <li>Pochtadagi havola rtm.afu.uz saytini ochadi, u yerda yangi parol qo'yiladi.</li>
          <li>
            Botga qaytib yana «⚡ Tezkor kirish» — ID va yangi parol. Muvaffaqiyatli
            kirgach, tiklash haqidagi eski xabarlar avtomatik o'chadi.
          </li>
        </ol>

        <Callout tone="slate" title="Boshqa odam bo'lib ko'rinish muammosi">
          Ilgari HEMIS orqali kirgan ba'zi xodimlar tizimda <b>boshqa odamning ismi va
          bo'limi</b> bilan chiqib qolgan edi. Sababi: HEMIS'ning OAuth identifikatori
          bilan xodimlar ro'yxatidagi ichki ID raqamlari boshqa-boshqa raqamlar bo'lsa ham,
          kod ularni bir-biriga taqqoslab ko'rar edi (va ism bo'yicha ham moslashtirardi).
          Bu ikkala taxmin ham olib tashlandi — endi mos kelmasa, tizim{" "}
          <b>kiritmaydi</b> va tezkor kirishdan foydalanish taklif etiladi. Noto'g'ri
          bog'langan xodim <code className="rounded bg-slate-100 px-1">/chiqish</code>{" "}
          yozib, o'z ID raqami bilan qayta kirsa, bog'lanish o'z-o'zidan to'g'rilanadi.
        </Callout>
      </Section>

      <Section
        id="bot"
        title="3. Bot qanday ishlaydi"
        lead="Murojaat yo'li: murojaatchidan RTM xodimigacha va yana murojaatchiga qaytib."
      >
        <DiagramFrame caption="1-chizma. Murojaatning tizim bo'ylab harakati">
          <BotFlowDiagram />
        </DiagramFrame>

        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-slate-700">
          <li>
            <b>Murojaatchi</b> botga kiradi, HEMIS orqali o'zini tasdiqlaydi va muammoni
            yozadi: kategoriya, tavsif, kerak bo'lsa rasm, video yoki ovozli xabar.
          </li>
          <li>
            <b>Bot</b> murojaatni qabul qiladi va darhol tasdiq beradi. Xodim veb-saytdagi
            «Yangi murojaat» sahifasidan ham yubora oladi — natija bir xil.
          </li>
          <li>
            <b>Server</b> murojaatni bazaga yozadi va unga raqam beradi
            (<code className="rounded bg-slate-100 px-1">RTM-000123</code>). Shu raqam
            hamma joyda — botda ham, saytda ham, guruhda ham — bir xil ishlatiladi.
          </li>
          <li>
            <b>Navbat va worker</b> — barcha Telegram xabarlari shu yerdan yuboriladi. Sayt
            yoki bot xabar yuborishni kutib turmaydi, shuning uchun interfeys sekinlashmaydi.
          </li>
          <li>
            <b>RTM guruhiga kartochka</b> tushadi. Har bir murojaat uchun <b>bitta</b>{" "}
            kartochka bo'ladi va holat o'zgargani sayin o'sha xabar tahrirlanadi — guruh
            har bir o'zgarish uchun yangi xabar bilan to'lib ketmaydi.
          </li>
          <li>
            <b>RTM xodimi</b> kartochkadagi «✋ Men bajaraman» tugmasini bosadi. Bir murojaatni
            bir necha xodim birgalikda olishi mumkin. Shundan keyin unga shaxsiy chatda to'liq
            ma'lumot va barcha fayllar yuboriladi.
          </li>
          <li>
            <b>Ish bajariladi</b>: xodim murojaatchi bilan yozishadi, ichki izoh qoldiradi,
            sarflangan inventarni belgilaydi va hisobot yozib murojaatni yakunlaydi.
          </li>
          <li>
            <b>Murojaatchiga</b> natija yuboriladi va undan <b>⭐ baho</b> so'raladi. Baho «Top
            xodimlar» reytingiga tushadi.
          </li>
        </ol>

        <Callout tone="brand" title="Veb-sayt bu jarayonning ustida turadi">
          Boshliq va Admin saytda murojaatni tayinlaydi, muddat qo'yadi, noto'g'ri murojaatni
          qaytaradi, yozishmalarni o'qiydi va hisobotlarni ko'radi. Saytdagi har bir amal
          darhol Telegramga ham chiqadi: guruhdagi kartochka yangilanadi, tegishli odamga
          xabar boradi.
        </Callout>
      </Section>

      <Section
        id="holatlar"
        title="4. Murojaatlarni ishlash tartibi (holatlar)"
        lead="Murojaat qaysi holatlardan o'tadi, holatni kim o'zgartira oladi."
      >
        <DiagramFrame caption="2-chizma. Murojaat holatlarining o'zgarishi">
          <RequestLifecycleDiagram />
        </DiagramFrame>

        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Holat</th>
                <th className="px-4 py-3">Ma'nosi</th>
                <th className="px-4 py-3">Kim o'zgartiradi</th>
              </tr>
            </thead>
            <tbody className="text-slate-700">
              {STATUS_ROWS.map((row) => (
                <tr key={row.status} className="border-b border-slate-100 last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-medium">{row.status}</td>
                  <td className="px-4 py-3">{row.meaning}</td>
                  <td className="px-4 py-3 text-slate-500">{row.who}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Callout tone="red" title="«Qaytarib yuborilgan» — alohida holat">
          <p>
            Noto'g'ri yuborilgan murojaatni <b>Boshliq yoki Admin</b> murojaat sahifasidagi
            qizil «🚫 Qaytarib yuborish» tugmasi orqali qaytaradi. Modal oynada sabab yoziladi
            (4 ta tayyor javob bor) va aynan shu matn murojaatchiga Telegram orqali boradi.
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>Qaytarilgan murojaat «Murojaatlar» ro'yxatida ko'rinmaydi;</li>
            <li>
              uni ko'rish uchun holat filtridan <b>«🚫 Qaytarib yuborilgan»</b> ni tanlang;
            </li>
            <li>murojaatni olgan xodimga ham xabar boradi va u ish ro'yxatidan chiqadi;</li>
            <li>guruhdagi kartochka «QAYTARIB YUBORILDI» holatiga o'tadi.</li>
          </ul>
          <p className="mt-2">
            <b>Bekor qilingan</b> bundan farq qiladi: u — RTM qabul qilgan, ammo keyin
            to'xtatilgan ish. Qaytarilgan murojaat esa umuman navbatga kirmagan.
          </p>
        </Callout>
      </Section>

      <Section
        id="rollar"
        title="5. Rollar va huquqlar"
        lead="Kim nima qila oladi. Rollar «Xodimlar» sahifasidan belgilanadi."
      >
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Rol</th>
                <th className="px-4 py-3">Nima qila oladi</th>
              </tr>
            </thead>
            <tbody className="text-slate-700">
              {ROLE_ROWS.map((row) => (
                <tr key={row.role} className="border-b border-slate-100 last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-medium">{row.role}</td>
                  <td className="px-4 py-3">{row.can}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Callout tone="slate" title="Ko'rish chegarasi">
          RTM xodimi faqat <b>o'ziga topshirilgan yoki o'zi olgan</b> murojaatlarni hamda
          o'zi yozgan murojaatlarni ko'radi. Boshqasini havola orqali ochmoqchi bo'lsa,
          «Bu murojaat sizga biriktirilmagan» degan xabar chiqadi. Boshliq va Admin esa
          barcha murojaatlarni ko'radi — chunki ishni ular taqsimlaydi.
        </Callout>

        <h3 className="mb-2 mt-6 text-sm font-semibold text-slate-800">
          👑 Topshiriq berish — faqat Boshliq roli
        </h3>
        <p className="mb-3 text-sm text-slate-600">
          Oddiy murojaat navbatga «egasiz» tushadi va xodimlar o'zlari oladi.{" "}
          <b>Topshiriq</b> esa — <b>muddat</b> va <b>mas'ul xodimlar</b> belgilangan holda
          yuborilgan murojaat. Uni faqat <b>Boshliq</b> roliga ega xodim yubora oladi.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          <Card tone="red" title="Faqat Admin roli — mumkin emas">
            <p>
              Admin — tizimni boshqarish roli (xodimlar, bo'limlar, sozlamalar). Muddat va
              bajaruvchi belgilash RTM boshlig'ining qarori, shuning uchun bunday xodim
              oddiy murojaat yuboradi. Saytda ham, botda ham buning sababi yozib
              ko'rsatiladi.
            </p>
          </Card>
          <Card tone="brand" title="Boshliq — mumkin">
            <p>
              Guruhdagi kartochka <b>«👑 BOSHLIQ TOPSHIRIG'I»</b> sarlavhasi bilan chiqadi va
              boshqa murojaatlardan ajralib turadi.
            </p>
          </Card>
          <Card tone="brand" title="Admin + Boshliq — mumkin">
            <p>
              Ikkala rol ham bo'lsa — mumkin, lekin kartochkada <b>«🛡 ADMIN TOPSHIRIG'I»</b>{" "}
              deb yoziladi: ikkisidan yuqorisi ko'rsatiladi.
            </p>
          </Card>
        </div>

        <Callout tone="brand" title="Topshiriq qayerdan yuboriladi">
          <p>
            <b>Saytda:</b> «Yangi topshiriq» sahifasi Boshliq uchun kengaytirilgan
            ko'rinishda ochiladi — muddat tugmalari (1 soat, 2 soat, 6 soat, 1 kun, 2 kun,
            1 hafta yoki aniq sana) va xodimlar ro'yxati.
          </p>
          <p className="mt-2">
            <b>Botda:</b> «👑 Yangi topshiriq» → kategoriya → tavsif → fayl → <b>muddat</b>{" "}
            → <b>mas'ul xodimlar</b>. Birinchi tanlangan xodim ⭐ mas'ul bo'ladi, har biriga
            Telegram orqali darhol xabar boradi.
          </p>
          <p className="mt-2">
            Muddat ham, bajaruvchi ham ixtiyoriy — ikkalasi bo'sh qoldirilsa, oddiy
            murojaatdek navbatga tushadi. Muddat o'tib ketsa, kartochka guruhda qizil
            «🔴 MUDDAT O'TDI» holatiga o'tadi va xodimlarga eslatma boradi.
          </p>
        </Callout>

        <Callout tone="slate" title="Kartochkalarda F.I — otasining ismisiz">
          Telegramdagi barcha kartochka va xabarlarda ism <b>familiya + ism</b> ko'rinishida
          yoziladi («Fayziyev Raxmatilla»), otasining sharifi ko'rsatilmaydi. Bu faqat
          ko'rinish qoidasi: bazada va saytdagi xodim profilida to'liq F.I.SH saqlanib
          qoladi. Sabab — bir kartochkada bir necha bajaruvchi bo'lganda to'liq ismlar uch
          qatorga bo'linib ketardi.
        </Callout>
      </Section>

      <Section
        id="kundalik"
        title="6. Kundalik eslatmalar"
        lead="Tez-tez so'raladigan narsalar va ularning javobi."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Card tone="slate" title="🔄 HEMIS sinxronizatsiyasi">
            <p>
              «HEMIS sinxronizatsiya» sahifasidagi tugma xodimlar va bo'limlarni yangilaydi.
              HEMIS'da ishdan bo'shagan xodim avtomatik ravishda kirish huquqidan mahrum
              bo'ladi — qo'lda bloklash shart emas.
            </p>
            <p className="mt-2">
              Suratlar ham shu paytda yuklanadi. Surat yo'q xodimlar har safar qaytadan
              urinib ko'riladi, shuning uchun suratlar chiqmasa — sinxronizatsiyani qayta
              ishga tushiring. Sabab «Xodimlar» sahifasidagi batafsil oynada yozib turadi.
            </p>
          </Card>
          <Card tone="slate" title="🚫 Bloklash va HEMIS holati">
            <p>
              <b>Bloklangan</b> — admin qo'li bilan qo'yilgan taqiq, tizimga umuman kira
              olmaydi. <b>HEMIS: faol emas</b> — bu HEMIS'ning qarori, keyingi
              sinxronizatsiyada o'zi tiklanishi ham mumkin. Ikkisi boshqa-boshqa narsa.
            </p>
          </Card>
          <Card tone="slate" title="📦 RTM Inventar">
            <p>
              Ombor qoldig'i qo'lda tahrirlanmaydi: har bir o'zgarish «± Harakat» oynasi
              orqali sabab bilan yoziladi, qoldiq esa shu yozuvlarning yig'indisi. Shuning
              uchun «12 ta toner olindi, 3 tasi qoldi — qolgani qayerga ketdi?» degan savolga
              javob bor.
            </p>
          </Card>
          <Card tone="slate" title="🗑 Hisobdan chiqarilganlar">
            <p>
              Inventar sahifasida ikkita bo'lim bor: <b>«Ombor qoldig'i»</b> va{" "}
              <b>«Hisobdan chiqarilganlar»</b>. Ikkinchisi — alohida reyestr: qachon, nima,
              qancha, nega, kim chiqargan, qiymati va bog'liq murojaat. Sana oralig'i,
              kategoriya va matn bo'yicha filtrlanadi; yuqoridagi ko'rsatkichlar butun
              tanlangan davr bo'yicha hisoblanadi, sahifa almashtirilganda o'zgarmaydi.
            </p>
            <p className="mt-2">
              Yozuv «± Harakat» → <b>«🗑 Hisobdan chiqarish»</b> sababi bilan qo'shiladi va
              o'chirilmaydi. Xato bo'lsa <b>«✏️ Tuzatish»</b> harakati bilan to'g'rilanadi —
              tarix hech qachon qayta yozilmaydi.
            </p>
          </Card>
          <Card tone="slate" title="⭐ Xizmatni baholash">
            <p>
              Murojaat yakunlangach, <b>murojaatchi</b> 1–5 yulduz qo'yadi va xohlasa izoh
              yozadi. Baho <b>bir marta</b> beriladi, o'zgartirilmaydi va ishni bajargan
              <b> har bir xodimga</b> yoziladi — birgalikda bajarilgan ish ikkalasining
              reytingiga ham kiradi.
            </p>
            <p className="mt-2">
              Baho qo'yilishi bilan bajaruvchilarga Telegram orqali xabar boradi (past baho
              bo'lsa — murojaatchi bilan bog'lanish tavsiyasi bilan), guruhdagi kartochkada
              yulduzlar paydo bo'ladi, «Top xodimlar» sahifasi yangilanadi.
            </p>
            <p className="mt-2">
              Murojaatda <b>biriktirilgan xodim bo'lmasa</b> baholab bo'lmaydi — bahoni
              kimga yozishni tizim bilmaydi. Sahifada buning sababi yozib ko'rsatiladi.
            </p>
          </Card>
          <Card tone="slate" title="💿 RTM Soft">
            <p>
              Bu yerga yuklangan fayllar botdagi «Soft va drayverlar» bo'limida chiqadi.
              Fayl birinchi marta yuborilgach Telegram uni keshlaydi — keyingi so'rovlar bir
              zumda bajariladi. Faylning o'zini almashtirib bo'lmaydi: yangisini yuklang,
              eskisini yashiring.
            </p>
          </Card>
        </div>

        <Callout tone="brand" title="Demo ma'lumotlar">
          Inventar va Soft bo'limlaridagi «Demo:» deb belgilangan yozuvlar tizim ishlashini
          ko'rsatish uchun bir marta qo'shilgan. Ularni o'chirib tashlasangiz, qaytadan
          paydo bo'lmaydi — keyingi yangilanishlarda ham tiklanmaydi.
        </Callout>
      </Section>
    </div>
  );
}

const STATUS_ROWS = [
  {
    status: "🆕 Yangi",
    meaning: "Murojaat tushdi, hali hech kim olmagan. Guruhga kartochka joylanadi.",
    who: "Tizim",
  },
  {
    status: "👤 Tayinlangan",
    meaning: "Bajaruvchi bor. Xodim o'zi olgan yoki Boshliq/Admin tayinlagan.",
    who: "RTM xodimi, Boshliq, Admin",
  },
  {
    status: "⏳ Jarayonda",
    meaning: "Xodim ishni boshladi.",
    who: "Bajaruvchi xodim",
  },
  {
    status: "⏸ Inventar kutilmoqda",
    meaning:
      "Kerakli qism omborda yo'q. Muddat hisoblanmaydi va kechikish deb belgilanmaydi.",
    who: "Bajaruvchi xodim",
  },
  {
    status: "✅ Bajarilgan",
    meaning: "Hisobot yozildi, murojaatchiga xabar va baho so'rovi yuborildi.",
    who: "Bajaruvchi xodim",
  },
  {
    status: "🚫 Qaytarib yuborilgan",
    meaning: "Noto'g'ri murojaat sabab bilan qaytarildi. Ro'yxatdan chiqadi.",
    who: "Boshliq, Admin",
  },
  {
    status: "❌ Bekor qilingan",
    meaning: "Ish to'xtatildi.",
    who: "Bajaruvchi xodim, Admin",
  },
];

const ROLE_ROWS = [
  {
    role: "Murojaatchi (oddiy xodim)",
    can: "Murojaat yuboradi, o'z murojaatlarini ko'radi, yozishadi va bajarilgach baho beradi.",
  },
  {
    role: "RTM xodimi",
    can: "Guruhdan murojaat oladi, ishni boshlaydi, inventar sarflaydi, hisobot bilan yakunlaydi. Faqat o'zining murojaatlarini ko'radi. Guruhni ula olmaydi va uza olmaydi.",
  },
  {
    role: "Boshliq",
    can: "Barcha murojaatlarni ko'radi, xodimga tayinlaydi va murojaatdan chiqaradi, muddat qo'yadi, noto'g'ri murojaatni qaytaradi, inventar va soft bo'limlariga yozadi, RTM guruhini ulaydi va uzadi. Yagona rol — muddat va bajaruvchi belgilab «topshiriq» yubora oladi.",
  },
  {
    role: "Admin (HEMIS hisobi)",
    can: "Boshliqning deyarli barcha huquqlari (guruhni ulash va uzish ham), ustiga admin panel: xodimlar rollari, bo'limlar, HEMIS sinxronizatsiyasi, guruhdagi bot xabarlari va shu sahifa. Topshiriq yubora olmaydi — buning uchun Boshliq roli ham kerak.",
  },
  {
    role: "Panel admin (email/parol)",
    can: "Zaxira kirish yo'li. Hech kimga rol berilmagan paytda ham tizimga kira oladi. Murojaat yubora olmaydi — HEMIS xodimi emas.",
  },
];

/* ------------------------------------------------------------------ *
 * Diagrams
 * ------------------------------------------------------------------ */

const BOX_W = 180;
const BOX_H = 66;

type Tone = "brand" | "slate" | "emerald" | "amber" | "red";

const TONES: Record<Tone, { fill: string; stroke: string; text: string }> = {
  brand: { fill: "#eff6ff", stroke: "#1d4ed8", text: "#1e40af" },
  slate: { fill: "#f8fafc", stroke: "#94a3b8", text: "#334155" },
  emerald: { fill: "#ecfdf5", stroke: "#059669", text: "#047857" },
  amber: { fill: "#fffbeb", stroke: "#d97706", text: "#b45309" },
  red: { fill: "#fef2f2", stroke: "#dc2626", text: "#b91c1c" },
};

function Box({
  x,
  y,
  title,
  subtitle,
  tone = "slate",
  w = BOX_W,
  h = BOX_H,
}: {
  x: number;
  y: number;
  title: string;
  subtitle?: string;
  tone?: Tone;
  w?: number;
  h?: number;
}) {
  const c = TONES[tone];
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={12} fill={c.fill} stroke={c.stroke} strokeWidth={1.5} />
      <text
        x={x + w / 2}
        y={y + (subtitle ? 28 : h / 2 + 5)}
        textAnchor="middle"
        fontSize={14}
        fontWeight={600}
        fill={c.text}
      >
        {title}
      </text>
      {subtitle && (
        <text x={x + w / 2} y={y + 47} textAnchor="middle" fontSize={11} fill="#64748b">
          {subtitle}
        </text>
      )}
    </g>
  );
}

/** A line with a head on the end, and its label placed to suit the direction. */
function Arrow({
  x1,
  y1,
  x2,
  y2,
  label,
  labelY,
  markerId,
  dashed = false,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label?: string;
  /**
   * Where the caption sits. Horizontal arrows run at box mid-height, and the gap between
   * two boxes is narrower than most captions — left just above the line, a caption spills
   * sideways over the boxes it points between. Callers pass the row's top edge so it lands
   * in the empty band above the row instead.
   */
  labelY?: number;
  markerId: string;
  dashed?: boolean;
}) {
  const horizontal = y1 === y2;
  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke="#94a3b8"
        strokeWidth={1.5}
        strokeDasharray={dashed ? "5 4" : undefined}
        markerEnd={`url(#${markerId})`}
      />
      {label && (
        <text
          x={horizontal ? (x1 + x2) / 2 : x1 + 9}
          y={labelY ?? (horizontal ? y1 - 9 : (y1 + y2) / 2 + 4)}
          textAnchor={horizontal ? "middle" : "start"}
          fontSize={10.5}
          fill="#64748b"
        >
          {label}
        </text>
      )}
    </g>
  );
}

function ArrowHead({ id }: { id: string }) {
  return (
    <defs>
      <marker
        id={id}
        viewBox="0 0 10 10"
        refX={9}
        refY={5}
        markerWidth={7}
        markerHeight={7}
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
      </marker>
    </defs>
  );
}

/** Scrolls sideways on a phone rather than shrinking the labels into nothing. */
function DiagramFrame({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <figure className="overflow-x-auto rounded-xl border border-slate-200 bg-white p-4">
      <div className="min-w-[720px]">{children}</div>
      <figcaption className="mt-2 text-center text-xs text-slate-400">{caption}</figcaption>
    </figure>
  );
}

function BotFlowDiagram() {
  const m = "arrow-bot";
  return (
    <svg viewBox="0 0 960 400" className="h-auto w-full" role="img">
      <title>Murojaatning tizim bo'ylab harakati</title>
      <desc>
        Murojaatchi botga yozadi, server saqlaydi, worker guruhga kartochka joylaydi, RTM
        xodimi murojaatni oladi va bajaradi, natija murojaatchiga qaytadi. Veb-sayt orqali
        Boshliq va Admin jarayonni boshqaradi.
      </desc>
      <ArrowHead id={m} />

      <Box x={20} y={30} tone="brand" title="1. Murojaatchi" subtitle="Telegram bot / sayt" />
      <Box x={265} y={30} tone="brand" title="2. Bot qabul qildi" subtitle="Kategoriya, tavsif, fayl" />
      <Box x={510} y={30} tone="slate" title="3. Server + baza" subtitle="RTM-000123 raqami" />
      <Box x={755} y={30} tone="slate" title="4. Navbat + worker" subtitle="Xabarlarni tarqatadi" />

      <Arrow markerId={m} x1={200} y1={63} labelY={22} x2={263} y2={63} label="muammoni yozadi" />
      <Arrow markerId={m} x1={445} y1={63} labelY={22} x2={508} y2={63} label="saqlanadi" />
      <Arrow markerId={m} x1={690} y1={63} labelY={22} x2={753} y2={63} label="navbatga" />
      <Arrow markerId={m} x1={845} y1={96} x2={845} y2={178} label="kartochka joylanadi" />

      <Box x={755} y={180} tone="brand" title="5. RTM guruhi" subtitle="Bitta kartochka" />
      <Box x={510} y={180} tone="brand" title="6. RTM xodimi" subtitle="«✋ Men bajaraman»" />
      <Box x={265} y={180} tone="amber" title="7. Ish bajariladi" subtitle="Yozishma, inventar" />
      <Box x={20} y={180} tone="emerald" title="8. Natija" subtitle="Xabar + ⭐ baho" />

      <Arrow markerId={m} x1={753} y1={213} labelY={172} x2={692} y2={213} label="o'ziga oladi" />
      <Arrow markerId={m} x1={508} y1={213} labelY={172} x2={447} y2={213} label="shaxsiy chatda" />
      <Arrow markerId={m} x1={263} y1={213} labelY={172} x2={202} y2={213} label="yakunlanadi" />

      <Box
        x={20}
        y={310}
        w={915}
        h={62}
        tone="slate"
        title="Veb-sayt — rtm.afu.uz"
        subtitle="Boshliq va Admin: tayinlash, muddat, qaytarish, yozishmalar, hisobot, inventar va soft"
      />
      <Arrow markerId={m} x1={600} y1={308} x2={600} y2={248} label="tayinlaydi" dashed />
      <Arrow markerId={m} x1={845} y1={308} x2={845} y2={248} label="kartochka yangilanadi" dashed />
    </svg>
  );
}

function RequestLifecycleDiagram() {
  const m = "arrow-life";
  return (
    <svg viewBox="0 0 960 290" className="h-auto w-full" role="img">
      <title>Murojaat holatlarining o'zgarishi</title>
      <desc>
        Yangi murojaat tayinlanadi, jarayonga o'tadi va bajariladi. Qism yetishmasa inventar
        kutish holatiga o'tadi, noto'g'ri murojaat qaytarib yuboriladi, bajarilgani uchun
        murojaatchi baho beradi.
      </desc>
      <ArrowHead id={m} />

      <Box x={20} y={24} h={62} tone="slate" title="🆕 Yangi" subtitle="Hech kim olmagan" />
      <Box x={265} y={24} h={62} tone="brand" title="👤 Tayinlangan" subtitle="Bajaruvchi bor" />
      <Box x={510} y={24} h={62} tone="brand" title="⏳ Jarayonda" subtitle="Ish ketmoqda" />
      <Box x={755} y={24} h={62} tone="emerald" title="✅ Bajarilgan" subtitle="Hisobot yozildi" />

      <Arrow markerId={m} x1={200} y1={55} labelY={16} x2={263} y2={55} label="oladi / tayinlanadi" />
      <Arrow markerId={m} x1={445} y1={55} labelY={16} x2={508} y2={55} label="ishni boshladi" />
      <Arrow markerId={m} x1={690} y1={55} labelY={16} x2={753} y2={55} label="yakunladi" />

      <Box
        x={20}
        y={180}
        h={62}
        tone="red"
        title="🚫 Qaytarib yuborilgan"
        subtitle="Ro'yxatdan chiqadi"
      />
      <Box x={265} y={180} h={62} tone="slate" title="❌ Bekor qilingan" subtitle="Ish to'xtatildi" />
      <Box x={510} y={180} h={62} tone="amber" title="⏸ Inventar kutilmoqda" subtitle="Qism yo'q" />
      <Box x={755} y={180} h={62} tone="emerald" title="⭐ Baho" subtitle="Murojaatchi baholaydi" />

      <Arrow markerId={m} x1={110} y1={88} x2={110} y2={178} label="Boshliq/Admin sabab bilan" />
      <Arrow markerId={m} x1={355} y1={88} x2={355} y2={178} label="istalgan bosqichda" dashed />
      <Arrow markerId={m} x1={560} y1={88} x2={560} y2={178} label="qism yo'q" />
      <Arrow markerId={m} x1={645} y1={178} x2={645} y2={88} label="qism keldi" />
      <Arrow markerId={m} x1={845} y1={88} x2={845} y2={178} label="so'raladi" />
    </svg>
  );
}

/* ------------------------------------------------------------------ *
 * Layout helpers
 * ------------------------------------------------------------------ */

function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="mb-10">
      <h2 className="text-lg font-bold text-slate-900 sm:text-xl">{title}</h2>
      <p className="mb-4 mt-0.5 text-sm text-slate-500">{lead}</p>
      {children}
    </section>
  );
}

function Card({ title, tone, children }: { title: string; tone: Tone; children: ReactNode }) {
  const border = {
    brand: "border-brand-100",
    slate: "border-slate-200",
    emerald: "border-emerald-200",
    amber: "border-amber-200",
    red: "border-red-200",
  }[tone];

  return (
    <div className={`rounded-xl border bg-white p-4 ${border}`}>
      <div className="mb-2 font-semibold text-slate-800">{title}</div>
      <div className="text-sm text-slate-600">{children}</div>
    </div>
  );
}

function Callout({
  tone,
  title,
  children,
}: {
  tone: Tone;
  title: string;
  children: ReactNode;
}) {
  const skin = {
    brand: "border-brand-100 bg-brand-50 text-brand-700",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-800",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    red: "border-red-200 bg-red-50 text-red-800",
  }[tone];

  return (
    <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${skin}`}>
      <div className="mb-1 font-semibold">{title}</div>
      <div>{children}</div>
    </div>
  );
}
