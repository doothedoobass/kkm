from django.db import models
from django.contrib.auth.models import User

class NeuroProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    full_name = models.CharField(max_length=200, blank=True, default='')
    pathway = models.CharField(max_length=100, default='Patient/User')
    cognitive_goal = models.CharField(max_length=100, default='Memory & Concentration')
    bci_familiarity = models.CharField(max_length=100, default='First Time')
    environment = models.CharField(max_length=100, default='Urban Center')
    subscription_tier = models.CharField(max_length=50, default='Standard Pro')
    web3_wallet = models.CharField(max_length=255, blank=True, null=True)
    data_processing_consent = models.BooleanField(default=True)
    account_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.full_name


class UserFeatureHint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.CharField(max_length=100)
    title = models.CharField(max_length=150)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'key')

    def __str__(self):
        return f"{self.user.username}: {self.key}"

class ResourceItem(models.Model):
    RESOURCE_TYPES = [
        ('RESEARCH', 'Research Paper'),
        ('DATASET', 'Dataset'),
        ('METHODOLOGY', 'Methodology'),
    ]
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    resource_format = models.CharField(max_length=50, blank=True, null=True)
    file_size = models.CharField(max_length=50, blank=True, null=True)
    action_label = models.CharField(max_length=50, default='Open')
    link = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    link_url = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.message[:60]}"


class WellnessProtocol(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    biomarker_source = models.CharField(max_length=150, default='Neural Village Device')
    status = models.CharField(max_length=50, default='active')
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.user.username})"

class GreenSpaceMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default='member')

    def __str__(self):
        return f"{self.user.username} - {self.status}"

class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey('NeurolearnCourse', on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    progress_pct = models.IntegerField(default=0)
    status = models.CharField(max_length=30, default='started')

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.title}"

class BrainHealthDataIndex(models.Model):
    region_name = models.CharField(max_length=150)
    latitude = models.FloatField()
    longitude = models.FloatField()
    socioeconomic_score = models.FloatField()
    environmental_impact_score = models.FloatField()
    overall_index = models.FloatField()
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.region_name} (Index: {self.overall_index})"

class Clinician(models.Model):
    name = models.CharField(max_length=150)
    specialty = models.CharField(max_length=150)
    institution = models.CharField(max_length=200)
    rating = models.FloatField(default=4.9)
    available_for_telemedicine = models.BooleanField(default=True)
    image_url = models.URLField(blank=True, null=True, default="https://ui-avatars.com/api/?name=Doc&background=0D8ABC&color=fff")

    def __str__(self):
        return f"{self.name} - {self.specialty}"

class MedicalTourismFacility(models.Model):
    facility_type_choices = [
        ('PHC', 'Primary Healthcare Centre'),
        ('HOSPITAL', 'Specialized Hospital'),
        ('RESEARCH', 'Medical Research Centre'),
        ('VR_AR', 'VR/AR Neuro-Rehab Center')
    ]
    name = models.CharField(max_length=200)
    facility_type = models.CharField(max_length=20, choices=facility_type_choices)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    description = models.TextField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.country})"

class MedicalReport(models.Model):
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to='medical_reports/%Y/%m/', null=True, blank=True)
    file_size = models.CharField(max_length=50, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    encrypted_hash = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return self.title

class MedicalItinerary(models.Model):
    destination_facility = models.ForeignKey(MedicalTourismFacility, on_delete=models.CASCADE)
    scheduled_date = models.DateField()
    duration_days = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, default='Planned')
    notes = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

class HealthWalletTransaction(models.Model):
    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=50) # Reward, Payment, Grant
    date = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

class InsurancePlan(models.Model):
    name = models.CharField(max_length=100)
    monthly_premium = models.DecimalField(max_digits=8, decimal_places=2)
    coverage_details = models.TextField()
    is_active = models.BooleanField(default=True)


class UserInsuranceSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    profile = models.ForeignKey(NeuroProfile, on_delete=models.SET_NULL, null=True, blank=True)
    plan = models.ForeignKey(InsurancePlan, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, default='active')
    underwriting_score = models.FloatField(null=True, blank=True)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_synced = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} -> {self.plan.name} ({self.status})"

class NeurolearnCourse(models.Model):
    title = models.CharField(max_length=200)
    instructor = models.CharField(max_length=150)
    duration_hours = models.IntegerField()
    difficulty = models.CharField(max_length=50, default='Beginner')
    description = models.TextField()

class Message(models.Model):
    # keep original sender text for backward compatibility
    sender = models.CharField(max_length=100)
    # optional FK to a user if available
    sender_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='received_messages')
    # conversation/thread the message belongs to
    conversation = models.ForeignKey('Conversation', on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']


class Appointment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    clinician = models.ForeignKey(Clinician, on_delete=models.CASCADE, null=True, blank=True)
    facility = models.ForeignKey(MedicalTourismFacility, on_delete=models.SET_NULL, null=True, blank=True)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    modality = models.CharField(max_length=50, choices=[('telemedicine','Telemedicine'),('in_person','In-Person')], default='telemedicine')
    notes = models.TextField(blank=True)
    sync_baseline = models.BooleanField(default=True)
    sync_emr = models.BooleanField(default=True)
    sync_pharm = models.BooleanField(default=False)
    fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=30, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)


class DataAccessGrant(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='grants')
    grant_type = models.CharField(max_length=100)
    granted = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)


class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        parts = list(self.participants.all()[:3])
        return ' / '.join([p.username for p in parts])


class CognitiveMetric(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    focus_retention = models.FloatField(default=0)
    stress_level = models.FloatField(default=0)

    class Meta:
        unique_together = ('user', 'date')

    def __str__(self):
        return f"CognitiveMetric({self.user}, {self.date})"


class NodeEvent(models.Model):
    node_name = models.CharField(max_length=200)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.node_name} @ {self.timestamp.isoformat()}"
