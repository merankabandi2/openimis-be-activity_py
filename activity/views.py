"""
REST views for Activity module.

Provides Excel export endpoint for PTBA data.
"""
import logging
from decimal import Decimal

from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from activity.models import PTBA, Composante, FundingSource

logger = logging.getLogger(__name__)

ZERO = Decimal('0')

# Header row definition
HEADERS = [
    # Hierarchy (cols 1-8)
    'Composante Code', 'Composante', 'Sous-Composante Code', 'Sous-Composante',
    'Activite Code', 'Activite', 'Sous-Activite Code', 'Sous-Activite',
    # Activity metadata (cols 9-13)
    'Indicateur', 'Province', 'Structure Responsable', 'Mode de Passation', 'Statut',
    # Physical planning (cols 14-20)
    'Unite', 'Cout Unitaire', 'Quantite Totale',
    'Quantite T1', 'Quantite T2', 'Quantite T3', 'Quantite T4',
    # Financial planning (cols 21-25)
    'Budget Total', 'Budget T1', 'Budget T2', 'Budget T3', 'Budget T4',
    # Funding sources are appended dynamically (cols 26+)
    # Execution T1 (4 cols)
    # Execution T2 (4 cols)
    # Execution T3 (4 cols)
    # Execution T4 (4 cols)
    # Observations
]

EXECUTION_HEADERS_PER_QUARTER = [
    'Budget Prevu', 'Budget Engage', 'Budget Decaisse', 'Resultats Realises',
]


def _get_user(request):
    """Extract user from request, handling DRF and Django auth."""
    user = getattr(request, 'user', None)
    if user is None or type(user) is AnonymousUser:
        return None
    if not getattr(user, 'id', None):
        return None
    return user


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_ptba(request, ptba_id):
    """Export PTBA to multi-column Excel format with execution data."""
    user = _get_user(request)
    if user is None:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    config = apps.get_app_config('activity')
    if not user.has_perms(config.gql_ptba_search_perms):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        ptba = PTBA.objects.get(id=ptba_id)
    except PTBA.DoesNotExist:
        return JsonResponse({'error': 'PTBA not found'}, status=404)

    # Collect all active funding sources used by this PTBA
    funding_sources = list(
        FundingSource.objects.filter(
            allocations__sous_activite__activite__sous_composante__composante__ptba=ptba,
        ).distinct().order_by('code')
    )

    # Build full header row
    full_headers = list(HEADERS)
    for fs in funding_sources:
        full_headers.append(f"{fs.code} - {fs.name}")
    for q in range(1, 5):
        for h in EXECUTION_HEADERS_PER_QUARTER:
            full_headers.append(f"T{q} {h}")
    full_headers.append('Observations')

    wb = Workbook()
    ws = wb.active
    ws.title = f"PTBA {ptba.code}"

    # Styles
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, size=10, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(full_headers))
    title_cell = ws.cell(row=1, column=1, value=f"{ptba.code} - {ptba.name}")
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')

    # Header row (row 3)
    header_row = 3
    for col_idx, header in enumerate(full_headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = thin_border

    # Data rows
    row_idx = header_row + 1
    composantes = Composante.objects.filter(ptba=ptba).prefetch_related(
        'sous_composantes__activites__sous_activites__funding_allocations__funding_source',
        'sous_composantes__activites__sous_activites__executions',
    ).order_by('sort_order', 'code')

    for comp in composantes:
        for sc in comp.sous_composantes.order_by('sort_order', 'code'):
            for act in sc.activites.order_by('sort_order', 'code'):
                for sa in act.sous_activites.order_by('sort_order', 'code'):
                    row_data = [
                        # Hierarchy
                        comp.code, comp.name,
                        sc.code, sc.name,
                        act.code, act.name,
                        sa.code, sa.name,
                        # Activity metadata
                        act.indicator_description, act.province,
                        act.implementing_structure, act.procurement_method,
                        act.status,
                        # Physical planning
                        sa.unit, sa.unit_cost, sa.quantity_total,
                        sa.quantity_t1, sa.quantity_t2, sa.quantity_t3, sa.quantity_t4,
                        # Financial planning
                        sa.budget_total, sa.budget_t1, sa.budget_t2, sa.budget_t3, sa.budget_t4,
                    ]

                    # Funding allocations (from prefetched cache)
                    allocations = {
                        alloc.funding_source_id: alloc.amount
                        for alloc in sa.funding_allocations.all()
                    }
                    for fs in funding_sources:
                        row_data.append(allocations.get(fs.id, ZERO))

                    # Execution data per quarter (from prefetched cache)
                    executions = {
                        ex.quarter: ex
                        for ex in sa.executions.all()
                    }
                    observations_parts = []
                    for q in range(1, 5):
                        ex = executions.get(q)
                        if ex:
                            row_data.extend([
                                ex.budget_prevu, ex.budget_engage,
                                ex.budget_decaisse, ex.resultats_realises,
                            ])
                            if ex.observations:
                                observations_parts.append(f"T{q}: {ex.observations}")
                        else:
                            row_data.extend([ZERO, ZERO, ZERO, ZERO])

                    row_data.append('; '.join(observations_parts))

                    # Write row
                    for col_idx, value in enumerate(row_data, start=1):
                        cell = ws.cell(row=row_idx, column=col_idx, value=value)
                        cell.border = thin_border

                    row_idx += 1

    # Auto-width columns (approximate)
    for col_idx in range(1, len(full_headers) + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 15

    # Wider columns for names
    for col_idx in [2, 4, 6, 8]:
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 30

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    filename = f"PTBA_{ptba.code}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
