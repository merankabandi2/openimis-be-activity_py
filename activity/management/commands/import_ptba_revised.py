import logging
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from activity.models import (
    PTBA, PTBAStatus, Composante, SousComposante, Activite,
    SousActivite, FundingSource, SousActiviteFunding, RevisionStatus,
)

logger = logging.getLogger(__name__)

# Column indices for the 21-column PTBA 2025-2026 revise format (0-based)
COL_COMPOSANTE = 0
COL_SC_CODE = 1
COL_SC_NAME = 2
COL_CATEGORY = 3
COL_ACT_CODE = 4
COL_ACT_NAME = 5
COL_SA_NAME = 6
COL_UNITE = 7
COL_QTE_INITIALE = 8
COL_QTE_REVISEE = 9
COL_COUT_UNITAIRE_INITIALE = 10
COL_COUT_UNITAIRE_REVISEE = 11
COL_BUDGET_INITIALE = 12
COL_BUDGET_REVISEE = 13
COL_D94400_INITIALE = 14
COL_D94400_REVISEE = 15
COL_E33370_INITIALE = 16
COL_E33370_REVISEE = 17
COL_ECART = 18
COL_STATUT = 19
COL_COMMENTAIRE = 20

# Mapping from Excel statut text to RevisionStatus values
STATUT_MAPPING = {
    'revise': RevisionStatus.REVISE,
    'reviser': RevisionStatus.REVISE,
    'ajoute': RevisionStatus.AJOUTE,
    'ajoutee': RevisionStatus.AJOUTE,
    'abandonne': RevisionStatus.ABANDONNE,
    'abandonner': RevisionStatus.ABANDONNE,
    'initial': RevisionStatus.INITIAL,
}


def safe_decimal(value, default=Decimal('0')):
    """Convert a cell value to Decimal, returning default on failure."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def safe_str(value):
    """Convert a cell value to string, returning empty string for None."""
    if value is None:
        return ''
    return str(value).strip()


def parse_revision_status(value):
    """Map a statut string from Excel to a RevisionStatus value."""
    if value is None:
        return RevisionStatus.INITIAL
    text = str(value).strip().lower()
    # Remove common French accents for matching. Only covers e-acute and
    # e-grave which are sufficient for the known statut values (revise,
    # ajoute, abandonne). Other Unicode accents are not handled.
    text = text.replace('\xe9', 'e').replace('\xe8', 'e')
    for key, status in STATUT_MAPPING.items():
        if key in text:
            return status
    return RevisionStatus.INITIAL


class Command(BaseCommand):
    help = (
        'Import a PTBA from the 21-column PTBA 2025-2026 revise Excel format. '
        'Rows 1-3 = headers, Row 4+ = data. '
        'Usage: python manage.py import_ptba_revised <excel_file> '
        '--ptba-code PTBA-2025-2026'
    )

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the PTBA Excel file')
        parser.add_argument(
            '--ptba-code', type=str, required=True,
            help='Code for the PTBA (e.g., PTBA-2025-2026). Creates if not exists.',
        )
        parser.add_argument(
            '--ptba-name', type=str, default=None,
            help='Name for the PTBA (used only when creating a new PTBA).',
        )
        parser.add_argument(
            '--fiscal-year-start', type=str, default=None,
            help='Fiscal year start date (YYYY-MM-DD). Used only when creating.',
        )
        parser.add_argument(
            '--fiscal-year-end', type=str, default=None,
            help='Fiscal year end date (YYYY-MM-DD). Used only when creating.',
        )
        parser.add_argument(
            '--sheet', type=str, default=None,
            help='Sheet name to read. Defaults to the active sheet.',
        )
        parser.add_argument(
            '--data-start-row', type=int, default=4,
            help='First data row (1-based). Default: 4 (rows 1-3 = headers).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Parse and report without writing to the database.',
        )

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError(
                "openpyxl is required. Install with: pip install openpyxl"
            )

        excel_file = options['excel_file']
        ptba_code = options['ptba_code']
        dry_run = options['dry_run']
        data_start_row = options['data_start_row']

        self.stdout.write(f"Loading Excel file: {excel_file}")

        try:
            wb = openpyxl.load_workbook(excel_file, data_only=True)
        except Exception as e:
            raise CommandError(f"Failed to open Excel file: {e}")

        if options['sheet']:
            if options['sheet'] not in wb.sheetnames:
                raise CommandError(
                    f"Sheet '{options['sheet']}' not found. "
                    f"Available: {wb.sheetnames}"
                )
            ws = wb[options['sheet']]
        else:
            ws = wb.active

        self.stdout.write(f"Using sheet: {ws.title}")
        self.stdout.write(
            f"Total rows: {ws.max_row}, Total columns: {ws.max_column}"
        )

        # Get or create PTBA
        ptba = PTBA.objects.filter(code=ptba_code).first()
        if not ptba:
            ptba_name = options.get('ptba_name') or ptba_code
            fiscal_start = options.get('fiscal_year_start') or '2025-07-01'
            fiscal_end = options.get('fiscal_year_end') or '2026-06-30'
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would create PTBA: {ptba_code} ({ptba_name})"
                )
            else:
                ptba = PTBA.objects.create(
                    code=ptba_code,
                    name=ptba_name,
                    fiscal_year_start=fiscal_start,
                    fiscal_year_end=fiscal_end,
                    status=PTBAStatus.DRAFT,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Created PTBA: {ptba}")
                )
        else:
            self.stdout.write(f"Using existing PTBA: {ptba}")

        if dry_run and not ptba:
            self.stdout.write(
                "[DRY RUN] Cannot proceed without PTBA object. Exiting."
            )
            return

        # Ensure funding sources exist for IDA D94400 and IDA E33370
        fs_d94400 = None
        fs_e33370 = None
        if not dry_run:
            fs_d94400, _ = FundingSource.objects.get_or_create(
                code='D94400',
                defaults={'name': 'IDA D94400', 'is_active': True},
            )
            fs_e33370, _ = FundingSource.objects.get_or_create(
                code='E33370',
                defaults={'name': 'IDA E33370', 'is_active': True},
            )

        # Parse rows
        stats = {
            'composantes': 0,
            'sous_composantes': 0,
            'activites': 0,
            'sous_activites': 0,
            'funding_allocations': 0,
            'total_budget_initial': Decimal('0'),
            'total_budget_revised': Decimal('0'),
            'rows_processed': 0,
            'rows_skipped': 0,
        }

        current_composante = None
        current_sous_composante = None
        current_activite = None
        sort_order_composante = 0
        sort_order_sous_composante = 0
        sort_order_activite = 0
        sort_order_sous_activite = 0

        num_cols = max(21, ws.max_column or 21)

        with transaction.atomic():
            for row_num in range(data_start_row, ws.max_row + 1):
                row = [
                    ws.cell(row=row_num, column=c + 1).value
                    for c in range(num_cols)
                ]

                # Skip completely empty rows
                if all(v is None for v in row[:7]):
                    stats['rows_skipped'] += 1
                    continue

                # Composante (merged cell, only appears on its own row)
                composante_text = safe_str(row[COL_COMPOSANTE])
                if composante_text and not safe_str(row[COL_ACT_NAME]):
                    # This is a composante header row
                    # Extract code from the text if possible
                    # Format: "Composante 1: Description" or just the name
                    comp_code = composante_text[:20]
                    comp_name = composante_text
                    # Try to extract a numeric code
                    parts = composante_text.split(':')
                    if len(parts) >= 2:
                        code_part = parts[0].strip()
                        # Extract trailing digits
                        digits = ''.join(
                            c for c in code_part if c.isdigit()
                        )
                        if digits:
                            comp_code = digits
                            comp_name = composante_text

                    if dry_run:
                        self.stdout.write(
                            f"  [DRY RUN] Composante: {comp_code} - "
                            f"{comp_name[:80]}"
                        )
                    else:
                        sort_order_composante += 1
                        current_composante, created = (
                            Composante.objects.update_or_create(
                                ptba=ptba, code=comp_code,
                                defaults={
                                    'name': comp_name,
                                    'sort_order': sort_order_composante,
                                },
                            )
                        )
                        if created:
                            stats['composantes'] += 1
                    sort_order_sous_composante = 0
                    stats['rows_processed'] += 1
                    continue

                # SousComposante
                sc_code_raw = safe_str(row[COL_SC_CODE])
                sc_name = safe_str(row[COL_SC_NAME])
                # SC code column sometimes contains full name — extract numeric code
                sc_code = sc_code_raw
                if sc_code_raw and len(sc_code_raw) > 20:
                    # Try extracting "X.Y" pattern from text like "Sous-composante 3.1 : ..."
                    import re
                    m = re.search(r'(\d+\.?\d*)', sc_code_raw)
                    sc_code = m.group(1) if m else sc_code_raw[:20]
                    if not sc_name:
                        sc_name = sc_code_raw
                if not sc_name and sc_code_raw:
                    sc_name = sc_code_raw
                if sc_code and sc_name and current_composante:
                    if dry_run:
                        self.stdout.write(
                            f"    [DRY RUN] SousComposante: {sc_code} - "
                            f"{sc_name[:80]}"
                        )
                    else:
                        sort_order_sous_composante += 1
                        current_sous_composante, created = (
                            SousComposante.objects.update_or_create(
                                composante=current_composante, code=sc_code,
                                defaults={
                                    'name': sc_name,
                                    'sort_order': sort_order_sous_composante,
                                },
                            )
                        )
                        if created:
                            stats['sous_composantes'] += 1
                    sort_order_activite = 0

                # Activite
                act_code = safe_str(row[COL_ACT_CODE])
                act_name = safe_str(row[COL_ACT_NAME])
                if act_name and current_sous_composante:
                    revision_status = parse_revision_status(row[COL_STATUT])
                    revision_comment = safe_str(row[COL_COMMENTAIRE])

                    if dry_run:
                        self.stdout.write(
                            f"      [DRY RUN] Activite: {act_code} - "
                            f"{act_name[:60]} [{revision_status}]"
                        )
                    else:
                        sort_order_activite += 1
                        activite_lookup = {
                            'sous_composante': current_sous_composante,
                        }
                        if act_code:
                            activite_lookup['code'] = act_code
                        else:
                            activite_lookup['name'] = act_name
                        current_activite, created = (
                            Activite.objects.update_or_create(
                                **activite_lookup,
                                defaults={
                                    'code': act_code,
                                    'name': act_name,
                                    'sort_order': sort_order_activite,
                                    'revision_status': revision_status,
                                    'revision_comment': revision_comment,
                                },
                            )
                        )
                        if created:
                            stats['activites'] += 1
                    sort_order_sous_activite = 0

                # SousActivite
                sa_name = safe_str(row[COL_SA_NAME])
                if sa_name and current_activite:
                    category = safe_str(row[COL_CATEGORY])
                    unit = safe_str(row[COL_UNITE])
                    qty_initial = safe_decimal(row[COL_QTE_INITIALE])
                    qty_revised = safe_decimal(row[COL_QTE_REVISEE], default=None)
                    uc_initial = safe_decimal(row[COL_COUT_UNITAIRE_INITIALE])
                    uc_revised = safe_decimal(row[COL_COUT_UNITAIRE_REVISEE], default=None)
                    budget_initial = safe_decimal(row[COL_BUDGET_INITIALE])
                    budget_revised = safe_decimal(row[COL_BUDGET_REVISEE], default=None)

                    revision_status = parse_revision_status(row[COL_STATUT])
                    revision_comment = safe_str(row[COL_COMMENTAIRE])

                    # Use revised values as the "current" if present,
                    # otherwise fall back to initial.
                    # Use `is not None` instead of truthiness to avoid
                    # treating Decimal('0') as missing.
                    effective_qty = qty_revised if qty_revised is not None else qty_initial
                    effective_uc = uc_revised if uc_revised is not None else uc_initial
                    effective_budget = (
                        budget_revised if budget_revised is not None else budget_initial
                    )

                    if not dry_run:
                        sort_order_sous_activite += 1
                        # NOTE: Lookup by name may fail with MultipleObjectsReturned
                        # if duplicate sous-activite names exist under the same
                        # activite. The revised PTBA format does not include
                        # sous-activite codes, so name-based matching is the
                        # best option.
                        sa_lookup = {'activite': current_activite}
                        sa_lookup['name'] = sa_name

                        sa_defaults = {
                            'name': sa_name,
                            'expense_category': category,
                            'unit': unit,
                            'quantity_total': effective_qty,
                            'unit_cost': effective_uc,
                            'budget_total': effective_budget,
                            'quantity_initial': qty_initial,
                            'quantity_revised': qty_revised,
                            'unit_cost_initial': uc_initial,
                            'unit_cost_revised': uc_revised,
                            'budget_initial': budget_initial,
                            'budget_revised': budget_revised,
                            'revision_status': revision_status,
                            'revision_comment': revision_comment,
                            'sort_order': sort_order_sous_activite,
                        }
                        try:
                            sa, created = SousActivite.objects.update_or_create(
                                **sa_lookup,
                                defaults=sa_defaults,
                            )
                        except SousActivite.MultipleObjectsReturned:
                            sa = SousActivite.objects.filter(**sa_lookup).first()
                            for k, v in sa_defaults.items():
                                setattr(sa, k, v)
                            sa.save()
                            created = False
                        if created:
                            stats['sous_activites'] += 1
                        stats['total_budget_initial'] += budget_initial
                        stats['total_budget_revised'] += (
                            budget_revised if budget_revised is not None
                            else budget_initial
                        )

                        # Funding allocations: IDA D94400
                        d94400_init = safe_decimal(row[COL_D94400_INITIALE])
                        d94400_rev = safe_decimal(row[COL_D94400_REVISEE], default=None)
                        effective_d94400 = (
                            d94400_rev if d94400_rev is not None else d94400_init
                        )
                        if effective_d94400 and effective_d94400 > 0 and fs_d94400:
                            SousActiviteFunding.objects.update_or_create(
                                sous_activite=sa,
                                funding_source=fs_d94400,
                                defaults={
                                    'amount': effective_d94400,
                                    'amount_initial': d94400_init,
                                    'amount_revised': d94400_rev,
                                },
                            )
                            stats['funding_allocations'] += 1

                        # Funding allocations: IDA E33370
                        e33370_init = safe_decimal(row[COL_E33370_INITIALE])
                        e33370_rev = safe_decimal(row[COL_E33370_REVISEE], default=None)
                        effective_e33370 = (
                            e33370_rev if e33370_rev is not None else e33370_init
                        )
                        if effective_e33370 and effective_e33370 > 0 and fs_e33370:
                            SousActiviteFunding.objects.update_or_create(
                                sous_activite=sa,
                                funding_source=fs_e33370,
                                defaults={
                                    'amount': effective_e33370,
                                    'amount_initial': e33370_init,
                                    'amount_revised': e33370_rev,
                                },
                            )
                            stats['funding_allocations'] += 1
                    else:
                        stats['sous_activites'] += 1
                        stats['total_budget_initial'] += safe_decimal(
                            row[COL_BUDGET_INITIALE]
                        )
                        stats['total_budget_revised'] += safe_decimal(
                            row[COL_BUDGET_REVISEE]
                        )

                stats['rows_processed'] += 1

        # Report
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import Summary:"))
        self.stdout.write(f"  Rows processed: {stats['rows_processed']}")
        self.stdout.write(f"  Rows skipped (empty): {stats['rows_skipped']}")
        self.stdout.write(f"  Composantes created: {stats['composantes']}")
        self.stdout.write(
            f"  Sous-Composantes created: {stats['sous_composantes']}"
        )
        self.stdout.write(f"  Activites created: {stats['activites']}")
        self.stdout.write(
            f"  Sous-Activites created: {stats['sous_activites']}"
        )
        self.stdout.write(
            f"  Funding allocations: {stats['funding_allocations']}"
        )
        self.stdout.write(
            f"  Total budget (initial): "
            f"{stats['total_budget_initial']:,.2f} BIF"
        )
        self.stdout.write(
            f"  Total budget (revised): "
            f"{stats['total_budget_revised']:,.2f} BIF"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  [DRY RUN] No changes were committed."
            ))
