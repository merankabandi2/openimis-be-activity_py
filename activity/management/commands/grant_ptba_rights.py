"""Grant the PTBA rights to the activity roles that hold the legacy PTBA codes.

The PTBA search, create, update and delete perms are the module config values
gql_ptba_*_perms (170014-170017 by default). The legacy codes 170001-170004
are also the social_protection beneficiary rights, so the command only looks
at live roles holding at least one other activity-module right (activity,
execution, transition, dashboard or funding perms). For such a role, each
legacy code it holds gives it the matching PTBA right when it lacks it.

A right already held is left alone and no right is ever closed. The rights
cache of the users holding a changed role is purged.

Usage:
    python manage.py grant_ptba_rights              # dry run
    python manage.py grant_ptba_rights --apply
"""
from django.apps import apps
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Role, RoleRight, UserRole

AUDIT_USER_ID = 1

# Legacy code -> module config attribute of the PTBA perm it maps to.
LEGACY_PTBA_CODES = (
    (170001, 'gql_ptba_search_perms'),
    (170002, 'gql_ptba_create_perms'),
    (170003, 'gql_ptba_update_perms'),
    (170004, 'gql_ptba_delete_perms'),
)

ACTIVITY_ROLE_PERMS = (
    'gql_activity_search_perms', 'gql_activity_create_perms',
    'gql_activity_update_perms', 'gql_activity_delete_perms',
    'gql_execution_report_perms', 'gql_execution_approve_perms',
    'gql_transition_perms', 'gql_dashboard_view_perms',
    'gql_funding_manage_perms',
)


def _codes(config, attribute):
    return [int(code) for code in getattr(config, attribute)]


def activity_role_rights(config):
    """Right codes that mark a role as an activity-module role."""
    rights = set()
    for attribute in ACTIVITY_ROLE_PERMS:
        rights.update(_codes(config, attribute))
    return rights


def legacy_mapping(config):
    """legacy code -> PTBA right codes it gives, from the module config."""
    return {legacy: _codes(config, attribute) for legacy, attribute in LEGACY_PTBA_CODES}


def plan(config=None):
    """One entry per live activity role holding a legacy PTBA code, by role id."""
    config = config or apps.get_app_config('activity')
    mapping = legacy_mapping(config)
    marker_rights = activity_role_rights(config)
    role_ids = (RoleRight.objects
                .filter(validity_to__isnull=True, right_id__in=marker_rights,
                        role__validity_to__isnull=True)
                .values_list('role_id', flat=True).distinct())
    entries = []
    for role in Role.objects.filter(id__in=role_ids).order_by('id'):
        held = set(RoleRight.objects
                   .filter(role=role, validity_to__isnull=True)
                   .values_list('right_id', flat=True))
        legacy_held = sorted(code for code in mapping if code in held)
        if not legacy_held:
            continue
        to_grant = []
        for legacy in legacy_held:
            for right_id in mapping[legacy]:
                if right_id not in held and right_id not in to_grant:
                    to_grant.append(right_id)
        entries.append({
            'role': role,
            'legacy_held': legacy_held,
            'ptba_held': sorted(r for codes in mapping.values() for r in codes if r in held),
            'to_grant': to_grant,
        })
    return entries


def invalidate_rights_cache(role):
    """Drop the cached rights of every user holding the role; returns the count.

    ``InteractiveUser.rights`` is cached with no expiry, so a granted right
    stays invisible to a logged-in user until the cache entry is removed.
    """
    user_ids = list(UserRole.objects
                    .filter(role=role, validity_to__isnull=True)
                    .values_list('user_id', flat=True).distinct())
    for user_id in user_ids:
        cache.delete(f'rights_{user_id}')
        cache.delete(f'is_admin_{user_id}')
    return len(user_ids)


class Command(BaseCommand):
    help = ('Grant the PTBA rights (gql_ptba_*_perms) to the activity roles '
            'holding the legacy PTBA codes 170001-170004')

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the rights; without it the command only reports what '
                 'it would do')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report only (the default); refused together with --apply')

    def handle(self, *args, **options):
        if options['apply'] and options['dry_run']:
            raise CommandError('--apply and --dry-run exclude each other')

        entries = plan()
        if not entries:
            self.stdout.write('no activity role holds a legacy PTBA code')
        for entry in entries:
            self.stdout.write(
                f"{entry['role'].name!r}: role {entry['role'].id}, "
                f"legacy {entry['legacy_held']}, "
                f"to grant {entry['to_grant']}, already held {entry['ptba_held']}")

        if not options['apply']:
            self.stdout.write(self.style.SUCCESS(
                'DRY RUN - nothing written (add --apply)'))
            return

        created = []
        with transaction.atomic():
            for entry in entries:
                for right_id in entry['to_grant']:
                    created.append(RoleRight.objects.create(
                        role=entry['role'], right_id=right_id,
                        audit_user_id=AUDIT_USER_ID))
        purged = sum(invalidate_rights_cache(entry['role'])
                     for entry in entries if entry['to_grant'])
        for row in created:
            self.stdout.write(
                f'created RoleRight {row.id}: role {row.role_id}, right {row.right_id}')
        self.stdout.write(self.style.SUCCESS(
            f'rights created {len(created)}, '
            f'rights cache purged for {purged} user(s)'))
