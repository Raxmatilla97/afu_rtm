from datetime import datetime

from pydantic import BaseModel

from afu_shared.media import kind_label


class RequestCreate(BaseModel):
    category_slug: str
    description: str


class RequestAssign(BaseModel):
    """Who should work on this.

    ``assigned_to_employee_ids`` is the real field — a request can be shared between staff.
    The older single-id form is still accepted so an admin page or script written against
    the previous API keeps working; the first id in the list is the primary assignee.
    """

    assigned_to_employee_ids: list[int] = []
    assigned_to_employee_id: int | None = None
    deadline_at: datetime | None = None

    def employee_ids(self) -> list[int]:
        if self.assigned_to_employee_ids:
            # De-duplicated, order preserved: the admin's first pick stays the lead.
            return list(dict.fromkeys(self.assigned_to_employee_ids))
        return [self.assigned_to_employee_id] if self.assigned_to_employee_id else []


class RequestStatusUpdate(BaseModel):
    status: str
    note: str | None = None


class RequestComplete(BaseModel):
    completion_note: str


class RequestReturn(BaseModel):
    """Why a request is being sent back.

    Free text rather than a code, with the four common cases offered as ready-made wordings
    in the interface. What the reporter needs is a sentence they can act on — "wrong
    department" as an enum value would arrive as a shrug.
    """

    reason: str


class RequestMessageCreate(BaseModel):
    #: May be empty — a voice clip or a screenshot is a complete message on its own.
    body: str = ""
    visibility: str = "to_requester"
    #: Files already uploaded to this request that this message should own. The web client
    #: uploads first and posts second, so that the message exists only once its files do —
    #: otherwise the Telegram notification would go out describing an empty message and the
    #: files would arrive attached to nothing.
    attachment_ids: list[int] = []


class RequestAttachmentResponse(BaseModel):
    id: int
    request_id: int
    message_id: int | None = None
    kind: str
    kind_label: str
    file_path: str | None
    original_filename: str | None
    content_type: str | None
    file_size: int | None = None
    duration_seconds: int | None = None
    #: Same-origin path the browser can put straight into <img>, <video> or <audio>.
    #: None when the file only ever existed as a Telegram handle (too large to download).
    url: str | None = None
    created_at: datetime

    @classmethod
    def from_attachment(cls, a) -> "RequestAttachmentResponse":
        return cls(
            id=a.id,
            request_id=a.request_id,
            message_id=a.message_id,
            kind=a.kind,
            kind_label=kind_label(a.kind),
            file_path=a.file_path,
            original_filename=a.original_filename,
            content_type=a.content_type,
            file_size=a.file_size,
            duration_seconds=a.duration_seconds,
            url=(
                f"/api/requests/{a.request_id}/attachments/{a.id}"
                if a.file_path
                else None
            ),
            created_at=a.created_at,
        )


class RequestMessageResponse(BaseModel):
    id: int
    request_id: int
    author_employee_id: int | None
    author_user_id: int | None
    author_name: str | None = None
    visibility: str
    body: str | None
    attachments: list[RequestAttachmentResponse] = []
    created_at: datetime

    @classmethod
    def from_message(
        cls, m, *, author_name: str | None = None, attachments=None
    ) -> "RequestMessageResponse":
        """``attachments`` overrides the relationship.

        Needed straight after creating a message: reading ``m.attachments`` there would be
        a lazy load on an async session, which raises rather than quietly issuing a query.
        The caller already holds the rows it just linked, so it passes them in.
        """
        files = m.attachments if attachments is None else attachments
        return cls(
            id=m.id,
            request_id=m.request_id,
            author_employee_id=m.author_employee_id,
            author_user_id=m.author_user_id,
            author_name=author_name,
            visibility=m.visibility,
            body=m.body,
            attachments=[RequestAttachmentResponse.from_attachment(a) for a in files],
            created_at=m.created_at,
        )


class RequesterCard(BaseModel):
    """Who reported the problem, in the detail the person handling it actually needs.

    Bundled onto the request rather than fetched separately because it is never wanted on
    its own: whoever opens a request needs to know within the same glance who to call.
    """

    id: int
    full_name: str
    employee_id_number: str | None = None
    department_name: str | None = None
    phone_number: str | None = None
    telegram_username: str | None = None
    image_local_path: str | None = None

    @classmethod
    def from_employee(cls, e) -> "RequesterCard":
        return cls(
            id=e.id,
            full_name=e.full_name,
            employee_id_number=e.employee_id_number,
            department_name=e.department.name if e.department else None,
            phone_number=e.phone_number,
            telegram_username=e.telegram_username,
            image_local_path=e.image_local_path,
        )


class AssigneeCard(BaseModel):
    employee_id: int
    full_name: str
    is_primary: bool


class RequestResponse(BaseModel):
    id: int
    display_number: str
    requester_employee_id: int
    requester_name: str | None = None
    requester: RequesterCard | None = None
    #: Everyone on the job. ``assigned_to_*`` above is the primary among them and stays for
    #: the compact places — list rows, badges — where one name is all that fits.
    assignees: list[AssigneeCard] = []
    category_slug: str
    category_label: str | None = None
    description: str
    status: str
    source: str
    assigned_to_employee_id: int | None
    assigned_to_name: str | None = None
    deadline_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None
    returned_at: datetime | None = None
    return_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_request(cls, r) -> "RequestResponse":
        return cls(
            id=r.id,
            display_number=r.display_number,
            requester_employee_id=r.requester_employee_id,
            requester_name=r.requester.full_name if r.requester else None,
            requester=RequesterCard.from_employee(r.requester) if r.requester else None,
            assignees=[
                AssigneeCard(
                    employee_id=a.employee_id,
                    full_name=a.employee.full_name if a.employee else f"#{a.employee_id}",
                    is_primary=a.is_primary,
                )
                for a in r.assignees
            ],
            category_slug=r.category_slug,
            category_label=r.category.label_uz if r.category else None,
            description=r.description,
            status=r.status,
            source=r.source,
            assigned_to_employee_id=r.assigned_to_employee_id,
            assigned_to_name=r.assigned_to.full_name if r.assigned_to else None,
            deadline_at=r.deadline_at,
            completed_at=r.completed_at,
            completion_note=r.completion_note,
            returned_at=r.returned_at,
            return_reason=r.return_reason,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
