import uuid
from django.db import models

from core.models import User
from location.models import Location


class PTBAStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Brouillon'
    APPROVED = 'APPROVED', 'Approuve'
    ACTIVE = 'ACTIVE', 'Actif'
    CLOSED = 'CLOSED', 'Cloture'


class ActivityStatus(models.TextChoices):
    PLANIFIE = 'PLANIFIE', 'Planifie'
    BUDGETISE = 'BUDGETISE', 'Budgetise'
    EN_COURS = 'EN_COURS', 'En cours'
    REALISE = 'REALISE', 'Realise'
    CLOTURE = 'CLOTURE', 'Cloture'


class RevisionStatus(models.TextChoices):
    INITIAL = 'INITIAL', 'Initial'
    REVISE = 'REVISE', 'Revise'
    AJOUTE = 'AJOUTE', 'Ajoute'
    ABANDONNE = 'ABANDONNE', 'Abandonne'


class PTBA(models.Model):
    """Annual Work Plan and Budget (Plan de Travail et Budget Annuel)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    fiscal_year_start = models.DateField()
    fiscal_year_end = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=PTBAStatus.choices,
        default=PTBAStatus.DRAFT,
    )
    benefit_plan = models.ForeignKey(
        'social_protection.BenefitPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ptbas',
    )
    json_ext = models.JSONField(null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    user_created = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name='+',
        null=True, blank=True,
    )
    user_updated = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name='+',
        null=True, blank=True,
    )

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "PTBA"
        verbose_name_plural = "PTBAs"
        ordering = ['-fiscal_year_start']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Composante(models.Model):
    """Strategic component (level 1)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ptba = models.ForeignKey(
        PTBA, on_delete=models.CASCADE, related_name='composantes',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=500)
    sort_order = models.IntegerField(default=0)

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Composante"
        verbose_name_plural = "Composantes"
        ordering = ['ptba', 'sort_order', 'code']
        unique_together = ('ptba', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"


class SousComposante(models.Model):
    """Sub-component (level 2)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    composante = models.ForeignKey(
        Composante, on_delete=models.CASCADE, related_name='sous_composantes',
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=500)
    sort_order = models.IntegerField(default=0)

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Sous-Composante"
        verbose_name_plural = "Sous-Composantes"
        ordering = ['composante', 'sort_order', 'code']
        unique_together = ('composante', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"


class Activite(models.Model):
    """Operational activity (level 3)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sous_composante = models.ForeignKey(
        SousComposante, on_delete=models.CASCADE, related_name='activites',
    )
    code = models.CharField(max_length=20, blank=True, default="")
    name = models.CharField(max_length=500)
    status = models.CharField(
        max_length=20,
        choices=ActivityStatus.choices,
        default=ActivityStatus.PLANIFIE,
    )
    indicator_description = models.TextField(blank=True, default="")
    province = models.CharField(max_length=255, blank=True, default="")
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activites',
    )
    implementing_structure = models.CharField(max_length=255, blank=True, default="")
    procurement_method = models.CharField(max_length=255, blank=True, default="")
    # M&E link - optional dependency on merankabandi.Indicator
    # The M2M field is created conditionally; see bottom of this file.
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    approved_date = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    closed_date = models.DateTimeField(null=True, blank=True)
    observations = models.TextField(blank=True, default="")
    sort_order = models.IntegerField(default=0)
    json_ext = models.JSONField(null=True, blank=True)
    # Revision tracking
    revision_status = models.CharField(
        max_length=20, choices=RevisionStatus.choices,
        default='INITIAL', blank=True,
    )
    revision_comment = models.TextField(blank=True, default="")

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Activite"
        verbose_name_plural = "Activites"
        ordering = ['sous_composante', 'sort_order', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"


# Conditionally add M2M to merankabandi.Indicator
try:
    from merankabandi.models import Indicator as MerankabandiIndicator
    Activite.add_to_class(
        'indicators',
        models.ManyToManyField(
            MerankabandiIndicator,
            blank=True,
            related_name='activities',
        ),
    )
    HAS_MERANKABANDI = True
except ImportError:
    HAS_MERANKABANDI = False


class SousActiviteSource(models.TextChoices):
    PTBA = 'PTBA', 'PTBA'
    WEEKLY = 'WEEKLY', 'Planification hebdomadaire'
    MANUAL = 'MANUAL', 'Saisie manuelle'


class SousActivite(models.Model):
    """Activity line item (level 4) - the budget unit."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activite = models.ForeignKey(
        Activite, on_delete=models.CASCADE, related_name='sous_activites',
    )
    code = models.CharField(max_length=20, blank=True, default="")
    source = models.CharField(
        max_length=10, choices=SousActiviteSource.choices,
        default='PTBA',
    )
    name = models.CharField(max_length=500)
    expense_category_code = models.CharField(max_length=20, blank=True, default="")
    expense_category = models.CharField(max_length=255, blank=True, default="")
    unit = models.CharField(max_length=100, blank=True, default="")
    quantity_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    quantity_t1 = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    quantity_t2 = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    quantity_t3 = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    quantity_t4 = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_t1 = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_t2 = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_t3 = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_t4 = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    sort_order = models.IntegerField(default=0)
    json_ext = models.JSONField(null=True, blank=True)
    # Revision tracking (Initiale vs Revisee)
    quantity_initial = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    quantity_revised = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
    )
    unit_cost_initial = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    unit_cost_revised = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
    )
    budget_initial = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_revised = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
    )
    # Scheduling
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)
    # Responsibility
    responsible = models.CharField(max_length=255, blank=True, default="")
    intervenants = models.CharField(max_length=500, blank=True, default="")
    # Revision status
    revision_status = models.CharField(
        max_length=20, choices=RevisionStatus.choices,
        default='INITIAL', blank=True,
    )
    revision_comment = models.TextField(blank=True, default="")

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Sous-Activite"
        verbose_name_plural = "Sous-Activites"
        ordering = ['activite', 'sort_order', 'code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class FundingSource(models.Model):
    """Multi-donor funding source configuration."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Source de Financement"
        verbose_name_plural = "Sources de Financement"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class SousActiviteFunding(models.Model):
    """Funding allocation per sous-activite per donor."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sous_activite = models.ForeignKey(
        SousActivite, on_delete=models.CASCADE, related_name='funding_allocations',
    )
    funding_source = models.ForeignKey(
        FundingSource, on_delete=models.CASCADE, related_name='allocations',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_initial = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_revised = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
    )

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Allocation de Financement"
        verbose_name_plural = "Allocations de Financement"
        unique_together = ('sous_activite', 'funding_source')

    def __str__(self):
        return f"{self.sous_activite.code} - {self.funding_source.code}: {self.amount}"


class QuarterlyExecution(models.Model):
    """Quarterly execution report for a sous-activite."""
    QUARTER_CHOICES = [
        (1, 'T1'),
        (2, 'T2'),
        (3, 'T3'),
        (4, 'T4'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sous_activite = models.ForeignKey(
        SousActivite, on_delete=models.CASCADE, related_name='executions',
    )
    quarter = models.IntegerField(choices=QUARTER_CHOICES)
    year = models.IntegerField()
    budget_prevu = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_engage = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    budget_decaisse = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    resultats_attendus = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    resultats_realises = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    taux_engagement = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    taux_decaissement = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    taux_realisation = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    observations = models.TextField(blank=True, default="")
    reported_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    reported_date = models.DateTimeField(null=True, blank=True)

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        verbose_name = "Execution Trimestrielle"
        verbose_name_plural = "Executions Trimestrielles"
        unique_together = ('sous_activite', 'quarter', 'year')
        ordering = ['sous_activite', 'year', 'quarter']

    def __str__(self):
        return f"{self.sous_activite.code} T{self.quarter} {self.year}"


class ActivityStatusTransition(models.Model):
    """Audit trail for lifecycle transitions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activite = models.ForeignKey(
        Activite, on_delete=models.CASCADE, related_name='transitions',
    )
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    transitioned_by = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    transitioned_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Transition de Statut"
        verbose_name_plural = "Transitions de Statut"
        ordering = ['-transitioned_at']

    def __str__(self):
        return f"{self.activite.code}: {self.from_status} -> {self.to_status}"


class WeeklyPlanEntry(models.Model):
    """Weekly operational planning entry for a sous-activite."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sous_activite = models.ForeignKey(
        SousActivite, on_delete=models.CASCADE, related_name='weekly_entries',
    )
    week_start = models.DateField()  # Monday of the week
    week_end = models.DateField()    # Friday of the week

    # Planning
    planned_description = models.TextField(blank=True, default="")

    # Execution
    status_description = models.TextField(blank=True, default="")

    # Status
    class WeeklyStatus(models.TextChoices):
        PLANIFIE = 'PLANIFIE', 'Planifie'
        EN_COURS = 'EN_COURS', 'En cours'
        REALISE = 'REALISE', 'Realise'
        REPORTE = 'REPORTE', 'Reporte'
        SUSPENDU = 'SUSPENDU', 'Suspendu'
        PARTIELLEMENT_REALISE = 'PARTIELLEMENT_REALISE', 'Partiellement realise'

    status = models.CharField(
        max_length=30, choices=WeeklyStatus.choices,
        default='PLANIFIE',
    )

    # Responsibility (can override sous-activite level)
    responsible = models.CharField(max_length=255, blank=True, default="")
    intervenants = models.CharField(max_length=500, blank=True, default="")

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, null=True, related_name='+',
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.week_start and self.week_start.weekday() != 0:  # 0 = Monday
            from django.core.exceptions import ValidationError
            raise ValidationError({'week_start': 'Week start must be a Monday.'})

    def update(self, *args, user=None, username=None, save=True, **kwargs):
        obj_data = kwargs.pop('data', {})
        if not obj_data:
            obj_data = kwargs
            kwargs = {}
        for key in obj_data:
            setattr(self, key, obj_data[key])
        if save:
            self.save()
        return self

    class Meta:
        ordering = ['-week_start']
        unique_together = ('sous_activite', 'week_start')

    def __str__(self):
        return f"{self.sous_activite.name} - W{self.week_start}"
