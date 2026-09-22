import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { describeError } from "@/api/errors";
import { inventoryApi, type ItemDraft } from "@/api/inventory";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { useAuth } from "@/context/AuthContext";
import type {
  InventoryCategory,
  InventoryItem,
  InventoryMovement,
  InventorySummary,
  Money,
  WriteOffPage,
} from "@/types";

const EMPTY_DRAFT: ItemDraft = {
  category_slug: "",
  name: "",
  unit: "dona",
  min_quantity: 0,
  unit_price: null,
  status: "available",
  note: null,
  initial_quantity: 0,
};

const STATUS_OPTIONS = [
  ["available", "✅ Mavjud"],
  ["planned", "📝 Rejalashtirilgan"],
  ["ordered", "🚚 Buyurtma qilingan"],
  ["archived", "📦 Arxivda"],
] as const;

const MOVEMENT_OPTIONS = [
  ["purchase", "🛒 Kirim (sotib olindi)", 1],
  ["return", "↩️ Qaytarildi", 1],
  ["write_off", "🗑 Hisobdan chiqarish", -1],
  ["adjustment", "✏️ Tuzatish", 1],
] as const;

/** Rows per page of the write-off ledger. Mirrors WRITE_OFF_PAGE_SIZE on the server. */
const WRITE_OFF_PAGE_SIZE = 50;

interface WriteOffFilters {
  q: string;
  categorySlug: string;
  from: string;
  to: string;
  page: number;
}

const EMPTY_WRITE_OFF_FILTERS: WriteOffFilters = {
  q: "",
  categorySlug: "",
  from: "",
  to: "",
  page: 0,
};

/**
 * The date ranges people actually ask for, so the common case is one tap rather than two
 * date pickers. "Bu oy" is first because a write-off register is read at month end.
 */
const WRITE_OFF_RANGES: ReadonlyArray<readonly [string, () => { from: string; to: string }]> = [
  ["Bu oy", () => ({ from: localIso(startOfMonth()), to: "" })],
  ["Oxirgi 30 kun", () => ({ from: localIso(daysAgo(30)), to: "" })],
  ["Oxirgi 90 kun", () => ({ from: localIso(daysAgo(90)), to: "" })],
  ["Bu yil", () => ({ from: `${new Date().getFullYear()}-01-01`, to: "" })],
  ["Barchasi", () => ({ from: "", to: "" })],
];

function money(value: Money): string {
  if (!value) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toLocaleString("uz-UZ")} so'm` : String(value);
}

function fullDateTime(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * `yyyy-mm-dd` in the reader's own timezone — what `<input type="date">` shows and what the
 * API filters on. `toISOString` would hand back the UTC date, which in UTC+5 is yesterday
 * for the first five hours of every day: "Bu oy" pressed on the 1st of October would have
 * quietly filtered from the 30th of September.
 */
function localIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function daysAgo(days: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d;
}

function startOfMonth(): Date {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

export function InventoryPage() {
  const { isAdmin, session } = useAuth();
  const canWrite =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

  // In the URL, not in state: the write-off register is the thing people are sent to look
  // at ("see what we scrapped in March"), and a tab that cannot be linked to means that
  // message has to carry directions instead of a link.
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "write-offs" ? "write-offs" : "stock";

  const [categories, setCategories] = useState<InventoryCategory[]>([]);
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [q, setQ] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [onlyLow, setOnlyLow] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ItemDraft>(EMPTY_DRAFT);
  const [openItem, setOpenItem] = useState<InventoryItem | null>(null);
  const [movements, setMovements] = useState<InventoryMovement[]>([]);

  const [writeOffs, setWriteOffs] = useState<WriteOffPage | null>(null);
  const [writeOffFilters, setWriteOffFilters] = useState<WriteOffFilters>(EMPTY_WRITE_OFF_FILTERS);

  const load = useCallback(async () => {
    try {
      const [cats, list, sum] = await Promise.all([
        inventoryApi.categories(),
        inventoryApi.items({
          q: q || undefined,
          category_slug: categoryFilter || undefined,
          only_low: onlyLow || undefined,
          include_archived: includeArchived || undefined,
        }),
        inventoryApi.summary(),
      ]);
      setCategories(cats);
      setItems(list);
      setSummary(sum);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    }
  }, [q, categoryFilter, onlyLow, includeArchived]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  // The tab count in the navigation reads from this, so it loads even while the stock tab
  // is showing: "Hisobdan chiqarilganlar · 41 ta yozuv" is the whole reason somebody goes
  // and looks, and a tab that only counts itself once opened never prompts anybody.
  const loadWriteOffs = useCallback(async () => {
    try {
      setWriteOffs(
        await inventoryApi.writeOffs({
          q: writeOffFilters.q || undefined,
          category_slug: writeOffFilters.categorySlug || undefined,
          date_from: writeOffFilters.from || undefined,
          date_to: writeOffFilters.to || undefined,
          limit: WRITE_OFF_PAGE_SIZE,
          offset: writeOffFilters.page * WRITE_OFF_PAGE_SIZE,
        }),
      );
    } catch (e) {
      setError(describeError(e));
    }
  }, [writeOffFilters]);

  useEffect(() => {
    const t = setTimeout(loadWriteOffs, 250);
    return () => clearTimeout(t);
  }, [loadWriteOffs]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      // Both, always: a write-off booked from the stock tab belongs in the ledger and in
      // the tab count immediately, not on the next reload.
      await Promise.all([load(), loadWriteOffs()]);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  async function openMovements(item: InventoryItem) {
    setOpenItem(item);
    try {
      setMovements(await inventoryApi.movements(item.id));
    } catch (e) {
      setError(describeError(e));
    }
  }

  const columns: Column<InventoryItem>[] = [
    {
      key: "name",
      header: "Nomi",
      mobile: "title",
      cell: (item) => item.name,
    },
    {
      key: "meta",
      header: "Kategoriya",
      mobile: "meta",
      cell: (item) => (
        <>
          {item.category_label}
          {item.note ? ` — ${item.note}` : ""}
        </>
      ),
    },
    {
      key: "quantity",
      header: "Qoldiq",
      align: "right",
      cell: (item) => (
        <>
          <span
            className={`font-semibold tabular-nums ${
              item.is_low ? "text-red-600" : "text-slate-800"
            }`}
          >
            {item.quantity}
          </span>
          <span className="text-xs text-slate-400"> {item.unit}</span>
          {item.min_quantity > 0 && (
            <span className="ml-1 text-[11px] text-slate-400">min {item.min_quantity}</span>
          )}
        </>
      ),
    },
    {
      key: "price",
      header: "Narxi",
      align: "right",
      cell: (item) => <span className="tabular-nums">{money(item.unit_price)}</span>,
    },
    {
      key: "status",
      header: "Holati",
      cell: (item) => <span className="text-xs">{item.status_label}</span>,
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (item) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
          <button
            onClick={() => openMovements(item)}
            className="min-h-9 rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
          >
            📜 Tarix
          </button>
          {canWrite && <MovementButton item={item} busy={busy} onSubmit={run} />}
        </div>
      ),
    },
  ];

  return (
    // Full width: eight columns of register, six summary tiles and a filter bar. Anything
    // narrower just puts a scrollbar under a table the screen could have shown whole.
    <div>
      <PageHeader
        title="RTM Inventar"
        subtitle="Ombor qoldig'i, sarflar va xaridlar. Har bir o'zgarish sababi bilan yoziladi."
        action={
          canWrite &&
          tab === "stock" && (
            <button
              onClick={() => {
                setCreating((v) => !v);
                setDraft({ ...EMPTY_DRAFT, category_slug: categories[0]?.slug ?? "" });
              }}
              className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700"
            >
              {creating ? "✖️ Bekor qilish" : "➕ Yangi inventar"}
            </button>
          )
        }
      />

      <nav className="mb-6 flex flex-wrap gap-2 border-b border-slate-200">
        <TabButton
          active={tab === "stock"}
          onClick={() => setParams({}, { replace: true })}
          icon="📦"
          label="Ombor qoldig'i"
          note={summary ? `${summary.total_items} tur` : undefined}
        />
        <TabButton
          active={tab === "write-offs"}
          onClick={() => setParams({ tab: "write-offs" }, { replace: true })}
          icon="🗑"
          label="Hisobdan chiqarilganlar"
          note={writeOffs ? `${writeOffs.total} ta yozuv` : undefined}
        />
      </nav>

      {error && <ErrorBanner message={error} />}

      {tab === "write-offs" ? (
        <WriteOffRegister
          categories={categories}
          page={writeOffs}
          filters={writeOffFilters}
          onFilters={setWriteOffFilters}
          onError={setError}
        />
      ) : (
        <>
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Tile label="Turlari" value={summary.total_items} />
          <Tile label="Omborda bor" value={summary.in_stock_items} tone="#0ca30c" />
          <Tile
            label="Tugayapti"
            value={summary.low_items}
            tone={summary.low_items ? "#d03b3b" : undefined}
            icon={summary.low_items ? "⚠️" : undefined}
          />
          <Tile label="Rejada" value={summary.planned_items} />
          <Tile label="Ombor qiymati" value={money(summary.stock_value)} small />
          <Tile
            label="Shu oy sarflandi"
            value={summary.consumed_this_month}
            note={summary.spent_this_month ? `xarid: ${money(summary.spent_this_month)}` : undefined}
          />
        </div>
      )}

      {creating && canWrite && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.name.trim() || !draft.category_slug) return;
            void run(async () => {
              await inventoryApi.createItem(draft);
              setCreating(false);
              setDraft(EMPTY_DRAFT);
            });
          }}
          className="mb-6 grid gap-3 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-2 lg:grid-cols-3"
        >
          <Field label="Nomi">
            <input
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="HP 85A toner"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Kategoriya">
            <select
              required
              value={draft.category_slug}
              onChange={(e) => setDraft({ ...draft, category_slug: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Tanlang</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.label_uz}
                </option>
              ))}
            </select>
          </Field>
          <Field label="O'lchov birligi">
            <input
              value={draft.unit}
              onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Boshlang'ich qoldiq">
            <input
              type="number"
              min={0}
              value={draft.initial_quantity}
              onChange={(e) =>
                setDraft({ ...draft, initial_quantity: Number(e.target.value) || 0 })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Minimal qoldiq" hint="Shu songa yetganda ogohlantiriladi. 0 — o'chiq">
            <input
              type="number"
              min={0}
              value={draft.min_quantity}
              onChange={(e) => setDraft({ ...draft, min_quantity: Number(e.target.value) || 0 })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Narxi (ixtiyoriy)" hint="Bir dona uchun, so'mda">
            <input
              type="number"
              min={0}
              step="0.01"
              value={draft.unit_price ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, unit_price: e.target.value ? e.target.value : null })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Holati">
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {STATUS_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Izoh (ixtiyoriy)" className="sm:col-span-2">
            <input
              value={draft.note ?? ""}
              onChange={(e) => setDraft({ ...draft, note: e.target.value || null })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <div className="flex items-end lg:col-span-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Saqlash
            </button>
          </div>
        </form>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Nomi bo'yicha qidirish..."
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-64"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.label_uz} ({c.item_count})
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={onlyLow}
            onChange={(e) => setOnlyLow(e.target.checked)}
          />
          Faqat tugayotganlar
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Arxivdagilar bilan
        </label>
      </div>

      <ResponsiveTable
        rows={items}
        columns={columns}
        rowKey={(i) => i.id}
        empty="Hech narsa topilmadi"
        rowClass={(i) => (i.is_low ? "bg-red-50/60" : "")}
      />
        </>
      )}
      {openItem && (
        <HistoryPanel
          item={openItem}
          movements={movements}
          canWrite={canWrite}
          onClose={() => setOpenItem(null)}
          onUploaded={() => openMovements(openItem)}
        />
      )}
    </div>
  );
}

/**
 * The one place stock changes, and it opens a real dialog to do it.
 *
 * This used to expand into a strip of unlabelled inputs inside the table cell — a 16-pixel
 * number box next to a 24-pixel price box, with the reason picker deciding the sign
 * invisibly. Booking a purchase as a write-off was one mis-click away and nothing on
 * screen said which way the number was about to move. The dialog has room to label every
 * field and to show the resulting quantity before anything is saved.
 */
function MovementButton({
  item,
  busy,
  onSubmit,
}: {
  item: InventoryItem;
  busy: boolean;
  onSubmit: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={busy}
        className="min-h-9 rounded-full border border-brand-600 px-3 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-50"
      >
        ± Harakat
      </button>
      {open && (
        <MovementModal
          item={item}
          busy={busy}
          onClose={() => setOpen(false)}
          onSubmit={onSubmit}
        />
      )}
    </>
  );
}

function MovementModal({
  item,
  busy,
  onClose,
  onSubmit,
}: {
  item: InventoryItem;
  busy: boolean;
  onClose: () => void;
  onSubmit: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [reason, setReason] = useState<string>("purchase");
  const [count, setCount] = useState(1);
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sign = MOVEMENT_OPTIONS.find(([value]) => value === reason)?.[2] ?? 1;
  const delta = sign * count;
  const nextQuantity = item.quantity + delta;
  // The server refuses a movement that would take stock below zero. Saying so here means
  // the reader finds out while they can still fix the number, not after a failed save.
  const wouldGoNegative = nextQuantity < 0;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-800">Inventar harakati</h2>
            <p className="truncate text-xs text-slate-500">
              {item.name} · hozirgi qoldiq: {item.quantity} {item.unit}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✖
          </button>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (count <= 0 || wouldGoNegative) return;
            void onSubmit(async () => {
              await inventoryApi.addMovement(item.id, {
                delta,
                reason,
                unit_price: price || null,
                note: note || null,
              });
              onClose();
            });
          }}
          className="flex-1 overflow-y-auto p-5"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sabab" className="sm:col-span-2">
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              >
                {MOVEMENT_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Miqdori" hint={`O'lchov birligi: ${item.unit}`}>
              <input
                type="number"
                min={1}
                value={count}
                onChange={(e) => setCount(Number(e.target.value) || 0)}
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              />
            </Field>
            <Field label="Birlik narxi" hint="Ixtiyoriy — kirim bo'lsa narxni yozib qo'ying">
              <input
                type="number"
                min={0}
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="masalan 320000"
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              />
            </Field>
            <Field label="Izoh" className="sm:col-span-2">
              <textarea
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Nima uchun? Masalan: 2-qavat printeri uchun olindi"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>

          <div
            className={`mt-4 rounded-lg px-4 py-3 text-sm ${
              wouldGoNegative
                ? "bg-red-50 text-red-700"
                : delta > 0
                  ? "bg-emerald-50 text-emerald-800"
                  : "bg-slate-100 text-slate-700"
            }`}
          >
            {wouldGoNegative ? (
              <>
                Omborda {item.quantity} {item.unit} bor — {count} {item.unit} chiqarib
                bo'lmaydi.
              </>
            ) : (
              <>
                Saqlangach qoldiq:{" "}
                <b className="tabular-nums">
                  {item.quantity} → {nextQuantity} {item.unit}
                </b>{" "}
                <span className="tabular-nums">
                  ({delta > 0 ? "+" : ""}
                  {delta})
                </span>
              </>
            )}
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50"
            >
              Bekor qilish
            </button>
            <button
              type="submit"
              disabled={busy || count <= 0 || wouldGoNegative}
              className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Saqlanmoqda..." : "💾 Saqlash"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  note,
}: {
  active: boolean;
  onClick: () => void;
  icon: string;
  label: string;
  note?: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      // The underline sits on the button rather than on a separate indicator so the tab
      // stays legible at 400px, where the two of them wrap onto separate lines.
      className={`-mb-px flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm font-medium transition-colors ${
        active
          ? "border-brand-600 text-brand-700"
          : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700"
      }`}
    >
      <span aria-hidden>{icon}</span>
      {label}
      {note && (
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] ${
            active ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-500"
          }`}
        >
          {note}
        </span>
      )}
    </button>
  );
}

/**
 * The write-off ledger: everything struck off the register, and what it was worth.
 *
 * Deliberately not another view of the stock table. A written-off item is often no longer
 * in stock at all — sometimes the item row itself has been archived — so a list keyed on
 * current quantity would either hide it or show a misleading zero. The row here is the
 * *event*: when, what, how many, why, who, and against which request.
 */
function WriteOffRegister({
  categories,
  page,
  filters,
  onFilters,
  onError,
}: {
  categories: InventoryCategory[];
  page: WriteOffPage | null;
  filters: WriteOffFilters;
  onFilters: (next: WriteOffFilters) => void;
  onError: (message: string | null) => void;
}) {
  const rows = page?.rows ?? [];
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / WRITE_OFF_PAGE_SIZE));
  const current = Math.min(filters.page, pageCount - 1);
  const filtered = Boolean(filters.q || filters.categorySlug || filters.from || filters.to);

  // Any filter change resets to the first page. Staying on page 4 of a set that just shrank
  // to two pages shows an empty table and reads as "nothing found".
  function setFilter(patch: Partial<WriteOffFilters>) {
    onError(null);
    onFilters({ ...filters, ...patch, page: 0 });
  }

  const columns: Column<InventoryMovement>[] = [
    {
      key: "item",
      header: "Inventar",
      mobile: "title",
      cell: (m) => (
        <span className="font-medium text-slate-800">{m.item_name ?? `#${m.item_id}`}</span>
      ),
    },
    {
      key: "category",
      header: "Kategoriya",
      mobile: "meta",
      cell: (m) => (
        <>
          {m.item_category_label ?? "—"}
          {m.item_status === "archived" && (
            <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
              📦 arxivda
            </span>
          )}
        </>
      ),
    },
    {
      key: "quantity",
      header: "Miqdori",
      align: "right",
      cell: (m) => (
        <>
          <span className="font-semibold tabular-nums text-red-700">{-m.delta}</span>
          <span className="text-xs text-slate-400"> {m.item_unit ?? "dona"}</span>
        </>
      ),
    },
    {
      key: "value",
      header: "Qiymati",
      align: "right",
      cell: (m) => <span className="tabular-nums">{money(m.total_price)}</span>,
    },
    {
      key: "reason",
      header: "Sababi",
      cell: (m) => (
        <span className="text-slate-600">
          {m.note || <span className="text-slate-400">Izoh yozilmagan</span>}
          {m.request_number && (
            <a
              href={`/requests/${m.request_id}`}
              className="ml-2 whitespace-nowrap text-brand-600 hover:underline"
            >
              {m.request_number}
            </a>
          )}
        </span>
      ),
    },
    {
      key: "who",
      header: "Kim",
      cell: (m) => <span className="text-slate-600">{m.employee_name ?? "Admin"}</span>,
    },
    {
      key: "when",
      header: "Sana",
      cell: (m) => (
        <span className="whitespace-nowrap text-slate-500">{fullDateTime(m.created_at)}</span>
      ),
    },
    {
      key: "docs",
      header: "Hujjat",
      cell: (m) =>
        m.attachments.length === 0 ? (
          <span className="text-slate-300">—</span>
        ) : (
          <span className="flex flex-wrap gap-2">
            {m.attachments.map((a) => (
              <a
                key={a.id}
                href={a.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-brand-600 hover:underline"
              >
                🧾 {a.original_filename || "hujjat"}
              </a>
            ))}
          </span>
        ),
    },
  ];

  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Tile
          label={filtered ? "Tanlangan davrda" : "Jami hisobdan chiqarilgan"}
          value={page?.total_quantity ?? 0}
          tone="#d03b3b"
          icon="🗑"
          note={`${total} ta yozuv`}
        />
        <Tile label="Qiymati" value={money(page?.total_value ?? null)} small tone="#d03b3b" />
        <Tile label="Inventar turlari" value={page?.item_count ?? 0} />
        <Tile
          label="Shu oy"
          value={page?.this_month_quantity ?? 0}
          note={
            page?.this_month_value ? `qiymati: ${money(page.this_month_value)}` : undefined
          }
        />
      </div>

      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap gap-1.5">
          {WRITE_OFF_RANGES.map(([label, make]) => {
            const range = make();
            const active = filters.from === range.from && filters.to === range.to;
            return (
              <button
                key={label}
                onClick={() => setFilter(range)}
                className={`min-h-9 rounded-full border px-3 text-xs font-medium transition-colors ${
                  active
                    ? "border-brand-600 bg-brand-600 text-white"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input
            value={filters.q}
            onChange={(e) => setFilter({ q: e.target.value })}
            placeholder="Inventar nomi yoki izoh bo'yicha..."
            className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-72"
          />
          <select
            value={filters.categorySlug}
            onChange={(e) => setFilter({ categorySlug: e.target.value })}
            className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
          >
            <option value="">Barcha kategoriyalar</option>
            {categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label_uz}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            dan
            <input
              type="date"
              value={filters.from}
              onChange={(e) => setFilter({ from: e.target.value })}
              className="min-h-11 rounded-lg border border-slate-300 px-2 text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            gacha
            <input
              type="date"
              value={filters.to}
              onChange={(e) => setFilter({ to: e.target.value })}
              className="min-h-11 rounded-lg border border-slate-300 px-2 text-sm"
            />
          </label>
          {filtered && (
            <button
              onClick={() => setFilter(EMPTY_WRITE_OFF_FILTERS)}
              className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm text-slate-600 hover:bg-slate-50"
            >
              ✖️ Filtrni tozalash
            </button>
          )}
        </div>
      </div>

      <ResponsiveTable
        rows={rows}
        columns={columns}
        rowKey={(m) => m.id}
        empty={
          filtered
            ? "Bu shartlarga mos hisobdan chiqarilgan inventar topilmadi"
            : "Hali hech narsa hisobdan chiqarilmagan"
        }
      />

      {pageCount > 1 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-slate-500">
            {current * WRITE_OFF_PAGE_SIZE + 1}–
            {Math.min((current + 1) * WRITE_OFF_PAGE_SIZE, total)} / {total}
          </span>
          <div className="flex gap-2">
            <button
              disabled={current === 0}
              onClick={() => onFilters({ ...filters, page: current - 1 })}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              ⬅️ Oldingi
            </button>
            <button
              disabled={current >= pageCount - 1}
              onClick={() => onFilters({ ...filters, page: current + 1 })}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              Keyingi ➡️
            </button>
          </div>
        </div>
      )}

      <p className="mt-4 text-xs text-slate-400">
        Hisobdan chiqarish — «Ombor qoldig'i» bo'limidagi «± Harakat» tugmasi orqali
        «🗑 Hisobdan chiqarish» sababi bilan yoziladi. Har bir yozuv qaytarib bo'lmaydi;
        xato bo'lsa «✏️ Tuzatish» harakati bilan to'g'rilanadi.
      </p>
    </div>
  );
}

function HistoryPanel({
  item,
  movements,
  canWrite,
  onClose,
  onUploaded,
}: {
  item: InventoryItem;
  movements: InventoryMovement[];
  canWrite: boolean;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [uploading, setUploading] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-800">{item.name}</h2>
            <p className="text-xs text-slate-500">
              Qoldiq: {item.quantity} {item.unit} · {item.category_label}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✖
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {movements.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">Harakatlar yo'q</p>
          ) : (
            <ul className="space-y-2">
              {movements.map((m) => (
                <li
                  key={m.id}
                  className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                >
                  <span>
                    <span
                      className={`font-semibold tabular-nums ${
                        m.delta > 0 ? "text-emerald-700" : "text-red-700"
                      }`}
                    >
                      {m.delta > 0 ? "+" : ""}
                      {m.delta}
                    </span>{" "}
                    <span className="text-slate-600">{m.reason_label}</span>
                    {m.request_number && (
                      <a
                        href={`/requests/${m.request_id}`}
                        className="ml-2 text-brand-600 hover:underline"
                      >
                        {m.request_number}
                      </a>
                    )}
                    {m.note && <span className="ml-2 text-xs text-slate-400">{m.note}</span>}
                  </span>
                  <span className="text-xs text-slate-400">
                    {m.employee_name ? `${m.employee_name} · ` : ""}
                    {new Date(m.created_at).toLocaleString("uz-UZ")}
                    {m.total_price ? ` · ${money(m.total_price)}` : ""}
                  </span>
                  {m.attachments.length > 0 && (
                    <span className="w-full">
                      {m.attachments.map((a) => (
                        <a
                          key={a.id}
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="mr-2 text-xs text-brand-600 hover:underline"
                        >
                          🧾 {a.original_filename || "chek"}
                        </a>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {canWrite && (
          <footer className="border-t border-slate-200 px-5 py-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
              🧾 Chek yoki hujjat biriktirish
              <input
                type="file"
                className="hidden"
                disabled={uploading}
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setUploading(true);
                  try {
                    await inventoryApi.uploadReceipt(item.id, file);
                    onUploaded();
                  } finally {
                    setUploading(false);
                  }
                }}
              />
            </label>
            <p className="mt-1 text-xs text-slate-400">
              Ixtiyoriy — chek bo'lmasa ham inventar hisobga olinaveradi.
            </p>
          </footer>
        )}
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  note,
  tone,
  icon,
  small,
}: {
  label: string;
  value: number | string;
  note?: string;
  tone?: string;
  icon?: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div
        className={`font-bold tabular-nums ${small ? "text-base" : "text-2xl"}`}
        style={{ color: tone ?? "#2a78d6" }}
      >
        {icon && <span className="mr-1">{icon}</span>}
        {value}
      </div>
      <div className="text-xs text-slate-500">{label}</div>
      {note && <div className="mt-0.5 text-[11px] text-slate-400">{note}</div>}
    </div>
  );
}

function Field({
  label,
  hint,
  className = "",
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}
