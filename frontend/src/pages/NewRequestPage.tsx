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
  const { session, isAdmin } = useAuth();
  // Boshliq and Admin can name who will do the work while they are filing it. For everyone
  // else the request goes into the queue unassigned, exactly as it always has.
  const canAssign =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

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
    if (!canAssign) return;
    employeesApi.rtmStaff().then(setStaff).catch(() => setStaff([]));
  }, [canAssign]);

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
        assigned_to_employee_ids: canAssign ? assigneeIds : [],
        // datetime-local carries no timezone, so the browser reads it as local time —
        // which is what the person typing it meant. toISOString hands UTC to the server.
        deadline_at: canAssign && deadline ? new Date(deadline).toISOString() : null,
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
        title="Yangi murojaat"
        subtitle="Muammoni tasvirlab bering — RTM guruhiga darhol yetkaziladi"
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
          {canAssign && (
            <section className="rounded-xl border border-brand-200 bg-brand-50/40 p-5">
              <div className="mb-1 font-medium text-slate-800">🛠 Bajaruvchini belgilash</div>
              <p className="mb-3 text-xs text-slate-500">
                Boshliq va Admin uchun. Birinchi tanlangan xodim mas'ul bo'ladi va har biriga
                Telegram orqali xabar boradi. Bo'sh qoldirsangiz, murojaat guruhga
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

              <label className="mt-4 block">
                <span className="mb-1 block text-xs font-medium text-slate-600">
                  Muddat <span className="font-normal text-slate-400">(ixtiyoriy)</span>
                </span>
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
                />
              </label>
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
              {canAssign && (
                <Check done={assigneeIds.length > 0} optional>
                  {assigneeIds.length > 0
                    ? `${assigneeIds.length} ta bajaruvchi tanlandi`
                    : "Bajaruvchi belgilanmagan"}
                </Check>
              )}
            </div>

            <button
              type="submit"
              disabled={!ready || busy}
              className="w-full rounded-lg bg-brand-600 px-4 py-3 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? progress ?? "Yuborilmoqda..." : "📨 Murojaatni yuborish"}
            </button>
            <p className="mt-2 text-center text-xs text-slate-400">
              Yuborilgandan so'ng murojaat sahifasiga o'tasiz.
            </p>
          </section>
        </div>
      </form>
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
