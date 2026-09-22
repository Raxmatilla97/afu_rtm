import { api } from "@/api/client";
import type { GroupChat, GroupMessage, GroupMessageDeleteResult } from "@/types";

/** One message, identified the only way Telegram can identify one. */
export interface GroupMessageRef {
  chat_id: number;
  message_id: number;
}

// POST for the delete, never DELETE: the reverse proxy forwards GET, POST and HEAD only.
export const groupMessagesApi = {
  chats: () => api.get<GroupChat[]>("/api/group-messages/chats"),
  list: (opts?: {
    chat_id?: number;
    kind?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.chat_id !== undefined) params.set("chat_id", String(opts.chat_id));
    if (opts?.kind) params.set("kind", opts.kind);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.offset) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return api.get<GroupMessage[]>(`/api/group-messages${qs ? `?${qs}` : ""}`);
  },
  remove: (messages: GroupMessageRef[]) =>
    api.post<GroupMessageDeleteResult>("/api/group-messages/delete", { messages }),
};
