import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'neuralspace.settings')
django.setup()

from core.models import *
from django.contrib.auth.models import User

# Clear existing data for fresh seed
BrainHealthDataIndex.objects.all().delete()
Clinician.objects.all().delete()
MedicalTourismFacility.objects.all().delete()
MedicalReport.objects.all().delete()
InsurancePlan.objects.all().delete()
NeurolearnCourse.objects.all().delete()
Message.objects.all().delete()
HealthWalletTransaction.objects.all().delete()
ResourceItem.objects.all().delete()
WellnessProtocol.objects.all().delete()
GreenSpaceMembership.objects.all().delete()
Enrollment.objects.all().delete()

# 1. Seed Global NBHDI Maps
nbhdi_data = [
    ("Neural Village HQ (UNN)", 6.8645, 7.4083, 85.0, 90.0, 88.5),
    ("Geneva NeuroHub", 46.2044, 6.1432, 98.5, 95.0, 96.8),
    ("Boston Cognitive Center", 42.3601, -71.0589, 92.0, 88.0, 90.0),
    ("Lagos Brain Institute", 6.5244, 3.3792, 65.0, 70.0, 67.5),
    ("Tokyo Neurotech Lab", 35.6762, 139.6503, 95.0, 92.0, 93.5),
    ("London Neuroscience", 51.5074, -0.1278, 88.0, 85.0, 86.5),
    ("Sydney Brain Center", -33.8688, 151.2093, 90.0, 89.0, 89.5),
    ("Cape Town Cognition", -33.9249, 18.4241, 75.0, 80.0, 77.5),
    ("Berlin Neuro", 52.5200, 13.4050, 93.0, 88.0, 90.5),
    ("São Paulo Lab", -23.5505, -46.6333, 68.0, 72.0, 70.0),
    ("Toronto Neurotech", 43.6510, -79.3470, 94.0, 90.0, 92.0),
]
for region, lat, lng, soc, env, overall in nbhdi_data:
    BrainHealthDataIndex.objects.create(region_name=region, latitude=lat, longitude=lng, socioeconomic_score=soc, environmental_impact_score=env, overall_index=overall)

# 2. Seed Clinicians
docs = [
    ("Dr. Aris Thorne", "Neurosurgery & BCI", "Geneva Neurological", 4.95, "https://ui-avatars.com/api/?name=Aris+Thorne&background=1e293b&color=3b82f6"),
    ("Dr. Chukwuma Adebayo", "Cognitive Neurology", "Neural Village Labs", 4.92, "https://ui-avatars.com/api/?name=Chukwuma+Adebayo&background=1e293b&color=10b981"),
    ("Dr. Elena Rostova", "EEG Pathology", "Harvard Brain Science", 4.88, "https://ui-avatars.com/api/?name=Elena+Rostova&background=1e293b&color=8b5cf6"),
    ("Dr. Satoshi Nakamoto", "Neuro-Encryption", "Tokyo Tech", 4.99, "https://ui-avatars.com/api/?name=Satoshi+N&background=1e293b&color=f59e0b"),
    ("Dr. Sarah Jenkins", "Pediatric Neurology", "London Health", 4.75, "https://ui-avatars.com/api/?name=Sarah+Jenkins&background=1e293b&color=ef4444"),
]
for name, spec, inst, rat, img in docs:
    Clinician.objects.create(name=name, specialty=spec, institution=inst, rating=rat, image_url=img)

# 3. Seed Tourism Facilities
facilities = [
    ("Alpine Neuro-Rehab", "VR_AR", "Switzerland", "Zurich", 47.3769, 8.5417, "VR/AR assisted post-stroke motor recovery."),
    ("Kyoto Brain Genomics", "RESEARCH", "Japan", "Kyoto", 35.0116, 135.7681, "Advanced genetic testing and neuro-architecture."),
    ("UNN Campus Neuro-Hub", "RESEARCH", "Nigeria", "Nsukka", 6.8645, 7.4083, "Hyper-local neural monitoring and tech incubation."),
    ("Johns Hopkins Neurosurgery", "HOSPITAL", "USA", "Baltimore", 39.2904, -76.6122, "World-class invasive and non-invasive surgeries."),
    ("Seoul BCI Center", "PHC", "South Korea", "Seoul", 37.5665, 126.9780, "Primary screening and BCI implant calibration."),
]
for name, ftype, country, city, lat, lng, desc in facilities:
    MedicalTourismFacility.objects.create(name=name, facility_type=ftype, country=country, city=city, latitude=lat, longitude=lng, description=desc)

# 4. Seed Medical Reports
MedicalReport.objects.create(title="Baseline 64-Channel EEG Spectrum", document_type="EEG Diagnostic Report", encrypted_hash="0x7f2a9c0d12e84b9f33...")
MedicalReport.objects.create(title="Functional MRI Cognitive Mapping", document_type="fMRI Imaging Scan", encrypted_hash="0x3e118ba9820fa49c21...")
MedicalReport.objects.create(title="Post-Op Recovery Telemetry", document_type="Wearable BCI Log", encrypted_hash="0x9a8b7c6d5e4f3g2h1i...")

# 5. Seed Insurance Plans
InsurancePlan.objects.create(name="Standard NeuroCare", monthly_premium=Decimal('49.99'), coverage_details="• Unlimited Telemedicine\n• Basic EEG/BCI Syncing\n• Standard e-MR Storage\n• Access to Academy")
InsurancePlan.objects.create(name="Neural Premium Pro", monthly_premium=Decimal('129.99'), coverage_details="• All Standard Features\n• Full Medical Tourism Coverage\n• Dedicated Hardware Replacements\n• VIP Consultation Queue\n• Advanced Genetic Lab Tests")
InsurancePlan.objects.create(name="Research Advocate", monthly_premium=Decimal('19.99'), coverage_details="• Subsidized access via Data Sharing\n• Monthly NBHDI reports\n• HealthWallet Rewards Multiplier")

# 6. Seed NBHDI Resource Items
ResourceItem.objects.create(resource_type='RESEARCH', title='Urban Correlates of Cognitive Decline in Developing Nations', description='A comprehensive study detailing the methodology behind the NBHDI socio-environmental weighting algorithm.', resource_format='PDF', file_size='2.4 MB', action_label='Download', link='https://example.com/resource1.pdf')
ResourceItem.objects.create(resource_type='DATASET', title='Global Environmental Stressor Baseline (2025)', description='Raw anonymized geospatial dataset utilized for environmental impact scoring.', resource_format='CSV/JSON', file_size='18 MB', action_label='Access', link='https://example.com/dataset1.csv')
ResourceItem.objects.create(resource_type='METHODOLOGY', title='NBHDI Scoring Architecture v1.2', description='Technical documentation on index calculation, node reliability, and update frequency.', resource_format='Wiki/Docs', action_label='Read', link='https://example.com/methodology')

# 7. Seed Neurolearn Courses
NeurolearnCourse.objects.create(title="Fundamentals of Brain-Computer Interfaces", instructor="Dr. Aris Thorne", duration_hours=12, difficulty="Beginner", description="Learn the basic signal processing required to interpret EEG data from commercial headsets.")
NeurolearnCourse.objects.create(title="Neuro-Ethics & Blockchain Data", instructor="Neural Village Legal", duration_hours=6, difficulty="Intermediate", description="Understanding patient data sovereignty, zero-knowledge proofs, and ethical AI in healthcare.")
NeurolearnCourse.objects.create(title="Advanced Applied Neuro-Architecture", instructor="Kyoto Institute", duration_hours=24, difficulty="Advanced", description="Designing physical spaces that promote cognitive healing using spatial computing.")

# 8. Seed Messages
Message.objects.create(sender="Dr. Chukwuma Adebayo", content="Your latest telemetry looks perfectly stable. Keep up the protocol.")
Message.objects.create(sender="NeuralSpace System", content="Your e-MR hash 0x7f2a... has been successfully anchored to the Polygon network.")
Message.objects.create(sender="GreenSpace DAO", content="A new local environmental initiative has launched near your region. Vote now.")

# 8. Seed Wallet Transactions
HealthWalletTransaction.objects.create(transaction_id="TX-892147A", amount=Decimal('250.00'), transaction_type="Reward", description="Monthly Anonymized Data Contribution")
HealthWalletTransaction.objects.create(transaction_id="TX-551029B", amount=Decimal('-49.99'), transaction_type="Payment", description="Standard NeuroCare Subscription")
HealthWalletTransaction.objects.create(transaction_id="TX-110293C", amount=Decimal('1000.00'), transaction_type="Grant", description="BrainHealthFund Alpha User AirDrop")

print("Massive Seed Database Injected Successfully!")
