from django.test import TransactionTestCase

from producers.services import next_member_code


class MemberCodeTests(TransactionTestCase):
    def test_assigns_zero_padded_codes(self):
        self.assertEqual(next_member_code(), "PROD-000001")
        self.assertEqual(next_member_code(), "PROD-000002")
