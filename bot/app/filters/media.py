"""The "this message carries a file" filter.

Written once and imported everywhere a handler accepts media, so the set of supported
kinds cannot fall out of step between the new-request flow, staff replies and completion
notes — a mismatch there would silently drop, say, round videos in one place only.
"""

from aiogram import F

#: Matches every media kind ``afu_shared.media.extract_media`` knows how to read.
HAS_MEDIA = F.photo | F.video | F.voice | F.video_note | F.audio | F.document
