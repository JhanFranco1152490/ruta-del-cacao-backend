from django.test import TransactionTestCase

from apps.producers.services import next_member_code


class MemberCodeTests(TransactionTestCase):
    def test_assigns_zero_padded_codes(self):
        first_code = next_member_code()
        second_code = next_member_code()

        self.assertRegex(first_code, r"^PROD-\d{6}$")
        self.assertEqual(
            int(second_code.removeprefix("PROD-")), int(first_code.removeprefix("PROD-")) + 1
        )
