"""Tests for afu_shared/people.py — how a person is named and labelled on a card.

Both rules here are load-bearing in the RTM group, which is the one surface where a
mistake is seen by the whole team at once:

* ``short_name`` decides what every card, note and warning calls somebody. It is a
  rendering choice, so the interesting cases are the shapes of name it must not mangle —
  a mononym, a double surname, stray whitespace from HEMIS.
* ``role_of`` decides whether a request is announced as a directive at all, and under
  which word. The rule is deliberately asymmetric: an Admin who is not a Boshliq gets
  nothing, and an Admin who *is* one outranks the Boshliq label.
"""

from afu_shared.models import Employee
from afu_shared.people import ROLE_ADMIN, ROLE_BOSHLIQ, role_label, role_of, short_name


def _employee(*, supervisor=False, admin=False, eligible=True) -> Employee:
    return Employee(
        employee_id_number="1",
        full_name="Fayziyev Raxmatilla Baxtiyor o'g'li",
        is_supervisor=supervisor,
        is_admin=admin,
        is_active=eligible,
        is_blocked=False,
        access_revoked=False,
        # is_eligible also demands the active HEMIS status code.
        employee_status_code="11" if eligible else "13",
    )


class TestShortName:
    def test_patronymic_is_dropped(self):
        assert short_name("Fayziyev Raxmatilla Baxtiyor o'g'li") == "Fayziyev Raxmatilla"

    def test_two_part_name_is_untouched(self):
        assert short_name("Fayziyev Raxmatilla") == "Fayziyev Raxmatilla"

    def test_mononym_survives(self):
        # Guessing here would turn a single-word name into an empty card line.
        assert short_name("Raxmatilla") == "Raxmatilla"

    def test_stray_whitespace_does_not_produce_empty_parts(self):
        assert short_name("  Fayziyev   Raxmatilla  Baxtiyor ") == "Fayziyev Raxmatilla"

    def test_missing_name_falls_back_rather_than_printing_none(self):
        assert short_name(None) == "—"
        assert short_name("", default="RTM xodimi") == "RTM xodimi"


class TestRoleOf:
    def test_boshliq_files_a_directive(self):
        assert role_of(_employee(supervisor=True)) == ROLE_BOSHLIQ

    def test_admin_alone_does_not(self):
        # The whole point of the split: Admin runs the panel, Boshliq commits RTM to a
        # deadline. An Admin without the Boshliq flag files an ordinary request.
        assert role_of(_employee(admin=True)) is None

    def test_admin_who_is_also_boshliq_is_labelled_admin(self):
        assert role_of(_employee(supervisor=True, admin=True)) == ROLE_ADMIN

    def test_ordinary_employee_gets_nothing(self):
        assert role_of(_employee()) is None

    def test_none_is_safe(self):
        assert role_of(None) is None

    def test_a_departed_boshliq_loses_it(self):
        # can_file_managed_request carries the eligibility check, so a ban cannot be
        # half-applied: the flag stays in the database, the power does not.
        assert role_of(_employee(supervisor=True, eligible=False)) is None


class TestRoleLabel:
    def test_labels_are_the_words_the_group_card_prints(self):
        assert role_label(ROLE_ADMIN) == "ADMIN"
        assert role_label(ROLE_BOSHLIQ) == "BOSHLIQ"

    def test_no_role_means_no_label(self):
        assert role_label(None) is None
