import { ApiError } from "@/api/client";

/**
 * A message a user can act on, from whatever the request threw.
 *
 * Exists because "nothing happened" is the worst possible failure mode: a button that
 * silently does nothing looks like a button that was never wired up, and sends everyone
 * looking in the wrong place. Every status that has a specific cause gets named here.
 */
export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.status) {
      case 401:
        return "Sessiya tugagan. Iltimos, qaytadan kiring.";
      case 403:
        return e.message || "Bu amal uchun sizda ruxsat yo'q.";
      case 404:
        return "Topilmadi.";
      case 405:
        // Almost always the WAF in front of the app refusing a method rather than the
        // application refusing the action — worth naming, because the fix is in the
        // proxy configuration and nowhere in the interface.
        return "Server bu so'rovni qabul qilmadi (405). RTM bilan bog'laning.";
      case 413:
        return "Fayl hajmi juda katta.";
      default:
        return `Xatolik (${e.status}): ${e.message}`;
    }
  }
  if (e instanceof Error) return e.message;
  return "Noma'lum xatolik yuz berdi.";
}
