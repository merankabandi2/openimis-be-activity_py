"""UAT section D (activites-uat.md): lifecycle, quarterly execution and
M&E indicator feeding, exercised through the GraphQL mutation classes with
accounts whose roles carry the exact right sets of the UAT roles."""
import datetime
import uuid
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase

from core.models import Role, RoleRight
from core.test_helpers import create_test_interactive_user
from activity.gql_mutations import (
    LinkActivityToIndicatorMutation,
    ReportQuarterlyExecutionMutation,
    TransitionActivityMutation,
    UnlinkActivityFromIndicatorMutation,
)
from activity.models import (
    PTBA, Activite, ActivityStatus, ActivityStatusTransition, Composante,
    QuarterlyExecution, SousActivite, SousComposante,
)
from activity.services import ActivityLifecycleService

ROLE_RIGHTS = {
    'gest': list(range(802005, 802018)) + [801009, 801022],
    'lect': [802014, 802005, 802012],
    'saisie': [802014, 802015, 802016, 802005, 802006, 802007],
    'exec': [802014, 802005, 802009],
    'appr': [802014, 802005, 802010, 802011],
}


def _role(name, rights):
    now = datetime.datetime.now()
    role = Role.objects.create(
        name=name, is_system=0, is_blocked=False, audit_user_id=-1, validity_from=now,
    )
    for right_id in rights:
        RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=-1, validity_from=now)
    return role


def _error_detail(result):
    """async_mutate returns None on success, else a list of {message, detail}."""
    if not result:
        return None
    return ' | '.join(str(e.get('detail', '')) for e in result)


class UatSectionDTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tag = uuid.uuid4().hex[:6]
        cls.users = {}
        for key, rights in ROLE_RIGHTS.items():
            role = _role(f'UAT-D-{key}-{tag}', rights)
            cls.users[key] = create_test_interactive_user(
                username=f'uatd_{key}_{tag}', roles=[role.id],
            )
        cls.ptba = PTBA.objects.create(
            code=f'UAT-ACT-D-{tag}', name='UAT D',
            fiscal_year_start=datetime.date(2026, 1, 1),
            fiscal_year_end=datetime.date(2026, 12, 31),
        )
        cls.comp = Composante.objects.create(ptba=cls.ptba, code='D1', name='Comp D')
        cls.sc = SousComposante.objects.create(composante=cls.comp, code='D1.1', name='SC D')

    # -- helpers -----------------------------------------------------------

    def _activity(self, status=ActivityStatus.PLANIFIE, n_sa=1):
        act = Activite.objects.create(
            sous_composante=self.sc, code=f'D-{uuid.uuid4().hex[:6]}',
            name='Activite UAT D', status=status,
        )
        for i in range(n_sa):
            SousActivite.objects.create(
                activite=act, code=f'{act.code}-{i + 1}', name=f'SA{i + 1}', unit='atelier',
                quantity_total=Decimal('8'), quantity_t1=Decimal('2'), quantity_t2=Decimal('2'),
                quantity_t3=Decimal('2'), quantity_t4=Decimal('2'),
                unit_cost=Decimal('1000'),
                budget_t1=Decimal('2000'), budget_t2=Decimal('2000'),
                budget_t3=Decimal('2000'), budget_t4=Decimal('2000'),
                budget_total=Decimal('8000'),
            )
        return act

    def _transition(self, who, act, to_status, comment=''):
        return TransitionActivityMutation.async_mutate(
            self.users[who], activite_id=str(act.id), to_status=to_status, comment=comment,
        )

    def _report(self, who, sa, quarter=1, year=2026, **values):
        return ReportQuarterlyExecutionMutation.async_mutate(
            self.users[who], sous_activite_id=str(sa.id), quarter=quarter, year=year, **values,
        )

    def _indicator(self):
        from merankabandi.models import Indicator
        return Indicator.objects.create(
            name='UAT-ACT indicateur de test', baseline=Decimal('0'), target=Decimal('100'),
        )

    # -- D1 ------------------------------------------------------------------

    def test_d1_budgetise_without_sous_activite_is_refused(self):
        act = self._activity(n_sa=0)
        result = self._transition('gest', act, ActivityStatus.BUDGETISE)
        detail = _error_detail(result)
        print(f'\n[D1] journal detail: {detail}')
        self.assertIn('Activity must have at least one sous-activite to be budgetised.', detail)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.PLANIFIE)
        self.assertFalse(ActivityStatusTransition.objects.filter(activite=act).exists())

    # -- D2 / D3 -------------------------------------------------------------

    def test_d2_d3_budgetise_revert_budgetise_history(self):
        act = self._activity()
        self.assertIsNone(self._transition('gest', act, ActivityStatus.BUDGETISE, 'D2 budget ok'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.BUDGETISE)
        first = ActivityStatusTransition.objects.get(activite=act)
        self.assertEqual((first.from_status, first.to_status), ('PLANIFIE', 'BUDGETISE'))
        self.assertEqual(first.transitioned_by_id, self.users['gest'].id)
        self.assertEqual(first.comment, 'D2 budget ok')
        self.assertIsNotNone(first.transitioned_at)

        self.assertIsNone(self._transition('appr', act, ActivityStatus.PLANIFIE, 'D3 retour'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.PLANIFIE)
        self.assertIsNone(self._transition('gest', act, ActivityStatus.BUDGETISE, 'D3 re-budget'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.BUDGETISE)
        rows = list(
            ActivityStatusTransition.objects.filter(activite=act)
            .order_by('transitioned_at').values_list('from_status', 'to_status', 'transitioned_by_id')
        )
        print(f'\n[D3] history: {[(r[0], r[1]) for r in rows]}')
        self.assertEqual(rows[1:], [
            ('BUDGETISE', 'PLANIFIE', self.users['appr'].id),
            ('PLANIFIE', 'BUDGETISE', self.users['gest'].id),
        ])

    # -- D4 ------------------------------------------------------------------

    def test_d4_demarrer_sets_approver_and_notifies_802009_holders_in_app(self):
        from notification.models import Notification, NotificationEventType, NotificationTemplate
        from notification.services import RecipientResolver
        et, _ = NotificationEventType.objects.update_or_create(
            code='activity.submitted',
            defaults={'category': 'activity', 'is_active': True,
                      'default_channels': {'in_app': True, 'email': False, 'sms': False}},
        )
        if not NotificationTemplate.objects.filter(event_type=et).exists():
            NotificationTemplate.objects.create(
                event_type=et, language='fr', subject='Activite {activity_type}',
                body='{new_status}',
            )
        act = self._activity(ActivityStatus.BUDGETISE)
        self.assertIsNone(self._transition('appr', act, ActivityStatus.EN_COURS, 'D4 start'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.EN_COURS)
        self.assertEqual(act.approved_by_id, self.users['appr'].id)
        self.assertIsNotNone(act.approved_date)

        holders = {u.id for u in RecipientResolver.by_role(802009)}
        self.assertIn(self.users['exec'].id, holders)
        self.assertIn(self.users['gest'].id, holders)
        notifs = Notification.objects.filter(event_type=et, entity_id=act.id)
        channels = set(notifs.values_list('channel', flat=True))
        recipients = set(notifs.values_list('recipient_id', flat=True))
        print(f'\n[D4] channels={channels} recipients={len(recipients)} holders_802009={len(holders)}'
              f' entity_url={set(notifs.values_list("entity_url", flat=True))}')
        self.assertEqual(channels, {'in_app'})
        self.assertIn(self.users['exec'].id, recipients)
        self.assertNotIn(self.users['appr'].id, recipients)
        self.assertEqual(recipients, holders - {self.users['appr'].id})
        self.assertEqual(len(mail.outbox), 0)

    def test_d4_notification_body_fills_location_and_date(self):
        from django.utils import timezone
        from notification.models import Notification, NotificationEventType, NotificationTemplate
        et, _ = NotificationEventType.objects.update_or_create(
            code='activity.submitted',
            defaults={'category': 'activity', 'is_active': True,
                      'default_channels': {'in_app': True, 'email': False, 'sms': False}},
        )
        NotificationTemplate.objects.update_or_create(
            event_type=et, language='fr',
            defaults={'subject': 'Activite soumise pour validation',
                      'body': 'Une activite {activity_type} a {location} du {date} est en attente de validation.'},
        )
        act = self._activity(ActivityStatus.BUDGETISE)
        self.assertIsNone(self._transition('appr', act, ActivityStatus.EN_COURS))
        notif = Notification.objects.filter(event_type=et, entity_id=act.id,
                                            recipient=self.users['exec']).get()
        print(f'\n[D4-body] {notif.title!r} / {notif.body!r}')
        self.assertEqual(
            notif.body,
            'Une activite Activite UAT D a - du %s est en attente de validation.'
            % timezone.now().strftime('%d/%m/%Y'),
        )

    # -- D5 / D6 / D7 --------------------------------------------------------

    @mock.patch('notification.services.NotificationService.notify')
    def test_d5_marquer_realise_emits_activity_validated(self, notify):
        from notification.services import RecipientResolver
        act = self._activity(ActivityStatus.EN_COURS)
        act.approved_by = self.users['appr']
        act.save()
        self.assertIsNone(self._transition('exec', act, ActivityStatus.REALISE, 'D5 fini'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.REALISE)
        row = ActivityStatusTransition.objects.get(activite=act)
        self.assertEqual((row.from_status, row.to_status, row.comment), ('EN_COURS', 'REALISE', 'D5 fini'))
        self.assertEqual(row.transitioned_by_id, self.users['exec'].id)
        notify.assert_called_once()
        kwargs = notify.call_args.kwargs
        self.assertEqual(kwargs['event_code'], 'activity.validated')
        self.assertEqual(kwargs['entity_url'], f'/activity/activite/{act.id}')
        sent = {u.id for u in kwargs['recipients']}
        expected = {u.id for u in RecipientResolver.by_role(802010)} | {self.users['appr'].id}
        print(f'\n[D5] event={kwargs["event_code"]} recipients={len(sent)} context={kwargs["context"]}')
        self.assertEqual(sent, expected)

    def test_d5_marquer_realise_refused_without_802009(self):
        act = self._activity(ActivityStatus.EN_COURS)
        detail = _error_detail(self._transition('appr', act, ActivityStatus.REALISE))
        print(f'\n[D5-neg] appr detail: {detail}')
        self.assertIn('Insufficient permissions for transition EN_COURS -> REALISE', detail)

    @mock.patch('notification.services.NotificationService.notify')
    def test_d6_reouvrir_realise_to_en_cours(self, notify):
        act = self._activity(ActivityStatus.REALISE)
        self.assertIsNone(self._transition('appr', act, ActivityStatus.EN_COURS, 'D6 reouvrir'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.EN_COURS)
        self.assertEqual(act.approved_by_id, self.users['appr'].id)
        codes = [c.kwargs['event_code'] for c in notify.call_args_list]
        print(f'\n[D6] events emitted on reopen: {codes}')
        self.assertEqual(codes, ['activity.submitted'])
        detail = _error_detail(self._transition('exec', self._activity(ActivityStatus.REALISE),
                                                ActivityStatus.EN_COURS))
        self.assertIn('Insufficient permissions for transition REALISE -> EN_COURS', detail)

    @mock.patch('notification.services.NotificationService.notify')
    def test_d7_cloturer_requires_execution_on_every_sous_activite(self, notify):
        act = self._activity(ActivityStatus.EN_COURS, n_sa=2)
        sa1, sa2 = act.sous_activites.order_by('code')
        self.assertIsNone(self._report('exec', sa1, budget_engage=Decimal('1500'),
                                       budget_decaisse=Decimal('1000'), resultats_realises=Decimal('2')))
        self.assertIsNone(self._transition('exec', act, ActivityStatus.REALISE))
        detail = _error_detail(self._transition('appr', act, ActivityStatus.CLOTURE))
        print(f'\n[D7] refusal: {detail}')
        self.assertIn(f'Sous-activite {sa2.code} has no execution data', detail)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.REALISE)

        self.assertIsNone(self._transition('appr', act, ActivityStatus.EN_COURS))
        self.assertIsNone(self._report('exec', sa2, budget_engage=Decimal('500'), resultats_realises=Decimal('1')))
        self.assertIsNone(self._transition('exec', act, ActivityStatus.REALISE))
        self.assertIsNone(self._transition('appr', act, ActivityStatus.CLOTURE, 'D7 cloture'))
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.CLOTURE)
        self.assertEqual(act.closed_by_id, self.users['appr'].id)
        self.assertIsNotNone(act.closed_date)
        detail = _error_detail(self._transition('gest', act, ActivityStatus.EN_COURS))
        self.assertIn('Cannot transition from CLOTURE', detail)

    # -- D8 (backend side of the per-account buttons) -------------------------

    def test_d8_transition_permission_matrix_per_account(self):
        matrix = {}
        for who, user in self.users.items():
            allowed = []
            for src, dst in ActivityLifecycleService.TRANSITION_PERMS:
                if user.has_perms(ActivityLifecycleService.required_perms(src, dst)):
                    allowed.append(f'{src}->{dst}')
            matrix[who] = sorted(allowed)
        print(f'\n[D8] matrix: {matrix}')
        self.assertEqual(matrix['lect'], [])
        self.assertEqual(matrix['exec'], ['EN_COURS->REALISE'])
        self.assertEqual(matrix['appr'], sorted([
            'BUDGETISE->EN_COURS', 'BUDGETISE->PLANIFIE', 'REALISE->CLOTURE', 'REALISE->EN_COURS',
        ]))
        self.assertEqual(matrix['saisie'], ['PLANIFIE->BUDGETISE'])
        self.assertEqual(len(matrix['gest']), 6)

    # -- D9 / D10 / D11 / D12 / D13 ------------------------------------------

    def test_d9_d10_report_computes_rates_and_updates_in_place(self):
        act = self._activity(ActivityStatus.EN_COURS)
        sa = act.sous_activites.get()
        self.assertIsNone(self._report('exec', sa, quarter=3, budget_engage=Decimal('1500'),
                                       budget_decaisse=Decimal('500'), resultats_realises=Decimal('1'),
                                       observations='D9'))
        qe = QuarterlyExecution.objects.get(sous_activite=sa, quarter=3, year=2026)
        print(f'\n[D9] prevu={qe.budget_prevu} attendus={qe.resultats_attendus} '
              f'taux={qe.taux_engagement}/{qe.taux_decaissement}/{qe.taux_realisation}')
        self.assertEqual(qe.budget_prevu, Decimal('2000'))
        self.assertEqual(qe.resultats_attendus, Decimal('2'))
        self.assertEqual(qe.taux_engagement, Decimal('75.00'))
        self.assertEqual(qe.taux_decaissement, Decimal('25.00'))
        self.assertEqual(qe.taux_realisation, Decimal('50.00'))
        self.assertEqual(qe.reported_by_id, self.users['exec'].id)

        self.assertIsNone(self._report('exec', sa, quarter=3, budget_engage=Decimal('2000'),
                                       budget_decaisse=Decimal('2000'), resultats_realises=Decimal('2'),
                                       observations='D10'))
        rows = QuarterlyExecution.objects.filter(sous_activite=sa, quarter=3, year=2026)
        self.assertEqual(rows.count(), 1)
        qe = rows.get()
        self.assertEqual((qe.taux_engagement, qe.taux_realisation, qe.observations),
                         (Decimal('100.00'), Decimal('100.00'), 'D10'))

    def test_d11_report_refused_when_not_en_cours(self):
        act = self._activity(ActivityStatus.BUDGETISE)
        detail = _error_detail(self._report('exec', act.sous_activites.get(), budget_engage=Decimal('10')))
        print(f'\n[D11] refusal: {detail}')
        self.assertIn('Activity must be EN_COURS to report execution', detail)
        self.assertFalse(QuarterlyExecution.objects.filter(sous_activite__activite=act).exists())

    def test_d12_rate_of_1500_percent_is_saved(self):
        act = self._activity(ActivityStatus.EN_COURS)
        sa = act.sous_activites.get()
        result = self._report('exec', sa, quarter=1, budget_engage=Decimal('30000'))
        print(f'\n[D12] engage=15x prevu -> {_error_detail(result)}')
        self.assertIsNone(result)
        execution = QuarterlyExecution.objects.get(sous_activite=sa)
        execution.refresh_from_db()
        self.assertEqual(execution.budget_prevu, Decimal('2000'))
        self.assertEqual(execution.taux_engagement, Decimal('1500.00'))

    def test_d13_report_accepted_with_802009_without_802007(self):
        self.assertFalse(self.users['exec'].has_perms(['802007']))
        act = self._activity(ActivityStatus.EN_COURS)
        self.assertIsNone(self._report('exec', act.sous_activites.get(), budget_engage=Decimal('10')))
        self.assertTrue(QuarterlyExecution.objects.filter(sous_activite__activite=act).exists())
        detail = _error_detail(self._report('saisie', act.sous_activites.get(), budget_engage=Decimal('20')))
        print(f'\n[D13] saisie (802007 without 802009): {detail}')
        self.assertIn('mutation.authentication_required', detail)

    # -- D15 / D16 / D17 / D18 -----------------------------------------------

    def test_d15_d16_link_and_unlink_with_raw_ids(self):
        ind = self._indicator()
        act = self._activity(ActivityStatus.EN_COURS)
        self.assertIsNone(LinkActivityToIndicatorMutation.async_mutate(
            self.users['gest'], activite_id=str(act.id), indicator_id=ind.id))
        self.assertEqual(list(act.indicators.values_list('id', flat=True)), [ind.id])
        detail = _error_detail(LinkActivityToIndicatorMutation.async_mutate(
            self.users['exec'], activite_id=str(act.id), indicator_id=ind.id))
        self.assertIn('mutation.authentication_required', detail)
        self.assertIsNone(UnlinkActivityFromIndicatorMutation.async_mutate(
            self.users['gest'], activite_id=str(act.id), indicator_id=ind.id))
        self.assertFalse(act.indicators.exists())

    def test_d17_report_feeds_indicator_achievement_at_quarter_end(self):
        from merankabandi.models import IndicatorAchievement
        ind = self._indicator()
        act = self._activity(ActivityStatus.EN_COURS)
        act.indicators.add(ind)
        self.assertIsNone(self._report('exec', act.sous_activites.get(), quarter=3,
                                       resultats_realises=Decimal('2')))
        ach = IndicatorAchievement.objects.get(indicator=ind)
        print(f'\n[D17] achievement date={ach.date} achieved={ach.achieved} comment={ach.comment!r}')
        self.assertEqual(ach.date, datetime.date(2026, 9, 30))
        self.assertEqual(ach.achieved, Decimal('2'))
        self.assertEqual(ach.comment, 'Auto: T3 2026')

    def test_d18_two_sous_activites_same_quarter_are_summed(self):
        from merankabandi.models import IndicatorAchievement
        ind = self._indicator()
        act = self._activity(ActivityStatus.EN_COURS, n_sa=2)
        act.indicators.add(ind)
        sa1, sa2 = act.sous_activites.order_by('code')
        self.assertIsNone(self._report('exec', sa1, quarter=3, resultats_realises=Decimal('2')))
        self.assertIsNone(self._report('exec', sa2, quarter=3, resultats_realises=Decimal('1')))
        achievements = IndicatorAchievement.objects.filter(indicator=ind, date=datetime.date(2026, 9, 30))
        print(f'\n[D18] achievements={list(achievements.values_list("achieved", flat=True))}')
        self.assertEqual(achievements.count(), 1)
        first = achievements.get()
        self.assertEqual(first.achieved, Decimal('3'))

        self.assertIsNone(self._report('exec', sa2, quarter=3, resultats_realises=Decimal('4')))
        self.assertEqual(list(achievements.values_list('id', 'achieved')), [(first.id, Decimal('6'))])


class UatSectionDFrontendPayloadTests(TestCase):
    """Runs the query and mutation text of the activity page
    (openimis-fe-activity_js src/actions.js) through the project schema."""

    def _execute(self, text):
        from openIMIS.schema import schema
        return schema.execute(text)

    def _validation_errors(self, text):
        from graphql import parse, validate
        from openIMIS.schema import schema
        return [e.message for e in validate(schema, parse(text))]

    def test_act_s2_activity_page_projection_is_valid(self):
        # indicators part of ACTIVITE_FULL_PROJECTION
        text = ('{ activite(id: "%s") { edges { node { id indicators { edges { node { id name '
                'baseline target achievements { edges { node { achieved date timestamp } } } } } } } } } }'
                % uuid.uuid4())
        self.assertEqual(self._validation_errors(text), [])

    def test_history_tab_projection_is_valid(self):
        # TRANSITION_HISTORY_PROJECTION
        text = ('{ activityStatusTransition(activite_Id: "%s", orderBy: ["-transitioned_at"]) '
                '{ edges { node { id fromStatus toStatus transitionedAt comment '
                'transitionedBy { username lastName otherNames } } } } }' % uuid.uuid4())
        self.assertEqual(self._validation_errors(text), [])

    def test_execution_tab_projection_is_valid(self):
        # QUARTERLY_EXECUTION_PROJECTION with the executionYearFilters filters
        text = ('{ quarterlyExecution(sousActivite_Activite_Id: "%s", year: 2026) '
                '{ edges { node { id quarter year budgetPrevu budgetEngage budgetDecaisse '
                'resultatsAttendus resultatsRealises tauxEngagement tauxDecaissement tauxRealisation '
                'observations reportedDate reportedBy { username lastName otherNames } '
                'sousActivite { id code name } } } } }' % uuid.uuid4())
        self.assertEqual(self._validation_errors(text), [])

    def test_act_s1_unlink_with_relay_id_is_rejected(self):
        # indicatorId is an Int argument: a relay-encoded id is rejected
        # before the mutation runs.
        from graphql_relay import to_global_id
        relay_id = to_global_id('IndicatorGQLType', 31)
        text = ('mutation { unlinkActivityFromIndicator(input: { clientMutationId: "x" '
                'activiteId: "%s" indicatorId: %s }) { internalId } }' % (uuid.uuid4(), relay_id))
        result = self._execute(text)
        messages = [str(e) for e in (result.errors or [])]
        print(f'\n[ACT-S1 unlink] relay id={relay_id} errors={messages}')
        self.assertTrue(messages)
