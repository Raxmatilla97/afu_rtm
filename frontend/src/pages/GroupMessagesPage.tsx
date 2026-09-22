import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { describeError } from "@/api/errors";
import { groupMessagesApi, type GroupMessageRef } from "@/api/groupMessages";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { StatusBadge } from "@/components/StatusBadge";
import type { GroupChat, GroupMessage } from "@/types";

/**
 * The kinds of message the bot puts in a group, in the order somebody scanning for clutter
 * would want them. Kept in step with `afu_shared/group_log.py`; an unknown kind still
 * appears in the list, it just does not get its own filter button.
 */
const KIND_FILTERS: ReadonlyArray<readonly [string, string]> = [
  ["", "Barchasi"],
  ["card", "🎫 Kartochkalar"],
  ["note", "💬 Izohlar"],
  ["overdue", "🔴 Muddat ogohlantirishi"],
  ["files", "📎 Fayllar"],
  ["welcome", "👋 Ulanish xabari"],
  ["notice", "📢 Bot xabari"],
];

/** How many rows one screen shows. Mirrors PAGE_SIZE on the server. */
const PAGE_SIZE = 100;

/** How many a single delete may take. Mirrors DELETE_LIMIT on the server. */
const DELETE_LIMIT = 50;

function when(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** `chat_id:message_id` — the only key a Telegram message has, and it is not a number. */
function keyOf(m: { chat_id: number; message_id: number }): string {
  return `${m.chat_id}:${m.message_id}`;
}

function refOf(key: string): GroupMessageRef {
  const [chat, message] = key.split(":");
  return { chat_id: Number(chat), message_id: Number(message) };
}

/**
 * Read a Telegram message link, or a bare message id, into the pair the API needs.
 *
 * `https://t.me/c/1234567890/456` is what "Copy Message Link" produces in a private
 * supergroup, and the number after `/c/` is the chat id with its `-100` prefix stripped —
 * so the link identifies the group as well, and the caller does not have to have picked the
 * right one. A public group's link (`t.me/name/456`) carries no id, and a bare number
 * carries neither, so both fall back to whichever chat is selected on the page.
 *
 * Returns null when there is no message id to be found at all.
 */
export function parseMessageRef(
  input: string,
  fallbackChatId: number | null,
): GroupMessageRef | null {
  const text = input.trim();
  if (!text) return null;

  const privateLink = text.match(/t\.me\/c\/(\d+)\/(?:\d+\/)?(\d+)/);
  if (privateLink) {
    return {
      chat_id: Number(`-100${privateLink[1]}`),
      message_id: Number(privateLink[2]),
    };
  }

  // A public link, or somebody who typed only the number. Either way the id is the last
  // run of digits, and the chat has to come from the picker.
  const tail = text.match(/(\d+)\s*$/);
  if (!tail || fallbackChatId === null) return null;
  return { chat_id: fallbackChatId, message_id: Number(tail[1]) };
}

/**
 * What the bot is currently showing the RTM groups, and the way to take it back down.
 *
 * The page exists because the group is the one surface nobody could edit from here. A card
 * for a request filed by mistake, a stack of "X took this on" lines under a busy job, an
 * overdue alarm for something that turned out to be fixed — all of it sat in a chat full of
 * people with no way to clear it except asking somebody with a phone.
 *
 * Deleting goes through Telegram synchronously and reports what Telegram said, rather than
 * queueing a job and claiming success. A bot that is not a group administrator cannot delete
 * anything, and that is precisely the failure an admin needs to be told about — silently
 * queueing it would leave them believing the group had been tidied.
 */
export function GroupMessagesPage() {
  const [chats, setChats] = useState<GroupChat[]>([]);
  const [messages, setMessages] = useState<GroupMessage[]>([]);
  const [chatFilter, setChatFilter] = useState<number | null>(null);
  const [kindFilter, setKindFilter] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const loadChats = useCallback(async () => {
    try {
      setChats(await groupMessagesApi.chats());
    } catch (e) {
      setError(describeError(e));
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMessages(
        await groupMessagesApi.list({
          chat_id: chatFilter ?? undefined,
          kind: kindFilter || undefined,
          q: q || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        }),
      );
      // Cleared on every refetch: a tick that survives a filter change would delete a
      // message the person can no longer see.
      setSelected([]);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [chatFilter, kindFilter, q, page]);

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const totalLive = useMemo(
    () => chats.reduce((sum, chat) => sum + chat.message_count, 0),
    [chats],
  );
  const allSelected = messages.length > 0 && selected.length === messages.length;

  function setFilter(patch: { chat?: number | null; kind?: string; q?: string }) {
    setNotice(null);
    if (patch.chat !== undefined) setChatFilter(patch.chat);
    if (patch.kind !== undefined) setKindFilter(patch.kind);
    if (patch.q !== undefined) setQ(patch.q);
    setPage(0);
  }

  function toggleRow(key: string) {
    setSelected((current) =>
      current.includes(key) ? current.filter((x) => x !== key) : [...current, key],
    );
  }

  async function remove(keys: string[]) {
    if (keys.length === 0 || busy) return;

    const chosen = messages.filter((m) => keys.includes(keyOf(m)));
    const cards = chosen.filter((m) => m.kind === "card").length;
    if (
      !window.confirm(
        `${keys.length} ta xabar RTM guruhidan o'chiriladi.\n\n` +
          (cards
            ? `Shundan ${cards} tasi murojaat kartochkasi — o'chirilsa, o'sha murojaat ` +
              "guruhda boshqa ko'rinmaydi va holati o'zgarganda ham qayta chiqmaydi. " +
              "Murojaatning o'zi saytda qoladi.\n" +
              "Kartochka ostidagi izohlar ham birga o'chiriladi — aks holda ular " +
              "«Удалённое сообщение» ostida osilib qoladi.\n\n"
            : "") +
          "Buni ortga qaytarib bo'lmaydi.",
      )
    ) {
      return;
    }

    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await send(keys.map(refOf));
    } finally {
      setBusy(false);
    }
  }

  /** The one place a delete is actually issued, so both entry points report it the same way. */
  async function send(refs: GroupMessageRef[]) {
    setNotice(null);
    setError(null);
    try {
      const result = await groupMessagesApi.remove(refs);
      const parts: string[] = [];
      if (result.deleted) parts.push(`${result.deleted} ta xabar guruhdan o'chirildi`);
      if (result.already_gone)
        parts.push(`${result.already_gone} tasi allaqachon o'chirilgan edi`);
      // Named out loud: a delete that removes five messages when one was ticked has to say
      // so, otherwise the count on screen looks like a bug.
      if (result.cascaded)
        parts.push(`kartochka ostidagi ${result.cascaded} ta izoh ham olib tashlandi`);
      setNotice(parts.join(", ") || null);
      if (result.failed.length) {
        setError(`O'chirib bo'lmadi — ${result.failed.join("; ")}`);
      }
      await Promise.all([load(), loadChats()]);
    } catch (e) {
      setError(describeError(e));
    }
  }

  /**
   * Delete something the list does not know about.
   *
   * Telegram gives a bot no way to read a group's history, so anything posted before this
   * log existed can never appear in the table above — and those are exactly the leftovers
   * an admin wants gone. A message id is all `deleteMessage` needs, though, and Telegram
   * hands one over on every message through "Copy Message Link".
   */
  async function removeByLink(input: string) {
    const ref = parseMessageRef(input, chatFilter);
    if (!ref) {
      setError(
        "Havola yoki xabar raqamini tushunib bo'lmadi. Telegramda xabarni bosib turib " +
          "«Havolani nusxalash» ni tanlang, yoki avval yuqoridan guruhni tanlab, faqat " +
          "xabar raqamini yozing.",
      );
      return;
    }
    const chat = chats.find((c) => c.chat_id === ref.chat_id);
    if (
      !window.confirm(
        `${chat?.title || `#${ref.chat_id}`} guruhidan ${ref.message_id}-raqamli xabar ` +
          "o'chiriladi.\n\nBu bot yuborgan xabar bo'lishi kerak — bot o'zga xabarlarni " +
          "faqat administrator bo'lgandagina o'chira oladi. Buni ortga qaytarib bo'lmaydi.",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await send([ref]);
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<GroupMessage>[] = [
    {
      key: "kind",
      header: "Turi",
      mobile: "title",
      cell: (m) => (
        <div className="flex items-center gap-2.5">
          <input
            type="checkbox"
            checked={selected.includes(keyOf(m))}
            onChange={() => toggleRow(keyOf(m))}
            aria-label={`${m.kind_label} xabarini tanlash`}
            className="h-4 w-4 shrink-0 accent-red-600"
          />
          <span className="font-medium text-slate-800">{m.kind_label}</span>
        </div>
      ),
    },
    {
      key: "chat",
      header: "Guruh",
      mobile: "meta",
      cell: (m) => m.chat_title || `#${m.chat_id}`,
    },
    {
      key: "preview",
      header: "Matni",
      cell: (m) => (
        <span className="block max-w-xl text-slate-600">
          {m.preview || <span className="text-slate-300">—</span>}
        </span>
      ),
    },
    {
      key: "request",
      header: "Murojaat",
      cell: (m) =>
        m.request_id ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <Link
              to={`/requests/${m.request_id}`}
              className="font-medium text-brand-700 hover:underline"
            >
              {m.request_number}
            </Link>
            {m.request_status && <StatusBadge status={m.request_status} />}
          </span>
        ) : (
          <span className="text-slate-300">—</span>
        ),
    },
    {
      key: "created",
      header: "Yuborilgan",
      cell: (m) => (
        <span className="whitespace-nowrap text-slate-500">
          {when(m.created_at)}
          {m.expires_at && (
            <span className="block text-[11px] text-slate-400">
              o'zi o'chadi: {when(m.expires_at)}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (m) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
          {m.telegram_url && (
            <a
              href={m.telegram_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-9 items-center rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
            >
              ↗ Guruhda ochish
            </a>
          )}
          <button
            onClick={() => remove([keyOf(m)])}
            disabled={busy}
            className="min-h-9 rounded-full border border-red-300 px-3 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            🗑 O'chirish
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Guruhdagi bot xabarlari"
        subtitle="Ayni damda RTM guruhlarida turgan xabarlar. Keraksizini shu yerdan o'chirasiz."
      />

      {error && <ErrorBanner message={error} />}
      {notice && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          ✅ {notice}
        </div>
      )}

      <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <div className="mb-1 font-semibold">⚠️ Nega ro'yxatda hamma xabar yo'q?</div>
        <p>
          Telegram botga guruh tarixini o'qish imkonini bermaydi — bot faqat{" "}
          <b>o'zi yuborgan paytda yozib qolgan</b> xabarlarini biladi. Xabarlarni yozib
          borish 2026-yil sentabrida qo'shildi, shuning uchun:
        </p>
        <ul className="mt-2 list-disc space-y-0.5 pl-5">
          <li>
            <b>Kartochkalar</b> — hammasi ko'rinadi, ular boshidan beri yozib kelingan.
          </li>
          <li>
            <b>Izohlar, muddat ogohlantirishlari, ulanish xabarlari</b> — faqat shu
            yangilanishdan keyin yuborilganlari. Eskilarini pastdagi{" "}
            <b>«Havola orqali o'chirish»</b> orqali olib tashlaysiz.
          </li>
          <li>
            📎 Fayllar 10 daqiqada bot tomonidan o'zi o'chadi — ro'yxatda faqat hali
            turganlari bo'ladi.
          </li>
        </ul>
        <p className="mt-2">
          O'chirish uchun bot guruhda <b>administrator</b> bo'lishi va «Xabarlarni
          o'chirish» huquqiga ega bo'lishi shart — aks holda Telegram rad etadi va sabab
          shu yerda yoziladi.
        </p>
      </div>

      {/* Chat picker. Tiles rather than a select: there are rarely more than three groups,
          and the count is the number that makes somebody open one. */}
      <div className="mb-4 flex flex-wrap gap-2">
        <ChatTile
          active={chatFilter === null}
          onClick={() => setFilter({ chat: null })}
          title="Barcha guruhlar"
          count={totalLive}
        />
        {chats.map((chat) => (
          <ChatTile
            key={chat.chat_id}
            active={chatFilter === chat.chat_id}
            onClick={() => setFilter({ chat: chat.chat_id })}
            title={chat.title || `#${chat.chat_id}`}
            count={chat.message_count}
            inactive={!chat.is_active}
          />
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={q}
          onChange={(e) => setFilter({ q: e.target.value })}
          placeholder="Matn bo'yicha qidirish..."
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-72"
        />
        <select
          value={kindFilter}
          onChange={(e) => setFilter({ kind: e.target.value })}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          {KIND_FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {messages.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={() =>
                setSelected(allSelected ? [] : messages.slice(0, DELETE_LIMIT).map(keyOf))
              }
              className="h-4 w-4 accent-red-600"
            />
            {allSelected ? "Tanlovni bekor qilish" : `Ro'yxatdagilarni tanlash`}
          </label>
          <span className="text-xs text-slate-400">
            {selected.length > 0
              ? `${selected.length} ta tanlandi`
              : `${messages.length} ta xabar ko'rsatilmoqda`}
            {messages.length > DELETE_LIMIT &&
              ` · bir vaqtda ${DELETE_LIMIT} tagacha o'chiriladi`}
          </span>
          {selected.length > 0 && (
            <button
              onClick={() => remove(selected)}
              disabled={busy}
              className="ml-auto min-h-11 rounded-lg bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {busy ? "O'chirilmoqda..." : `🗑 Tanlanganlarni o'chirish (${selected.length})`}
            </button>
          )}
        </div>
      )}

      {loading ? (
        <div className="text-slate-400">Yuklanmoqda...</div>
      ) : (
        <ResponsiveTable
          rows={messages}
          columns={columns}
          rowKey={keyOf}
          empty="Bu shartlarga mos bot xabari topilmadi"
          rowClass={(m) => (selected.includes(keyOf(m)) ? "bg-red-50/60" : "")}
        />
      )}

      {(page > 0 || messages.length === PAGE_SIZE) && (
        <div className="mt-4 flex justify-end gap-2">
          <button
            disabled={page === 0 || busy}
            onClick={() => setPage((p) => p - 1)}
            className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            ⬅️ Oldingi
          </button>
          <button
            disabled={messages.length < PAGE_SIZE || busy}
            onClick={() => setPage((p) => p + 1)}
            className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            Keyingi ➡️
          </button>
        </div>
      )}

      <ManualDelete
        busy={busy}
        chats={chats}
        chatFilter={chatFilter}
        onChat={(id) => setFilter({ chat: id })}
        onSubmit={removeByLink}
      />
    </div>
  );
}

/**
 * The escape hatch for anything the list cannot know about.
 *
 * Which is a real category, not an edge case: Telegram offers bots no way to read a group's
 * history, so every message the bot sent before it started keeping a log is invisible here
 * for ever. Deleting one needs nothing but its id, and Telegram gives that away on every
 * message through "Copy Message Link" — so the fix is a box to paste it into.
 */
function ManualDelete({
  busy,
  chats,
  chatFilter,
  onChat,
  onSubmit,
}: {
  busy: boolean;
  chats: GroupChat[];
  chatFilter: number | null;
  onChat: (id: number | null) => void;
  onSubmit: (input: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (busy || !value.trim()) return;
        await onSubmit(value);
        setValue("");
      }}
      className="mt-8 rounded-xl border border-slate-200 bg-white p-5"
    >
      <div className="mb-1 font-semibold text-slate-800">
        🔗 Ro'yxatda yo'q xabarni havola orqali o'chirish
      </div>
      <p className="mb-3 text-sm text-slate-500">
        Telegramda kerakli bot xabarini bosib turing → <b>«Havolani nusxalash»</b> →
        shu yerga qo'ying. Eski izohlar, muddat ogohlantirishlari va boshqa qolgan
        xabarlarni shu yo'l bilan tozalaysiz. Havola o'rniga faqat xabar raqamini ham
        yozsa bo'ladi — u holda guruhni yonidagi ro'yxatdan tanlang.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="https://t.me/c/1234567890/456"
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-96"
        />
        <select
          value={chatFilter ?? ""}
          onChange={(e) => onChat(e.target.value ? Number(e.target.value) : null)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="">Guruhni tanlang</option>
          {chats.map((chat) => (
            <option key={chat.chat_id} value={chat.chat_id}>
              {chat.title || `#${chat.chat_id}`}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="min-h-11 rounded-lg bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          🗑 O'chirish
        </button>
      </div>

      <p className="mt-2 text-xs text-slate-400">
        Faqat bot yuborgan xabarlar uchun ishlatiladi. Bot guruhda administrator bo'lsa,
        Telegram texnik jihatdan boshqa a'zolarning xabarini ham o'chirishga ruxsat beradi —
        shuning uchun havolani qo'yishdan oldin tekshiring.
      </p>
    </form>
  );
}

function ChatTile({
  active,
  onClick,
  title,
  count,
  inactive,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  count: number;
  inactive?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`flex min-h-11 items-center gap-2 rounded-lg border px-4 text-sm transition-colors ${
        active
          ? "border-brand-600 bg-brand-600 text-white"
          : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
      }`}
    >
      <span className="font-medium">{title}</span>
      {/* A disconnected group still holds everything the bot posted before it left, which is
          exactly why it stays in this list rather than being hidden. */}
      {inactive && (
        <span className={`text-[11px] ${active ? "text-white/70" : "text-slate-400"}`}>
          uzilgan
        </span>
      )}
      <span
        className={`rounded-full px-2 py-0.5 text-xs tabular-nums ${
          active ? "bg-white/20" : "bg-slate-100 text-slate-500"
        }`}
      >
        {count}
      </span>
    </button>
  );
}
