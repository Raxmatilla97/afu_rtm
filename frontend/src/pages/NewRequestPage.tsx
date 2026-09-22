import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { describeError } from "@/api/errors";
import { categoriesApi, employeesApi } from "@/api/reference";
import { requestsApi } from "@/api/requests";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { RichTextEditor } from "@/components/RichTextEditor";
import { useAuth } from "@/context/AuthContext";
import { htmlToText, isEmptyHtml } from "@/lib/richtext";
import type { Category, Employee } from "@/types";

/**
 * One glyph per category, so the picker can be read at a glance.
 *
 * Keyed by the seeded slugs; anything added later falls back to the last entry rather than
 * rendering an empty square. A category with no icon still works — it just looks plainer.
 */
const CATEGORY_ICONS: Record<string, string> = {
  printer: "🖨",
  software: "💻",
  network: "🌐",
  hardware: "🔧",
  account: "🔑",
  email: "✉️",
  av_equipment: "📽",
  telephony: "☎️",
  website: "🕸",
  new_equipment: "🆕",
  cabling: "🔌",
  other: "📋",
};

/** How large one attachment may be. Mirrors MAX_UPLOAD_BYTES on the server. */
const MAX_FILE_BYTES = 25 * 1024 * 1024;

/**
 * The deadlines a Boshliq actually sets, as whole units of time from now.
 *
 * The same six the bot offers, in the same order and with the same wording — a directive
 * issued from a phone and one issued from a desk have to be the same object, and "2 soat"
 * meaning something different in the two places is the kind of difference nobody reports
 * and everybody works around.
 */
const DEADLINE_PRESETS: ReadonlyArray<readonly [string, number]> = [
  ["1 soat", 60],
  ["2 soat", 120],
  ["6 soat", 360],
  ["1 kun", 24 * 60],
  ["2 kun", 48 * 60],
  ["1 hafta", 7 * 24 * 60],
];

/** `minutes` from now, formatted for `<input type="datetime-local">` in local time. */
function deadlineFromNow(minutes: number): string {
  const at = new Date(Date.now() + minutes * 60_000);
  // toISOString would hand back UTC, which the control then reads as local — an hour or
  // five off depending on where the reader is sitting.
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
    `T${pad(at.getHours())}:${pad(at.getMinutes())}`
  );
}

interface Picked {
  file: File;
  /** Object URL for an image, so the writer can see what they attached. Revoked on removal. */
  preview: string | null;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function NewRequestPage() {
  const navigate = useNavigate();
  const { session } = useAuth();

  // Three different people reach this page and they need three different pages.
  //
  // A **Boshliq** (including one who is also an Admin) files a *directive*: it goes out with
  // a deadline and a named team, and the RTM group card says who issued it. That is the
  // "boshqacha interfeys" below — a banner, a deadline picker and a staff picker.
  //
  // An employee flagged **only Admin** does not get it. Admin is the panel role: they add
  // employees and fix records. Committing RTM to a deadline is the head's call, so they
  // file an ordinary request and are told, in as many words, why the extra controls are
  // not there.
  //
  // A **panel admin** — the email/password login — has no employee identity at all, so
  // there is nobody to file *as*. The server refuses it; saying so before they type five
  // paragraphs is the least the page can do.
  const employee = session.kind === "employee" ? session.employee : null;
  const canDirect = Boolean(employee?.can_file_managed_request);
  const roleLabel = employee?.management_role ?? null;
  const adminWithoutBoshliq = Boolean(employee?.is_admin && !employee.is_supervisor);
  const isPanelAdmin = session.kind === "admin";

  const [categories, setCategories] = useState<Category[]>([]);
  const [categorySlug, setCategorySlug] = useState("");
  const [descriptionHtml, setDescriptionHtml] = useState("");
  const [picked, setPicked] = useState<Picked[]>([]);
  const [staff, setStaff] = useState<Employee[]>([]);
  const [assigneeIds, setAssigneeIds] = useState<number[]>([]);
  const [deadline, setDeadline] = useState("");

  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    categoriesApi.list().then(setCategories).catch((e) => setError(describeError(e)));
  }, []);

  useEffect(() => {
    if (!canDirect) return;
    employeesApi.rtmStaff().then(setStaff).catch(() => setStaff([]));
  }, [canDirect]);

  // Object URLs are a real allocation — each one pins the whole image in memory until it is
  // revoked. Removing a file revokes its own; this releases whatever is still held when the
  // page is left. It reads through a ref because the cleanup of a mount-time effect closes
  // over the *first* render's state, which is always the empty list.
  const pickedRef = useRef<Picked[]>([]);
  pickedRef.current = picked;
  useEffect(() => {
    return () =>
      pickedRef.current.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
  }, []);

  const plainDescription = useMemo(() => htmlToText(descriptionHtml), [descriptionHtml]);
  const chosenCategory = categories.find((c) => c.slug === categorySlug) ?? null;
  const ready = Boolean(categorySlug) && !isEmptyHtml(descriptionHtml);

  function addFiles(incoming: FileList | File[]) {
    const accepted: Picked[] = [];
    const tooBig: string[] = [];
    for (const file of Array.from(incoming)) {
      if (file.size > MAX_FILE_BYTES) {
        tooBig.push(file.name);
        continue;
      }
      accepted.push({
        file,
        preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      });
    }
    // Refused here rather than at upload time: finding out a file was too large only after
    // the request has already been created is the worst moment to be told.
    setError(
      tooBig.length
        ? `Bu fayllar 25 MB dan katta va qo'shilmadi: ${tooBig.join(", ")}`
        : null,
    );
    if (accepted.length) setPicked((current) => [...current, ...accepted]);
  }

  function removeFile(index: number) {
    setPicked((current) => {
      const item = current[index];
      if (item?.preview) URL.revokeObjectURL(item.preview);
      return current.filter((_, i) => i !== index);
    });
  }

  function toggleAssignee(employeeId: number) {
    setAssigneeIds((current) =>
      current.includes(employeeId)
        ? current.filter((x) => x !== employeeId)
        : // Appended, never prepended: the first pick is the lead, and choosing a second
          // person must not quietly demote the first.
          [...current, employeeId],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || busy) return;

    setBusy(true);
    setError(null);
    try {
      setProgress("Murojaat yaratilmoqda...");
      const created = await requestsApi.create({
        category_slug: categorySlug,
        description: plainDescription,
        description_html: descriptionHtml || null,
        assigned_to_employee_ids: canDirect ? assigneeIds : [],
        // datetime-local carries no timezone, so the browser reads it as local time —
        // which is what the person typing it meant. toISOString hands UTC to the server.
        deadline_at: canDirect && deadline ? new Date(deadline).toISOString() : null,
      });

      // Attached afterwards because an attachment needs a request to belong to. If one
      // file fails the request still exists, so the writer is taken to it rather than
      // losing everything they typed.
      const failed: string[] = [];
      for (const [index, item] of picked.entries()) {
        setProgress(`Fayl yuklanmoqda (${index + 1}/${picked.length})...`);
        try {
          await requestsApi.uploadAttachment(created.id, item.file);
        } catch {
          failed.push(item.file.name);
        }
      }
      if (failed.length) {
        // Not thrown: the request itself was filed, and sending the writer back to an empty
        // form over a failed upload would lose it.
        window.alert(
          `Murojaat yaratildi, ammo bu fayllar yuklanmadi: ${failed.join(", ")}.\n` +
            "Ularni murojaat sahifasidagi yozishmalar orqali qayta yuboring.",
        );
      }
      navigate(`/requests/${created.id}`);
    } catch (err) {
      setError(describeError(err));
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    // Full width, like the list and the detail page this sits between. The old form was
    // capped at 36rem, which left a rich editor, a category grid and an assignment panel
    // fighting over a third of the screen.
    <div>
      <PageHeader
        title={canDirect ? `Yangi topshiriq · ${roleLabel}` : "Yangi murojaat"}
        subtitle={
          canDirect
            ? "Muddat va bajaruvchi belgilab yuboriladi — RTM guruhida alohida kartochka bo'lib chiqadi"
            : "Muammoni tasvirlab bering — RTM guruhiga darhol yetkaziladi"
        }
        action={
          <Link
            to="/requests"
            className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 bg-white px-4 text-sm text-slate-700 hover:bg-slate-50"
          >
            ← Murojaatlar
          </Link>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* The three audiences from the comment at the top of this component, each told what
          they are looking at before they start typing rather than after they press send. */}
      {isPanelAdmin && (
        <Alert tone="danger" icon="🔒" title="Admin hisobidan murojaat yuborilmaydi">
          Siz elektron pochta va parol bilan kirgan <b>panel admini</b>siz — bu hisob hech
          qaysi xodimga bog'lanmagan, shuning uchun murojaatni <i>kim nomidan</i> yuborishni
          tizim bila olmaydi va server uni rad etadi.
          <br />
          Murojaat yubormoqchi bo'lsangiz, HEMIS yoki «⚡ Tezkor kirish» orqali o'z xodim
          hisobingiz bilan kiring. Boshqalarning murojaatlarini{" "}
          <Link to="/requests" className="font-medium underline">
            «Murojaatlar»
          </Link>{" "}
          sahifasida ko'rib, tayinlab va yakunlab borishingiz mumkin.
        </Alert>
      )}

      {canDirect && (
        <Alert
          tone="brand"
          icon={roleLabel === "ADMIN" ? "🛡" : "👑"}
          title={`${roleLabel} rejimi yoqildi`}
        >
          Sizda <b>Boshliq</b> roli bor, shuning uchun bu sahifa kengaytirilgan ko'rinishda:
          murojaatni yuborish bilan birga <b>bajarish muddatini</b> va{" "}
          <b>mas'ul xodimlarni</b> ham belgilay olasiz.
          <ul className="mt-2 list-disc space-y-0.5 pl-5">
            <li>
              RTM guruhiga oddiy murojaat emas, <b>«{roleLabel} TOPSHIRIG'I»</b> kartochkasi
              tushadi va boshqa murojaatlardan ajralib turadi.
            </li>
            <li>Tanlangan har bir xodimga Telegram orqali darhol xabar boradi.</li>
            <li>
              Muddat — bu RTM nomidan berilgan va'da: o'tib ketsa, kartochka guruhda qizil
              «MUDDAT O'TDI» holatiga o'tadi.
            </li>
            <li>Muddat va bajaruvchi — ixtiyoriy. Bo'sh qoldirsangiz oddiy murojaat bo'ladi.</li>
          </ul>
        </Alert>
      )}

      {adminWithoutBoshliq && (
        <Alert tone="warning" icon="⚠️" title="Sizda faqat Admin roli bor">
          Muddat va bajaruvchi belgilab <b>topshiriq</b> yuborishni faqat <b>Boshliq</b>{" "}
          roliga ega xodim qila oladi — Admin roli tizimni boshqarish uchun (xodimlar,
          bo'limlar, sozlamalar), murojaatni kimga va qachongacha topshirish esa RTM
          boshlig'ining qarori.
          <br />
          Siz quyidagi oddiy shakl orqali murojaat yuborishingiz mumkin; u navbatga
          «egasiz» bo'lib tushadi va xodimlar o'zlari oladi. Topshiriq berish kerak bo'lsa,
          hisobingizga <b>Boshliq</b> rolini ham qo'shish lozim.
        </Alert>
      )}

      <form
        onSubmit={handleSubmit}
        className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]"
      >
        <div className="space-y-6">
          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <SectionTitle step={1} title="Murojaat turi" hint="Qaysi sohaga tegishli?" />
            {categories.length === 0 ? (
              <div className="text-sm text-slate-400">Kategoriyalar yuklanmoqda...</div>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
                {categories.map((category) => {
                  const chosen = category.slug === categorySlug;
                  return (
                    <button
                      key={category.slug}
                      type="button"
                      onClick={() => setCategorySlug(category.slug)}
                      aria-pressed={chosen}
                      className={`flex min-h-16 items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                        chosen
                          ? "border-brand-600 bg-brand-50 font-medium text-brand-700"
                          : "border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <span aria-hidden className="text-xl">
                        {CATEGORY_ICONS[category.slug] ?? "📋"}
                      </span>
                      <span className="min-w-0">{category.label_uz}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <SectionTitle
              step={2}
              title="Tavsif"
              hint="Qaysi bino, qaysi xona, qaysi qurilma — qancha aniq bo'lsa, shuncha tez hal bo'ladi"
            />
            <RichTextEditor
              value={descriptionHtml}
              onChange={setDescriptionHtml}
              disabled={busy}
              minHeightClass="min-h-[14rem]"
              placeholder="Masalan: 3-bino, 204-xona. Printerdan qog'oz chiqmayapti, ekranda «paper jam» yozuvi turibdi..."
            />
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <SectionTitle
              step={3}
              title="Materiallar"
              hint="Ixtiyoriy — surat, video yoki hujjat, har biri 25 MB gacha"
            />
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
              }}
              onClick={() => fileInput.current?.click()}
              className={`cursor-pointer rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm transition-colors ${
                dragging
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-slate-300 text-slate-500 hover:border-slate-400 hover:bg-slate-50"
              }`}
            >
              <div className="text-2xl" aria-hidden>
                📎
              </div>
              <div className="mt-1 font-medium">Fayllarni bu yerga tashlang</div>
              <div className="text-xs text-slate-400">yoki bosing va kompyuterdan tanlang</div>
            </div>
            <input
              ref={fileInput}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                // Cleared so choosing the same file twice in a row still fires a change.
                e.target.value = "";
              }}
            />

            {picked.length > 0 && (
              <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                {picked.map((item, index) => (
                  <li
                    key={`${item.file.name}-${index}`}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 p-2"
                  >
                    {item.preview ? (
                      <img
                        src={item.preview}
                        alt=""
                        className="h-12 w-12 shrink-0 rounded object-cover"
                      />
                    ) : (
                      <span
                        aria-hidden
                        className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-slate-100 text-xl"
                      >
                        📄
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-slate-800">{item.file.name}</div>
                      <div className="text-xs text-slate-400">{humanSize(item.file.size)}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      aria-label={`${item.file.name} faylini olib tashlash`}
                      className="shrink-0 rounded-full px-2 py-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    >
                      ✖
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="space-y-6 lg:sticky lg:top-8">
          {canDirect && (
            <section className="overflow-hidden rounded-xl border-2 border-brand-300 bg-brand-50/50">
              {/* A filled header bar, not another white card: this panel is the one thing on
                  the page that is not on everybody else's, and it has to look like it. */}
              <div className="flex items-center gap-2 bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white">
                <span aria-hidden>{roleLabel === "ADMIN" ? "🛡" : "👑"}</span>
                {roleLabel} topshirig'i
              </div>

              <div className="space-y-5 p-5">
                <div>
                  <div className="mb-1 text-sm font-medium text-slate-800">
                    ⏱ Bajarish muddati
                  </div>
                  <p className="mb-2 text-xs text-slate-500">
                    Hozirdan boshlab hisoblanadi. Muddat o'tsa, guruhdagi kartochka qizil
                    «MUDDAT O'TDI» holatiga o'tadi va xodimlarga eslatma boradi.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {DEADLINE_PRESETS.map(([label, minutes]) => {
                      const value = deadlineFromNow(minutes);
                      // Compared to the minute: the preset is "6 hours from now", and a
                      // value computed a minute ago is still the button the user pressed.
                      const chosen = deadline.slice(0, 16) === value.slice(0, 16);
                      return (
                        <button
                          key={label}
                          type="button"
                          onClick={() => setDeadline(chosen ? "" : value)}
                          aria-pressed={chosen}
                          className={`min-h-9 rounded-full border px-3 text-xs font-medium transition-colors ${
                            chosen
                              ? "border-brand-600 bg-brand-600 text-white"
                              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                          }`}
                        >
                          {chosen ? "✓ " : ""}
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-xs font-medium text-slate-600">
                      yoki aniq sana va vaqt{" "}
                      <span className="font-normal text-slate-400">(ixtiyoriy)</span>
                    </span>
                    <input
                      type="datetime-local"
                      value={deadline}
                      onChange={(e) => setDeadline(e.target.value)}
                      className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
                    />
                  </label>
                </div>

                <div className="border-t border-brand-200 pt-4">
                  <div className="mb-1 text-sm font-medium text-slate-800">
                    🛠 Tayinlangan xodimlar
                  </div>
                  <p className="mb-2 text-xs text-slate-500">
                    Birinchi tanlangan xodim <b>mas'ul</b> bo'ladi va har biriga Telegram
                    orqali darhol xabar boradi. Bo'sh qoldirsangiz, topshiriq guruhga
                    «egasiz» bo'lib tushadi va xodimlar o'zlari oladi.
                  </p>
                  {staff.length === 0 ? (
                    <div className="text-xs text-slate-400">RTM xodimlari ro'yxati bo'sh.</div>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {staff.map((person) => {
                        const chosen = assigneeIds.includes(person.id);
                        const lead = assigneeIds.indexOf(person.id) === 0;
                        return (
                          <button
                            key={person.id}
                            type="button"
                            onClick={() => toggleAssignee(person.id)}
                            aria-pressed={chosen}
                            className={`min-h-9 rounded-full border px-3 text-xs font-medium transition-colors ${
                              chosen
                                ? "border-brand-600 bg-brand-600 text-white"
                                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                            }`}
                          >
                            {chosen ? (lead ? "⭐ " : "✓ ") : ""}
                            {person.full_name}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {assigneeIds.length > 1 && (
                    <p className="mt-2 text-[11px] text-slate-500">
                      ⭐ — mas'ul xodim. Tartibni o'zgartirish uchun tanlovni bekor qilib,
                      mas'ul bo'ladigan xodimni birinchi bo'lib bosing.
                    </p>
                  )}
                </div>
              </div>
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-3 font-medium text-slate-800">Yuborishga tayyormi?</div>
            <div className="mb-4 space-y-1.5 text-sm">
              <Check done={Boolean(chosenCategory)}>
                {chosenCategory ? chosenCategory.label_uz : "Murojaat turi tanlanmagan"}
              </Check>
              <Check done={!isEmptyHtml(descriptionHtml)}>
                {plainDescription.length > 0
                  ? `Tavsif — ${plainDescription.length} belgi`
                  : "Tavsif yozilmagan"}
              </Check>
              <Check done={picked.length > 0} optional>
                {picked.length > 0 ? `${picked.length} ta material` : "Material biriktirilmagan"}
              </Check>
              {canDirect && (
                <>
                  <Check done={Boolean(deadline)} optional>
                    {deadline
                      ? `Muddat — ${new Date(deadline).toLocaleString("uz-UZ", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}`
                      : "Muddat belgilanmagan"}
                  </Check>
                  <Check done={assigneeIds.length > 0} optional>
                    {assigneeIds.length > 0
                      ? `${assigneeIds.length} ta xodim tayinlandi`
                      : "Xodim tayinlanmagan"}
                  </Check>
                </>
              )}
            </div>

            <button
              type="submit"
              disabled={!ready || busy || isPanelAdmin}
              className="w-full rounded-lg bg-brand-600 px-4 py-3 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy
                ? progress ?? "Yuborilmoqda..."
                : canDirect
                  ? "📨 Topshiriqni yuborish"
                  : "📨 Murojaatni yuborish"}
            </button>
            <p className="mt-2 text-center text-xs text-slate-400">
              {canDirect
                ? "Yuborilgach guruhga topshiriq kartochkasi tushadi va siz uning sahifasiga o'tasiz."
                : "Yuborilgandan so'ng murojaat sahifasiga o'tasiz."}
            </p>
          </section>
        </div>
      </form>
    </div>
  );
}

/**
 * A framed explanation above the form.
 *
 * Separate from `ErrorBanner`, which reports something that went wrong. These say what kind
 * of page the reader is on before they spend five minutes on it — which role they are
 * filing as, what the extra controls will do, or why the controls they expected are absent.
 */
function Alert({
  tone,
  icon,
  title,
  children,
}: {
  tone: "brand" | "warning" | "danger";
  icon: string;
  title: string;
  children: React.ReactNode;
}) {
  const tones = {
    brand: "border-brand-300 bg-brand-50 text-slate-700",
    warning: "border-amber-300 bg-amber-50 text-amber-900",
    danger: "border-red-300 bg-red-50 text-red-900",
  } as const;

  return (
    <div className={`mb-6 flex gap-3 rounded-xl border p-4 text-sm ${tones[tone]}`} role="note">
      <span aria-hidden className="text-xl leading-none">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="mb-1 font-semibold">{title}</div>
        <div className="leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

function SectionTitle({ step, title, hint }: { step: number; title: string; hint: string }) {
  return (
    <div className="mb-3 flex items-start gap-3">
      <span
        aria-hidden
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-500"
      >
        {step}
      </span>
      <div className="min-w-0">
        <div className="font-medium text-slate-800">{title}</div>
        <div className="text-xs text-slate-400">{hint}</div>
      </div>
    </div>
  );
}

/**
 * One line of the readiness list.
 *
 * `optional` items never block sending, so an unfinished one gets a dash rather than the
 * empty circle that means "still to do" — otherwise the list reads as four things left
 * undone when only two of them actually hold the button back.
 */
function Check({
  done,
  optional = false,
  children,
}: {
  done: boolean;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2">
      <span aria-hidden className={done ? "text-emerald-600" : "text-slate-300"}>
        {done ? "✓" : optional ? "–" : "○"}
      </span>
      <span className={done ? "text-slate-700" : "text-slate-400"}>{children}</span>
    </div>
  );
}
