import logging
import datetime
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from activity.models import PTBA, Activite, SousActivite, SousActiviteSource, WeeklyPlanEntry

logger = logging.getLogger(__name__)

# Column indices for the weekly plan format (0-based)
COL_ACT_CODE = 0
COL_ACT_NAME = 1
COL_SA_NAME = 2
COL_ECHEANCE_DEBUT = 3
COL_ECHEANCE_FIN = 4
COL_RESPONSABLE = 5
COL_INTERVENANTS = 6
COL_WEEK_DATA_START = 7  # Alternating: Etat de lieu, Planification


def safe_str(value):
    """Convert a cell value to string, returning empty string for None."""
    if value is None:
        return ''
    return str(value).strip()


def parse_date(value):
    """Parse a date from an Excel cell. Returns date or None."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def get_monday_of_week(dt):
    """Return the Monday of the week containing dt."""
    return dt - datetime.timedelta(days=dt.weekday())


def get_friday_of_week(dt):
    """Return the Friday of the week containing dt."""
    monday = get_monday_of_week(dt)
    return monday + datetime.timedelta(days=4)


class Command(BaseCommand):
    help = (
        'Import a weekly operational plan (Planification Hebdo) from Excel. '
        'Matches sous-activites by activity code and name to the existing PTBA hierarchy. '
        'Usage: python manage.py import_weekly_plan <excel_file> '
        '--ptba-code PTBA-2025-2026'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'excel_file', type=str, help='Path to the weekly plan Excel file',
        )
        parser.add_argument(
            '--ptba-code', type=str, required=True,
            help='Code of the PTBA to match against.',
        )
        parser.add_argument(
            '--sheet', type=str, default=None,
            help='Sheet name to read. Defaults to the active sheet.',
        )
        parser.add_argument(
            '--data-start-row', type=int, default=3,
            help='First data row (1-based). Default: 3.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Parse and report without writing to the database.',
        )

    def _parse_week_headers(self, ws, header_row):
        """
        Parse the header row to extract week date pairs.

        Each pair of columns after COL_WEEK_DATA_START represents:
        - Even offset (0, 2, 4...): Etat de lieu
        - Odd offset (1, 3, 5...): Planification

        Returns list of (col_etat, col_plan, week_date) tuples.
        """
        weeks = []
        col = COL_WEEK_DATA_START + 1  # 1-based
        while col <= (ws.max_column or 0):
            header_val = ws.cell(row=header_row, column=col).value
            if header_val is None:
                col += 2
                continue

            # Try to extract date from header text
            header_text = safe_str(header_val)
            week_date = None

            # Look for date patterns in header
            # Common: "Etat de lieu au 24/03/2026"
            # or "Planification du 24-28/03/2026"
            date_match = re.search(
                r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', header_text,
            )
            if date_match:
                try:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3))
                    week_date = datetime.date(year, month, day)
                except (ValueError, OverflowError):
                    pass

            if week_date:
                monday = get_monday_of_week(week_date)
                friday = get_friday_of_week(week_date)
                weeks.append({
                    'col_etat': col,
                    'col_plan': col + 1,
                    'week_start': monday,
                    'week_end': friday,
                })

            col += 2

        return weeks

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

        # Validate PTBA exists
        ptba = PTBA.objects.filter(code=ptba_code).first()
        if not ptba:
            raise CommandError(
                f"PTBA with code '{ptba_code}' not found. "
                f"Import the PTBA first using import_ptba_revised."
            )
        self.stdout.write(f"Using PTBA: {ptba}")

        # Sous-activites of this PTBA by (activity code, name). The same name
        # may appear under several activities, so the row's activity code is
        # part of the key. A row without an activity code matches by name
        # only when that name is unique in the PTBA.
        sa_by_key = {}
        sa_by_name = {}
        for sa in SousActivite.objects.filter(
            activite__sous_composante__composante__ptba=ptba
        ).select_related('activite'):
            name_key = sa.name.strip().lower()
            sa_by_key[((sa.activite.code or '').strip(), name_key)] = sa
            sa_by_name.setdefault(name_key, []).append(sa)

        # Build lookup of activites by code for this PTBA (for unmatched SA creation)
        act_by_code = {}
        for act in Activite.objects.filter(
            sous_composante__composante__ptba=ptba
        ):
            if act.code:
                act_by_code[act.code.strip()] = act

        self.stdout.write(
            f"Found {len(sa_by_key)} sous-activites in PTBA"
        )
        self.stdout.write(
            f"Found {len(act_by_code)} activites by code"
        )

        # Parse week headers from header rows
        # Try rows 1 and 2 for date headers
        weeks = self._parse_week_headers(ws, 1)
        if not weeks:
            weeks = self._parse_week_headers(ws, 2)
        if not weeks:
            weeks = self._parse_week_headers(ws, data_start_row - 1)

        self.stdout.write(f"Found {len(weeks)} week columns")
        for w in weeks:
            self.stdout.write(
                f"  Week: {w['week_start']} - {w['week_end']}"
            )

        stats = {
            'matched': 0,
            'unmatched': 0,
            'created_as_weekly': 0,
            'entries_created': 0,
            'dates_updated': 0,
            'rows_processed': 0,
            'rows_skipped': 0,
        }
        current_act_code = None

        num_cols = ws.max_column or 7

        with transaction.atomic():
            for row_num in range(data_start_row, ws.max_row + 1):
                row = [
                    ws.cell(row=row_num, column=c + 1).value
                    for c in range(num_cols)
                ]

                # Skip empty rows
                if all(v is None for v in row[:7]):
                    stats['rows_skipped'] += 1
                    continue

                # Track current activity code (merged rows)
                act_code_raw = safe_str(row[COL_ACT_CODE])
                if act_code_raw:
                    current_act_code = act_code_raw.strip()

                # SousActivite name
                sa_name = safe_str(row[COL_SA_NAME])
                if not sa_name:
                    # Could be an activity header row
                    stats['rows_processed'] += 1
                    continue

                # Match sous-activite by activity code and name
                sa_key = sa_name.strip().lower()
                if current_act_code:
                    sa = sa_by_key.get((current_act_code, sa_key))
                else:
                    same_name = sa_by_name.get(sa_key, [])
                    sa = same_name[0] if len(same_name) == 1 else None
                if not sa:
                    # Create as WEEKLY source sous-activité under matching activity
                    parent_act = act_by_code.get(current_act_code) if current_act_code else None
                    if parent_act:
                        responsible = safe_str(row[COL_RESPONSABLE])
                        intervenants = safe_str(row[COL_INTERVENANTS])
                        date_start = parse_date(row[COL_ECHEANCE_DEBUT])
                        date_end = parse_date(row[COL_ECHEANCE_FIN])
                        sa, _ = SousActivite.objects.get_or_create(
                            activite=parent_act,
                            name=sa_name[:500],
                            source=SousActiviteSource.WEEKLY,
                            defaults={
                                'responsible': responsible,
                                'intervenants': intervenants,
                                'date_start': date_start,
                                'date_end': date_end,
                            },
                        )
                        sa_by_key[(current_act_code, sa_key)] = sa
                        stats['created_as_weekly'] += 1
                    else:
                        stats['unmatched'] += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Row {row_num}: No parent activity "
                                f"for code={current_act_code}: {sa_name[:60]}"
                            )
                        )
                        stats['rows_processed'] += 1
                        continue
                else:
                    stats['matched'] += 1

                # Update date_start/date_end and responsible/intervenants
                date_start = parse_date(row[COL_ECHEANCE_DEBUT])
                date_end = parse_date(row[COL_ECHEANCE_FIN])
                responsible = safe_str(row[COL_RESPONSABLE])
                intervenants = safe_str(row[COL_INTERVENANTS])

                update_fields = {}
                if date_start:
                    update_fields['date_start'] = date_start
                if date_end:
                    update_fields['date_end'] = date_end
                if responsible:
                    update_fields['responsible'] = responsible
                if intervenants:
                    update_fields['intervenants'] = intervenants
                if update_fields:
                    for field, value in update_fields.items():
                        setattr(sa, field, value)
                    sa.save()
                    stats['dates_updated'] += 1

                # Create weekly entries
                for week in weeks:
                    etat_val = safe_str(
                        ws.cell(
                            row=row_num, column=week['col_etat'],
                        ).value
                    )
                    plan_val = ''
                    if week['col_plan'] <= num_cols:
                        plan_val = safe_str(
                            ws.cell(
                                row=row_num, column=week['col_plan'],
                            ).value
                        )

                    # Skip if both columns are empty
                    if not etat_val and not plan_val:
                        continue

                    WeeklyPlanEntry.objects.update_or_create(
                        sous_activite=sa,
                        week_start=week['week_start'],
                        defaults={
                            'week_end': week['week_end'],
                            'status_description': etat_val,
                            'planned_description': plan_val,
                            'responsible': responsible or sa.responsible,
                            'intervenants': (
                                intervenants or sa.intervenants
                            ),
                        },
                    )
                    stats['entries_created'] += 1

                stats['rows_processed'] += 1

            # A dry run performs the whole import and rolls it back, so its
            # summary is the one the real run prints.
            if dry_run:
                transaction.set_rollback(True)

        # Report
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import Summary:"))
        self.stdout.write(f"  Rows processed: {stats['rows_processed']}")
        self.stdout.write(f"  Rows skipped (empty): {stats['rows_skipped']}")
        self.stdout.write(
            f"  Sous-activites matched (PTBA): {stats['matched']}"
        )
        self.stdout.write(
            f"  Sous-activites created (WEEKLY): {stats['created_as_weekly']}"
        )
        self.stdout.write(
            f"  Sous-activites unmatched (no parent): {stats['unmatched']}"
        )
        self.stdout.write(
            f"  Weekly entries created/updated: {stats['entries_created']}"
        )
        self.stdout.write(
            f"  Sous-activites dates updated: {stats['dates_updated']}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  [DRY RUN] No changes were committed."
            ))
