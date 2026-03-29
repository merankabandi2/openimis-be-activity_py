from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from django.test import TestCase

from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite,
    FundingSource, SousActiviteFunding, RevisionStatus,
)
from activity.management.commands.import_ptba_revised import (
    safe_decimal, safe_str, parse_revision_status,
)


class SafeDecimalTest(TestCase):
    def test_none_returns_default(self):
        self.assertEqual(safe_decimal(None), Decimal('0'))

    def test_valid_number(self):
        self.assertEqual(safe_decimal(1500000), Decimal('1500000'))

    def test_valid_string(self):
        self.assertEqual(safe_decimal('250000.50'), Decimal('250000.50'))

    def test_invalid_returns_default(self):
        self.assertEqual(safe_decimal('N/A'), Decimal('0'))
        self.assertEqual(safe_decimal(''), Decimal('0'))

    def test_custom_default(self):
        self.assertEqual(
            safe_decimal(None, Decimal('-1')), Decimal('-1')
        )


class SafeStrTest(TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(safe_str(None), '')

    def test_strips_whitespace(self):
        self.assertEqual(safe_str('  hello  '), 'hello')

    def test_number_to_string(self):
        self.assertEqual(safe_str(42), '42')


class ParseRevisionStatusTest(TestCase):
    def test_none_returns_initial(self):
        self.assertEqual(parse_revision_status(None), RevisionStatus.INITIAL)

    def test_revise(self):
        self.assertEqual(
            parse_revision_status('Revise'), RevisionStatus.REVISE
        )

    def test_ajoute(self):
        self.assertEqual(
            parse_revision_status('Ajoute'), RevisionStatus.AJOUTE
        )
        self.assertEqual(
            parse_revision_status('Ajoutee'), RevisionStatus.AJOUTE
        )

    def test_abandonne(self):
        self.assertEqual(
            parse_revision_status('Abandonne'), RevisionStatus.ABANDONNE
        )

    def test_unknown_returns_initial(self):
        self.assertEqual(
            parse_revision_status('Unknown'), RevisionStatus.INITIAL
        )

    def test_accented_revise(self):
        self.assertEqual(
            parse_revision_status('R\xe9vis\xe9'), RevisionStatus.REVISE
        )
